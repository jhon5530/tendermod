from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_systemconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysisresult',
            name='indicators_context_text',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='analysisresult',
            name='experience_context_text',
            field=models.TextField(blank=True, default=''),
        ),
    ]
