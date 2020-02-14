# Generated by Django 2.2.10 on 2020-02-14 14:25

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("server", "0006_auto_20200210_1959")]

    operations = [
        migrations.RunSQL(
            [
                """
                UPDATE server_wfmodule
                SET fetch_errors = CASE fetch_error
                    WHEN '' THEN jsonb_build_array()
                    ELSE jsonb_build_array(jsonb_build_object(
                        'message', jsonb_build_object(
                            'id', 'TODO_i18n',
                            'arguments', jsonb_build_object('text', fetch_error)
                        ),
                        'quickFixes', jsonb_build_array()
                    )) END
                WHERE fetch_error IS NOT NULL
                  AND fetch_error <> ''
                  AND (fetch_errors IS NULL OR jsonb_array_length(fetch_errors) = 0)
                """
            ],
            elidable=True,
        )
    ]
