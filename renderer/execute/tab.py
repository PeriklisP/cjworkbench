import io
import logging
from dataclasses import dataclass
from itertools import cycle
from pathlib import Path
from typing import Any, Dict, List, Optional, FrozenSet

import pyarrow as pa

from cjwkernel.chroot import ChrootContext
from cjworkbench.sync import database_sync_to_async
from cjwstate.models import Step, Workflow
from cjwstate.modules.types import ModuleZipfile
from cjwstate.modules.util import gather_param_tab_slugs
from cjwstate.rendercache import load_cached_render_result, CorruptCacheError
from .step import execute_step, locked_step
from .types import StepResult, Tab


logger = logging.getLogger(__name__)


def _init_empty_table_bytes() -> bytes:
    bio = io.BytesIO()
    with pa.ipc.RecordBatchFileWriter(bio, pa.schema([])):
        pass
    return bio.getvalue()


EmptyTableBytes: bytes = _init_empty_table_bytes()


class cached_property:
    """Memoize a property by replacing the function with the retval."""

    def __init__(self, func):
        self.__doc__ = getattr(func, "__doc__")
        self._func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self

        func = self._func
        value = func(obj)
        obj.__dict__[func.__name__] = value
        return value


@dataclass(frozen=True)
class ExecuteStep:
    step: Step
    module_zipfile: Optional[ModuleZipfile]
    params: Dict[str, Any]


@dataclass(frozen=True)
class TabFlow:
    """Sequence of steps in a single Tab.

    This is a data class: there are no database queries here. In particular,
    querying for `.stale_steps` gives the steps that were stale _at the time of
    construction_.
    """

    tab: Tab
    steps: List[ExecuteStep]

    @property
    def tab_slug(self) -> str:
        return self.tab.slug

    @cached_property
    def first_stale_index(self) -> int:
        """Index into `self.steps` of the first Step that needs rendering.

        `None` if the entire flow is fresh.
        """
        cached_results = [step.step.cached_render_result for step in self.steps]
        try:
            # Stale Step means its .cached_render_result is None.
            return cached_results.index(None)
        except ValueError:
            return None

    @cached_property
    def stale_steps(self) -> List[ExecuteStep]:
        """Just the steps of `self.steps` that need rendering.

        `[]` if the entire flow is fresh.
        """
        index = self.first_stale_index
        if index is None:
            return []
        else:
            return self.steps[index:]

    @cached_property
    def last_fresh_step(self) -> Optional[Step]:
        """The first fresh step."""
        stale_index = self.first_stale_index
        if stale_index is None:
            stale_index = len(self.steps)
        fresh_index = stale_index - 1
        if fresh_index < 0:
            return None
        return self.steps[fresh_index].step

    @cached_property
    def input_tab_slugs(self) -> FrozenSet[str]:
        """Slugs of tabs that are used as _input_ into this tab's steps."""
        return frozenset().union(
            *(
                gather_param_tab_slugs(
                    step.module_zipfile.get_spec().param_schema, step.params
                )
                for step in self.steps
                if step.module_zipfile
            )
        )


@database_sync_to_async
def _load_step_result_from_rendercache(
    workflow: Workflow, step: Step, path: Path
) -> StepResult:
    # raises UnneededExecution
    with locked_step(workflow, step) as safe_step:
        crr = safe_step.cached_render_result
        assert crr is not None  # otherwise we'd have raised UnneededExecution

        # Read the entire input Parquet file. Raise CorruptCacheError.
        load_cached_render_result(crr, path)
        return StepResult(path, crr.table_metadata.columns)


async def execute_tab_flow(
    chroot_context: ChrootContext,
    workflow: Workflow,
    flow: TabFlow,
    tab_results: Dict[Tab, Optional[StepResult]],
    output_path: Path,
) -> StepResult:
    """Ensure `flow.tab.live_steps` all cache fresh render results.

    `tab_results.keys()` must be ordered as the Workflow's tabs are.

    Raise `UnneededExecution` if something changes underneath us such that we
    can't guarantee all render results will be fresh. (The remaining execution
    is "unneeded" because we assume another render has been queued.)

    WEBSOCKET NOTES: each step is executed in turn. After each execution,
    we notify clients of its new columns and status.
    """
    logger.debug(
        "Rendering Tab(%d, %s - %s)", workflow.id, flow.tab_slug, flow.tab.name
    )

    basedir = output_path.parent

    # Execute one module at a time.
    #
    # We don't hold any lock throughout the loop: the loop can take a long
    # time; it might be run multiple times simultaneously (even on
    # different computers); and `await` doesn't work with locks.
    #
    # We pass data between two Arrow files, kinda like double-buffering. The
    # two are `output_path` and `buffer_path`. This requires fewer temporary
    # files, so it's less of a hassle to clean up.
    with chroot_context.tempfile_context(
        dir=basedir, prefix="render-buffer", suffix=".arrow"
    ) as buffer_path:
        # We will render from `buffer_path` to `output_path` and from
        # `output_path` to `buffer_path`, alternating, so that the final output
        # is in `output_path` and we only use a single tempfile. (Think "page
        # flipping" in graphics.) Illustrated:
        #
        # [cache] -> A -> B -> C: A and C use `output_path`.
        # [cache] -> A -> B: cache and B use `output_path`.
        step_output_paths = cycle([output_path, buffer_path])

        # Find the first stale step, going backwards. Build a to-do list (in
        # reverse).
        #
        # When render() exits, the render cache should be fresh for all steps.
        # "fresh" means `step.cached_render_result` returns non-None and
        # reading does not result in a `CorruptCacheError`. BUT it's really
        # expensive to check for `CorruptCacheError` all the time; so as an
        # optimization, we only check for `CorruptCacheError` when it prevents
        # us from loading a step's _input_. [2019-10-10, adamhooper] This rule
        # was created so that renderer can recover from `CorruptCacheError`
        # (instead of crashing completely). `CorruptCacheError` is still a
        # serious problem that needs human intervention.
        #
        # A _correct_ approach would be to read every step from the cache.
        #
        # Set `step_index` (first step that needs rendering) and `last_result`
        # (the input to `flow.steps[step_index]`)
        known_stale = flow.first_stale_index
        for step_index in range(len(flow.steps) - 1, -1, -1):
            input_path = next(step_output_paths)
            if known_stale is not None and step_index >= known_stale:
                # We know this step needs to be rendered, from our
                # last_relevant_delta_id math.
                continue  # loop, decrementing `step_index`
            else:
                # This step _shouldn't_ need to be rendered. Load its output.
                # If we get CorruptCacheError, recover by backtracking another
                # step.
                step = flow.steps[step_index].step
                try:
                    # raise CorruptCacheError, UnneededExecution
                    last_result = await _load_step_result_from_rendercache(
                        workflow, step, input_path
                    )
                    # `input_path` will be input into steps[step_index]
                    step_index += 1
                    break
                except CorruptCacheError:
                    logger.exception(
                        "Backtracking to recover from corrupt cache in wf-%d/wfm-%d",
                        workflow.id,
                        step.id,
                    )
                    # loop
        else:
            # "Step minus-1" -- we need an input into flow.steps[0]
            #
            # fiddle with cycle's state -- `last_result` has no backing file;
            # but if it did, it would be `next(step_output_paths)`.
            input_path = next(step_output_paths)
            input_path.write_bytes(EmptyTableBytes)
            last_result = StepResult(path=input_path, columns=[])
            step_index = 0  # needed when there are no steps at all

        for step, output_path in zip(flow.steps[step_index:], step_output_paths):
            output_path.write_bytes(b"")  # don't leak data from two steps ago
            output: StepResult = await execute_step(
                chroot_context=chroot_context,
                workflow=workflow,
                step=step.step,
                module_zipfile=step.module_zipfile,
                params=step.params,
                tab_name=flow.tab.name,
                input_path=last_result.path,
                input_table_columns=last_result.columns,
                tab_results=tab_results,
                output_path=output_path,
            )
            last_result = output

        return last_result
