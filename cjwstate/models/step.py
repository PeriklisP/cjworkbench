import json
import logging
import secrets
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from django.db import models
from django.db.models import Q

from cjwkernel.types import TableMetadata
from cjwstate import clientside, s3

from .cached_render_result import CachedRenderResult
from .fields import ColumnsField, RenderErrorsField
from .tab import Tab
from .workflow import Workflow

logger = logging.getLogger(__name__)


class Step(models.Model):
    """An instance of a Module in a Tab."""

    class Meta:
        app_label = "server"
        db_table = "step"
        ordering = ["order"]
        constraints = [
            models.CheckConstraint(
                check=(
                    # No way to negate F expressions. Wow.
                    # https://code.djangoproject.com/ticket/16211
                    #
                    # Instead, use a four-way truth-table approach :)
                    (Q(next_update__isnull=True) & Q(auto_update_data=False))
                    | (Q(next_update__isnull=False) & Q(auto_update_data=True))
                ),
                name="auto_update_consistency_check",
            ),
            models.CheckConstraint(
                check=(
                    (
                        Q(cached_migrated_params__isnull=True)
                        & Q(cached_migrated_params_module_version__isnull=True)
                    )
                    | (
                        Q(cached_migrated_params__isnull=False)
                        & Q(cached_migrated_params_module_version__isnull=False)
                    )
                ),
                name="cached_migrated_params_consistency_check",
            ),
            models.UniqueConstraint(
                # Really, we want Step slug to be unique by _workflow_, not
                # by tab. But that's not reasonable with Postgres CHECK constraints.
                # We'll do the heavy lifting in software ... and leave this
                # less-useful check as a constraint as documentation and for the index.
                fields=["tab_id", "slug"],
                name="unique_wf_module_slug",
            ),
        ]
        indexes = [
            models.Index(
                fields=["next_update"],
                name="pending_update_queue",
                condition=Q(next_update__isnull=False, is_deleted=False),
            )
        ]

    slug = models.SlugField(db_index=True)
    """Unique ID, generated by the client.

    Within a Workflow, each Step has a different slug. The client randomly
    generates it so that the client can queue up requests that relate to it,
    before the Step is even created in the database (i.e., before it gets an
    ID). When duplicating a Workflow, we duplicate all its Steps' slugs.

    Slugs are unique per Workflow, and non-reusable. Even after deleting a Step,
    the slug cannot be reused. (This requirement lets us use a database UNIQUE
    INDEX and support soft-deleting.)
    """

    tab = models.ForeignKey(Tab, related_name="steps", on_delete=models.CASCADE)

    module_id_name = models.CharField(max_length=200, default="")

    order = models.IntegerField()

    notes = models.TextField(null=True, blank=True)

    stored_data_version = models.DateTimeField(
        null=True, blank=True
    )  # we may not have stored data

    # drives whether the module is expanded or collapsed on the front-end.
    is_collapsed = models.BooleanField(default=False, blank=False, null=False)

    is_deleted = models.BooleanField(default=False, null=False)

    # For modules that fetch data: how often do we check for updates, and do we
    # switch to latest version automatically
    auto_update_data = models.BooleanField(default=False)

    # when should next update run?
    next_update = models.DateTimeField(null=True, blank=True)
    # time in seconds between updates, default of 1 day
    update_interval = models.IntegerField(default=86400)
    last_update_check = models.DateTimeField(null=True, blank=True)

    # true means, 'email owner when output changes'
    notifications = models.BooleanField(default=False)

    # true means user has not acknowledged email
    has_unseen_notification = models.BooleanField(default=False)

    cached_migrated_params = models.JSONField(null=True, blank=True)
    """Non-secret parameter values -- after a call to migrate_params().

    This may not match the current module version. And it may be `None` for
    backwards compatibility with Steps that did not cache migrated params.

    Why not just overwrite `params`? Because `params` is set by a user and
    `cached_migrated_params` is set by a machine, and let's not confuse our
    sources.
    """

    cached_migrated_params_module_version = models.CharField(
        max_length=200, blank=True, null=True
    )
    """ModuleZipfile .version that generated cached_migrated_params."""

    cached_render_result_delta_id = models.IntegerField(null=True, blank=True)
    cached_render_result_status = models.CharField(
        null=True,
        blank=True,
        choices=[("ok", "ok"), ("error", "error"), ("unreachable", "unreachable")],
        max_length=20,
    )
    cached_render_result_errors = RenderErrorsField(blank=True, default=list)

    # should be models.JSONField but we need backwards-compatibility
    cached_render_result_json = models.BinaryField(blank=True)
    cached_render_result_columns = ColumnsField(null=True, blank=True)
    cached_render_result_nrows = models.IntegerField(null=True, blank=True)

    # TODO once we auto-compute stale module outputs, nix is_busy -- it will
    # be implied by the fact that the cached output revision is wrong.
    is_busy = models.BooleanField(default=False, null=False)

    fetch_errors = RenderErrorsField(default=list)
    """Most recent collection of errors preventing StoredObject creation.

    For instance, HTTP errors.

    See also `cached_render_result_errors`, which pertains to render().
    """

    # Most-recent delta that may possibly affect the output of this module.
    # This isn't a ForeignKey because many deltas have a foreign key pointing
    # to the Step, so we'd be left with a chicken-and-egg problem.
    last_relevant_delta_id = models.IntegerField(default=0, null=False)

    params = models.JSONField(default=dict)
    """Non-secret parameter values, valid at time of writing.

    This may not match the current module version: migrate_params() will make
    the params match today's Python and JavaScript.

    These values were set by a human.
    """

    secrets = models.JSONField(default=dict)
    """Dict of {'name': ..., 'secret': ...} values that are private.

    Secret values aren't duplicated, and they're not stored in undo history.
    They have no schema: they're either set, or they're missing.

    Secrets aren't passed to `render()`: they're only passed to `fetch()`.
    """

    file_upload_api_token = models.CharField(
        max_length=100, null=True, blank=True, default=None
    )
    """"Authorization" header bearer token for programs to use "uploadfile".

    This may optionally be set on 'uploadfile' modules and no others. Workbench
    will allow HTTP requests with the header
    `Authorization: bearer {file_upload_api_token}` to file-upload APIs.

    Never expose this API token to readers. Only owner and writers may see it.
    """

    def __str__(self):
        # Don't use DB queries here.
        return "step[%d] at position %d" % (self.id, self.order)

    @property
    def workflow(self):
        return Workflow.objects.get(tabs__steps__id=self.id)

    @property
    def workflow_id(self):
        return self.tab.workflow_id

    @property
    def tab_slug(self):
        return self.tab.slug

    @property
    def uploaded_file_prefix(self):
        """ "Folder" on S3 where uploads go.

        This ends in "/", so it can be used as a prefix in s3 operations.
        """
        return f"wf-{self.workflow_id}/wfm-{self.id}/"

    @classmethod
    def live_in_workflow(cls, workflow: Union[int, Workflow]) -> models.QuerySet:
        """QuerySet of not-deleted Steps in `workflow`, ordered by tab+position.

        You may specify `workflow` by its `pk` or as an object.

        Deleted Steps and Steps in deleted Tabs will omitted.
        """
        if isinstance(workflow, int):
            workflow_id = workflow
        else:
            workflow_id = workflow.pk

        return cls.objects.filter(
            tab__workflow_id=workflow_id, tab__is_deleted=False, is_deleted=False
        ).order_by("tab__position", "order")

    # ---- Authorization ----
    # User can access step if they can access workflow
    def request_authorized_read(self, request):
        return self.workflow.request_authorized_read(request)

    def request_authorized_write(self, request):
        return self.workflow.request_authorized_write(request)

    def list_fetched_data_versions(self):
        return list(
            self.stored_objects.order_by("-stored_at").values_list("stored_at", "read")
        )

    @property
    def secret_metadata(self) -> Dict[str, Any]:
        """Dict keyed by secret name, with values {'name': '...'}.

        Missing secrets are not included in the returned dict. Secrets are not
        validated against a schema.
        """
        return {k: {"name": v["name"]} for k, v in self.secrets.items() if v}

    # --- Duplicate ---
    # used when duplicating a whole workflow
    def duplicate_into_new_workflow(self, to_tab):
        to_workflow = to_tab.workflow

        # Slug must be unique across the entire workflow; therefore, the
        # duplicate Step must be on a different workflow. (If we need
        # to duplicate within the same workflow, we'll need to change the
        # slug -- different method, please.)
        assert to_tab.workflow_id != self.workflow_id
        slug = self.slug

        # SECURITY: set last_relevant_delta_id=0: any number is allowed
        # here, and 0 conveys no additional information.
        return self._duplicate_with_slug_and_delta_id(to_tab, slug, 0)

    def duplicate_into_same_workflow(self, to_tab):
        # Make sure we're calling this correctly
        assert to_tab.workflow_id == self.workflow_id

        # Generate a new slug: 9 bytes, base64-encoded, + and / becoming - and _.
        # Mimics assets/js/utils.js:generateSlug()
        slug = "step-" + secrets.token_urlsafe(9)

        # last_relevant_delta_id is _wrong_, but we need to set it to
        # something. See DuplicateTabCommand to understand the chicken-and-egg
        # dilemma.
        last_relevant_delta_id = self.last_relevant_delta_id

        return self._duplicate_with_slug_and_delta_id(
            to_tab, slug, last_relevant_delta_id
        )

    def _duplicate_with_slug_and_delta_id(self, to_tab, slug, last_relevant_delta_id):
        # Initialize but don't save
        new_step = Step(
            tab=to_tab,
            slug=slug,
            module_id_name=self.module_id_name,
            fetch_errors=self.fetch_errors,
            stored_data_version=self.stored_data_version,
            order=self.order,
            notes=self.notes,
            is_collapsed=self.is_collapsed,
            auto_update_data=False,
            next_update=None,
            update_interval=self.update_interval,
            last_update_check=self.last_update_check,
            last_relevant_delta_id=last_relevant_delta_id,
            params=self.params,
            secrets={},  # DO NOT COPY SECRETS
        )

        # Copy cached render result, if there is one.
        #
        # If we duplicate a Workflow mid-render, the cached render result might
        # not have any useful data. But that's okay: just kick off a new
        # render. The common case (all-rendered Workflow) will produce a
        # fully-rendered duplicate Workflow.
        #
        # We cannot copy the cached result if the destination Tab has a
        # different name than this one: tab_name is passed to render(), so even
        # an exactly-duplicated Step can have a different output.
        cached_result = self.cached_render_result
        if cached_result is not None and self.tab.name == to_tab.name:
            # assuming file-copy succeeds, copy cached results.
            new_step.cached_render_result_delta_id = new_step.last_relevant_delta_id
            for attr in ("status", "errors", "json", "columns", "nrows"):
                full_attr = f"cached_render_result_{attr}"
                setattr(new_step, full_attr, getattr(self, full_attr))

            new_step.save()  # so there is a new_step.id for parquet_key

            # Now new_step.cached_render_result will return a
            # CachedRenderResult, because all the DB values are set. It'll have
            # a .parquet_key ... but there won't be a file there (because we
            # never wrote it).
            from cjwstate.rendercache.io import BUCKET, crr_parquet_key

            old_parquet_key = crr_parquet_key(cached_result)
            new_parquet_key = crr_parquet_key(new_step.cached_render_result)

            try:
                s3.copy(
                    s3.CachedRenderResultsBucket,
                    new_parquet_key,
                    "%(Bucket)s/%(Key)s" % {"Bucket": BUCKET, "Key": old_parquet_key},
                )
            except s3.layer.error.NoSuchKey:
                # DB and filesystem are out of sync. CachedRenderResult handles
                # such cases gracefully. So `new_result` will behave exactly
                # like `cached_result`.
                pass
        else:
            new_step.save()

        # Duplicate the current stored data only, not the history
        if self.stored_data_version is not None:
            self.stored_objects.get(stored_at=self.stored_data_version).duplicate(
                new_step
            )

        # For each "file" param, duplicate the "selected" uploaded_file if there
        # is one.
        #
        # We assume any UUID in `params` that points to an uploaded file _is_
        # a file-dtype param. ([adamhooper, 2020-07-14] when the assumption does
        # not hold, will this cause DB errors? Not sure, but it's not a security
        # risk.)
        #
        # Why not check the param schema? Because we'd need to define behavior
        # for when the module doesn't exist, or its version is changed, or its
        # code breaks.... bah! These behaviors don't line up with any user
        # expectations. Users want to copy the thing they see.
        for uuid_str in self.params.values():
            if not isinstance(uuid_str, str):
                continue
            try:
                UUID(uuid_str)
            except ValueError:
                continue
            uploaded_file = self.uploaded_files.filter(uuid=uuid_str).first()
            if not uploaded_file:
                continue

            new_key = uploaded_file.key.replace(
                self.uploaded_file_prefix, new_step.uploaded_file_prefix
            )
            assert new_key != uploaded_file.key
            # TODO handle file does not exist
            s3.copy(
                s3.UserFilesBucket,
                new_key,
                f"{s3.UserFilesBucket}/{uploaded_file.key}",
            )
            new_step.uploaded_files.create(
                created_at=uploaded_file.created_at,
                name=uploaded_file.name,
                size=uploaded_file.size,
                uuid=uploaded_file.uuid,
                key=new_key,
            )

        return new_step

    @property
    def cached_render_result(self) -> CachedRenderResult:
        """A CachedRenderResult with this Step's rendered output.

        Return `None` if there is a cached result but it is not fresh.

        This does not read the dataframe from disk. If you want a "snapshot in
        time" of the `render()` output, you need a lock, like this:

            # Lock the workflow, making sure we don't overwrite data
            with workflow.cooperative_lock():
                step.refresh_from_db()
                # Read from disk
                with cjwstate.rendercache.io.open_cached_render_result(
                    step.cached_render_result
                ) as result:
                    ...
        """
        result = self._build_cached_render_result_fresh_or_not()
        if result and result.delta_id != self.last_relevant_delta_id:
            return None
        return result

    def get_stale_cached_render_result(self):
        """
        Build a CachedRenderResult with this Step's stale rendered output.

        Return `None` if there is a cached result but it is fresh.

        This does not read the dataframe from disk. If you want a "snapshot in
        time" of the `render()` output, you need a lock, like this:

            # Lock the workflow, making sure we don't overwrite data
            with workflow.cooperative_lock():
                step.refresh_from_db()
                # Read from disk
                with cjwstate.rendercache.io.open_cached_render_result(
                    step.get_stale_cached_render_result()
                ) as result:
                    ...
        """
        result = self._build_cached_render_result_fresh_or_not()
        if result and result.delta_id == self.last_relevant_delta_id:
            return None
        return result

    def _build_cached_render_result_fresh_or_not(self) -> Optional[CachedRenderResult]:
        """Build a CachedRenderResult with this Step's rendered output.

        If the output is stale, return it anyway. (The return value's .delta_id
        will not match this Step's .delta_id.)

        This does not read the dataframe from disk. If you want a "snapshot in
        time" of the `render()` output, you need a lock, like this:

            # Lock the workflow, making sure we don't overwrite data
            with workflow.cooperative_lock():
                step.refresh_from_db()
                # Read from disk
                with cjwstate.rendercache.io.open_cached_render_result(
                    step.get_stale_cached_render_result()
                ) as result:
        """
        if self.cached_render_result_delta_id is None:
            return None

        delta_id = self.cached_render_result_delta_id
        status = self.cached_render_result_status
        columns = self.cached_render_result_columns
        errors = self.cached_render_result_errors
        nrows = self.cached_render_result_nrows

        # cached_render_result_json is sometimes a memoryview
        json_bytes = bytes(self.cached_render_result_json)
        if json_bytes:
            json_dict = json.loads(json_bytes)
        else:
            json_dict = {}

        return CachedRenderResult(
            workflow_id=self.workflow_id,
            step_id=self.id,
            delta_id=delta_id,
            status=status,
            errors=errors,
            json=json_dict,
            table_metadata=TableMetadata(nrows, columns),
        )

    def delete(self, *args, **kwargs):
        # TODO make DB _not_ depend upon s3.
        s3.remove_recursive(s3.UserFilesBucket, self.uploaded_file_prefix)
        s3.remove_recursive(
            s3.CachedRenderResultsBucket,
            "wf-%d/wfm-%d/" % (self.workflow_id, self.id),
        )
        # We can't delete in-progress uploads from tusd's bucket because there's
        # no directory hierarchy. The object lifecycle policy will delete them.
        super().delete(*args, **kwargs)

    def get_clientside_files(self) -> List[clientside.UploadedFile]:
        return [
            clientside.UploadedFile(
                name=name, uuid=uuid, size=size, created_at=created_at
            )
            for name, uuid, size, created_at in self.uploaded_files.order_by(
                "-created_at"
            ).values_list("name", "uuid", "size", "created_at")
        ]

    def get_clientside_fetched_version_list(self) -> clientside.FetchedVersionList:
        return clientside.FetchedVersionList(
            versions=[
                clientside.FetchedVersion(created_at=created_at, is_seen=is_seen)
                for created_at, is_seen in self.stored_objects.order_by(
                    "-stored_at"
                ).values_list("stored_at", "read")
            ],
            selected=self.stored_data_version,
        )

    def to_clientside(self) -> clientside.StepUpdate:
        # params
        from cjwstate.models.module_registry import MODULE_REGISTRY

        try:
            module_zipfile = MODULE_REGISTRY.latest(self.module_id_name)
        except KeyError:
            module_zipfile = None

        if module_zipfile is None:
            params = {}
        else:
            from cjwstate.params import get_migrated_params

            module_spec = module_zipfile.get_spec()
            param_schema = module_spec.get_param_schema()
            # raise ModuleError
            params = get_migrated_params(self, module_zipfile=module_zipfile)
            try:
                param_schema.validate(params)
            except ValueError:
                logger.exception(
                    "%s.migrate_params() gave invalid output: %r",
                    self.module_id_name,
                    params,
                )
                params = param_schema.coerce(params)

        crr = self._build_cached_render_result_fresh_or_not()
        if crr is None:
            crr = clientside.Null

        return clientside.StepUpdate(
            id=self.id,
            slug=self.slug,
            module_slug=self.module_id_name,
            tab_slug=self.tab_slug,
            is_busy=self.is_busy,
            render_result=crr,
            files=self.get_clientside_files(),
            params=params,
            secrets=self.secret_metadata,
            is_collapsed=self.is_collapsed,
            notes=self.notes,
            is_auto_fetch=self.auto_update_data,
            fetch_interval=self.update_interval,
            last_fetched_at=self.last_update_check,
            is_notify_on_change=self.notifications,
            has_unseen_notification=self.has_unseen_notification,
            last_relevant_delta_id=self.last_relevant_delta_id,
            versions=self.get_clientside_fetched_version_list(),
        )
