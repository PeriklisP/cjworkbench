import asyncio
import datetime
from unittest.mock import patch

from django.contrib.auth.models import User

from cjworkbench.models.userusage import UserUsage
from cjwstate import clientside, commands, rabbitmq
from cjwstate.models.block import Block
from cjwstate.models.commands import DeleteStep
from cjwstate.models.workflow import Workflow
from cjwstate.tests.utils import DbTestCase


async def async_noop(*args, **kwargs):
    pass


class DeleteStepTest(DbTestCase):
    @patch.object(rabbitmq, "send_update_to_workflow_clients", async_noop)
    @patch.object(rabbitmq, "send_user_update_to_user_clients", async_noop)
    def test_delete_lone_step(self):
        workflow = Workflow.create_and_init()  # tab-1
        tab1 = workflow.tabs.first()
        step = tab1.steps.create(
            order=0,
            slug="step-1",
            last_relevant_delta_id=workflow.last_delta_id,
            params={"url": ""},
        )

        self.run_with_async_db(
            commands.do(DeleteStep, workflow_id=workflow.id, step=step)
        )
        step.refresh_from_db()  # it is only _soft_-deleted.
        self.assertEqual(step.is_deleted, True)
        self.assertEqual(list(tab1.live_steps.values_list("slug", "order")), [])

        self.run_with_async_db(commands.undo(workflow.id))
        step.refresh_from_db()
        self.assertEqual(step.is_deleted, False)
        self.assertEqual(
            list(tab1.live_steps.values_list("slug", "order")), [("step-1", 0)]
        )

        self.run_with_async_db(commands.redo(workflow.id))
        step.refresh_from_db()  # it is only _soft_-deleted.
        self.assertEqual(step.is_deleted, True)
        self.assertEqual(list(tab1.live_steps.values_list("slug", "order")), [])

    @patch.object(rabbitmq, "send_update_to_workflow_clients")
    @patch.object(rabbitmq, "send_user_update_to_user_clients", async_noop)
    def test_delete_custom_report_blocks(self, send_update):
        future_none = asyncio.Future()
        future_none.set_result(None)
        send_update.return_value = future_none

        workflow = Workflow.create_and_init(has_custom_report=True)  # tab-1
        tab1 = workflow.tabs.first()
        step1 = tab1.steps.create(
            order=0,
            slug="step-1",
            last_relevant_delta_id=workflow.last_delta_id,
            params={"url": ""},
        )
        step2 = tab1.steps.create(
            order=0,
            slug="step-2",
            last_relevant_delta_id=workflow.last_delta_id,
            params={"url": ""},
        )

        # Report will include the step twice, and have another step elsewhere
        # that should not be touched
        block1 = workflow.blocks.create(
            position=0, slug="block-step-1-1", block_type="Chart", step=step1
        )
        block2 = workflow.blocks.create(
            position=1, slug="block-step-2", block_type="Chart", step=step2
        )
        block3 = workflow.blocks.create(
            position=2, slug="block-step-1-2", block_type="Chart", step=step1
        )

        self.run_with_async_db(
            commands.do(DeleteStep, workflow_id=workflow.id, step=step1)
        )

        with self.assertRaises(Block.DoesNotExist):
            block1.refresh_from_db()
        with self.assertRaises(Block.DoesNotExist):
            block3.refresh_from_db()
        block2.refresh_from_db()
        self.assertEqual(block2.position, 0)

        send_update.assert_called()
        update = send_update.call_args[0][1]
        self.assertEqual(update.workflow.block_slugs, ["block-step-2"])
        self.assertEqual(
            update.tabs, {"tab-1": clientside.TabUpdate(step_ids=[step2.id])}
        )
        self.assertEqual(update.clear_step_ids, frozenset([step1.id]))
        self.assertEqual(update.blocks, {})

        self.run_with_async_db(commands.undo(workflow.id))
        # The old blocks are deleted. We expect new blocks with new IDs.
        with self.assertRaises(Block.DoesNotExist):
            block1.refresh_from_db()
        with self.assertRaises(Block.DoesNotExist):
            block3.refresh_from_db()
        new_block1 = workflow.blocks.get(slug=block1.slug)
        new_block3 = workflow.blocks.get(slug=block3.slug)
        self.assertEqual(new_block1.step_id, step1.id)
        self.assertEqual(new_block3.step_id, step1.id)
        block2.refresh_from_db()
        self.assertEqual(new_block1.position, 0)
        self.assertEqual(block2.position, 1)
        self.assertEqual(new_block3.position, 2)
        send_update.assert_called()
        update = send_update.call_args[0][1]
        self.assertEqual(
            update.workflow.block_slugs,
            ["block-step-1-1", "block-step-2", "block-step-1-2"],
        )
        self.assertEqual(
            update.tabs, {"tab-1": clientside.TabUpdate(step_ids=[step1.id, step2.id])}
        )
        self.assertEqual(
            update.blocks,
            {
                "block-step-1-1": clientside.ChartBlock("step-1"),
                "block-step-1-2": clientside.ChartBlock("step-1"),
            },
        )

        self.run_with_async_db(commands.redo(workflow.id))
        block2.refresh_from_db()
        self.assertEqual(block2.position, 0)

    @patch.object(rabbitmq, "send_user_update_to_user_clients")
    @patch.object(rabbitmq, "send_update_to_workflow_clients", async_noop)
    def test_update_workflow_fetches_per_day(self, send_user_update):
        send_user_update.side_effect = async_noop

        user = User.objects.create(email="a@example.org")
        workflow = Workflow.create_and_init(owner_id=user.id, fetches_per_day=3.0)
        tab = workflow.tabs.first()
        tab.steps.create(
            slug="step-1",
            order=0,
            auto_update_data=True,
            update_interval=86400,
            next_update=datetime.datetime.now(),
        )
        step2 = tab.steps.create(
            slug="step-2",
            order=1,
            auto_update_data=True,
            update_interval=43200,
            next_update=datetime.datetime.now(),
        )

        self.run_with_async_db(
            commands.do(DeleteStep, workflow_id=workflow.id, step=step2)
        )
        workflow.refresh_from_db()
        self.assertEqual(workflow.fetches_per_day, 1.0)

        send_user_update.assert_called_with(
            user.id, clientside.UserUpdate(usage=UserUsage(1.0))
        )
        send_user_update.reset_mock()

        # Undo doesn't increase usage (user might not expect it to)
        self.run_with_async_db(commands.undo(workflow.id))
        send_user_update.assert_not_called()
        workflow.refresh_from_db()
        self.assertEqual(workflow.fetches_per_day, 1.0)
        step2.refresh_from_db()
        self.assertEqual(step2.auto_update_data, False)


#      @patch.object(rabbitmq, "send_update_to_workflow_clients")
#      def test_clientside_update(self, send_update):
#         future_none = asyncio.Future()
#         future_none.set_result(None)
#         send_update.return_value = future_none
#
#         workflow = Workflow.create_and_init(selected_tab_position=0)  # tab-1
#         tab2 = workflow.tabs.create(position=1, slug="tab-2")
#         self.run_with_async_db(
#             commands.do(DeleteTab, workflow_id=workflow.id, tab=tab2)
#         )
#         delta1 = send_update.call_args[0][1]
#         self.assertEqual(delta1.workflow.tab_slugs, ["tab-1"])
#         self.assertFalse(delta1.tabs)
#         self.assertEqual(delta1.clear_tab_slugs, frozenset(["tab-2"]))
#
#         self.run_with_async_db(commands.undo(workflow.id))
#         delta2 = send_update.call_args[0][1]
#         self.assertEqual(delta2.workflow.tab_slugs, ["tab-1", "tab-2"])
#         self.assertEqual(list(delta2.tabs.keys()), ["tab-2"])
#         self.assertFalse(delta2.clear_tab_slugs)
