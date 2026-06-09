from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_analysisresult_cumple_equipo_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysissession',
            name='timing_json',
            field=models.TextField(blank=True, default='[]'),
        ),
    ]
