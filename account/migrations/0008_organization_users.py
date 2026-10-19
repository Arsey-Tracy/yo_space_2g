from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0007_alter_customuser_id_alter_member_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="users",
            field=models.ManyToManyField(
                related_name="organizations",
                through="account.Member",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
