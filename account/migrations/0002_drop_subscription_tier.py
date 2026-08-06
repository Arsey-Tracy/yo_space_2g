from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="organization",
            name="subscription_tier",
        ),
    ]
