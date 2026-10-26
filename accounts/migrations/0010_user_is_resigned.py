from django.db import migrations, models


def mark_existing_inactive_users_resigned(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(is_active=False).update(is_resigned=True)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_alter_user_is_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_resigned',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            mark_existing_inactive_users_resigned,
            migrations.RunPython.noop,
        ),
    ]
