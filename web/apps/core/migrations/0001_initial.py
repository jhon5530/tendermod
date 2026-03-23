from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='AnalysisSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[
                        ('created', 'Creado'),
                        ('ingesting_pdf', 'Ingiriendo PDF'),
                        ('pdf_ready', 'PDF listo'),
                        ('extracted', 'Requisitos extraidos'),
                        ('evaluating', 'Evaluando'),
                        ('completed', 'Completado'),
                        ('error', 'Error'),
                    ],
                    default='created',
                    max_length=20,
                )),
                ('pdf_filename', models.CharField(blank=True, max_length=255)),
                ('experience_requirements_json', models.TextField(blank=True)),
                ('indicators_requirements_json', models.TextField(blank=True)),
                ('general_info_text', models.TextField(blank=True)),
                ('celery_task_id', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AnalysisResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('experience_result_json', models.TextField(blank=True)),
                ('indicators_result_json', models.TextField(blank=True)),
                ('cumple_experiencia', models.BooleanField(null=True)),
                ('cumple_indicadores', models.BooleanField(null=True)),
                ('cumple_final', models.BooleanField(null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('session', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='result',
                    to='core.analysissession',
                )),
            ],
        ),
    ]
