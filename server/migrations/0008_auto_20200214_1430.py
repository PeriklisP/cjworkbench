# Generated by Django 2.2.10 on 2020-02-14 14:30

import cjwstate.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("server", "0007_jsonize_fetch_errors")]

    operations = [
        migrations.AlterField(
            model_name="wfmodule",
            name="fetch_errors",
            field=cjwstate.models.fields.RenderErrorsField(default=list),
        )
    ]
