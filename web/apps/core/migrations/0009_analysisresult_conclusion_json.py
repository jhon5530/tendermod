from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_analysissession_timing_json'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysisresult',
            name='conclusion_json',
            field=models.TextField(blank=True, default=''),
        ),
    ]
