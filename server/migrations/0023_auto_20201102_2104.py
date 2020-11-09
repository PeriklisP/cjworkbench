# Generated by Django 2.2.16 on 2020-11-02 21:04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("server", "0022_auto_20201020_1915"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflow",
            name="has_custom_report",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="Block",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("slug", models.SlugField()),
                ("position", models.IntegerField()),
                (
                    "block_type",
                    models.CharField(
                        choices=[
                            ("Chart", "Chart"),
                            ("Table", "Table"),
                            ("Text", "Text"),
                        ],
                        editable=False,
                        max_length=5,
                    ),
                ),
                ("text_markdown", models.TextField(blank=True)),
                (
                    "step",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="blocks",
                        to="server.Step",
                    ),
                ),
                (
                    "tab",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="blocks",
                        to="server.Tab",
                    ),
                ),
                (
                    "workflow",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blocks",
                        to="server.Workflow",
                    ),
                ),
            ],
            options={
                "db_table": "block",
                "ordering": ["workflow_id", "position"],
            },
        ),
        migrations.AddConstraint(
            model_name="block",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("block_type", "Chart"),
                        ("step_id__isnull", False),
                        ("tab_id__isnull", True),
                        ("text_markdown", ""),
                    ),
                    models.Q(
                        ("block_type", "Table"),
                        ("step_id__isnull", True),
                        ("tab_id__isnull", False),
                        ("text_markdown", ""),
                    ),
                    models.Q(
                        ("block_type", "Text"),
                        ("step_id__isnull", True),
                        ("tab_id__isnull", True),
                        models.Q(_negated=True, text_markdown=""),
                    ),
                    _connector="OR",
                ),
                name="block_type_nulls_check",
            ),
        ),
        migrations.AddConstraint(
            model_name="block",
            constraint=models.UniqueConstraint(
                fields=("workflow", "slug"), name="unique_workflow_block_slugs"
            ),
        ),
        migrations.AddConstraint(
            model_name="block",
            constraint=models.UniqueConstraint(
                fields=("workflow", "position"), name="unique_workflow_block_positions"
            ),
        ),
    ]