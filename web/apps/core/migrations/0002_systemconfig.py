from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('threshold_objeto', models.FloatField(default=0.75)),
            ],
            options={
                'verbose_name': 'Configuracion del sistema',
            },
        ),
    ]
