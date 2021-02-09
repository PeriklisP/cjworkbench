# Generated by Django 3.1.6 on 2021-02-01 15:59

from django.db import migrations


class Migration(migrations.Migration):
    """
    Infer delta.last_applied_at.

    The purpose of last_applied_at is to delete "old" deltas. For instance, in
    this sequence:

        Jan 1: Create delta1
        Jan 2: Create delta2
        Jan 3: Create delta3
        Jan 4: Undo delta3
        Jan 5: Undo delta2 (Workflow is now at delta1)
        Jan 6: Delete deltas older than Jan 4

    delta1: delete (even though it's active!)
    delta2: don't delete (it was applied Jan 5)
    delta3: don't delete (it was applied Jan 4)

    For now, we're _imputing_ last_applied_at: it's starting as the "datetime"
    (a.k.a. created_at) column. The best we can do is say,
    "workflow.updated_at is Jan 5, and since delta2 and delta3 have been undone,
    they were undone as recently as Jan 5.

    It's imperfect because workflow.updated_at wasn't set correctly when undoing
    before 2021-02-01. But this is a corner case and we won't worry too much
    about it.
    """

    dependencies = [
        ("server", "0030_auto_20210201_1430"),
    ]

    operations = [
        migrations.RunSQL(
            [
                """
                -- workflow.updated_at: pick most-recent delta, even if it is
                -- not applied. Un-applied deltas must have been undone, so if
                -- workflow.updated_at is less than an un-applied delta it is
                -- definitely wrong.
                UPDATE workflow
                SET updated_at = GREATEST(
                    updated_at,
                    (
                        SELECT MAX("datetime")
                        FROM delta
                        WHERE delta.workflow_id = workflow.id
                    )
                )
                """,
                """
                -- Set last_applied_at on every applied delta.
                UPDATE delta
                SET last_applied_at = "datetime"
                FROM workflow
                WHERE delta.workflow_id = workflow.id
                  AND delta.id <= workflow.last_delta_id
                """,
                """
                -- Set last_applied_at on every un-applied delta.
                UPDATE delta
                SET last_applied_at = workflow.updated_at
                FROM workflow
                WHERE delta.workflow_id = workflow.id
                  AND delta.id >= workflow.last_delta_id
                  AND workflow.updated_at > delta.last_applied_at
                """,
            ],
            elidable=True,
        ),
    ]