from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_analysisresult_conclusion_json'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysissession',
            name='auto_flow_active',
            field=models.BooleanField(default=False),
        ),
    ]
