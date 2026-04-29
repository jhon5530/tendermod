from django.db import models


class AnalysisSession(models.Model):
    STATUS_CHOICES = [
        ('created', 'Creado'),
        ('ingesting_pdf', 'Ingiriendo PDF'),
        ('pdf_ready', 'PDF listo'),
        ('extracted', 'Requisitos extraidos'),
        ('evaluating', 'Evaluando'),
        ('completed', 'Completado'),
        ('error', 'Error'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created')
    pdf_filename = models.CharField(max_length=255, blank=True)
    # ExperienceResponse.model_dump_json()
    experience_requirements_json = models.TextField(blank=True)
    # MultipleIndicatorResponse.model_dump_json()
    indicators_requirements_json = models.TextField(blank=True)
    # General info string from get_general_info()
    general_info_text = models.TextField(blank=True)
    # GeneralRequirementList.model_dump_json()
    general_requirements_json = models.TextField(blank=True, default='')
    celery_task_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Session {self.pk} — {self.pdf_filename} [{self.status}]"

    @property
    def status_display_class(self):
        mapping = {
            'created': 'secondary',
            'ingesting_pdf': 'warning',
            'pdf_ready': 'info',
            'extracted': 'primary',
            'evaluating': 'warning',
            'completed': 'success',
            'error': 'danger',
        }
        return mapping.get(self.status, 'secondary')


class AnalysisResult(models.Model):
    session = models.OneToOneField(
        AnalysisSession,
        on_delete=models.CASCADE,
        related_name='result',
    )
    # ExperienceComplianceResult.model_dump_json()
    experience_result_json = models.TextField(blank=True)
    # IndicatorComplianceResult.model_dump_json()
    indicators_result_json = models.TextField(blank=True)
    cumple_experiencia = models.BooleanField(null=True)
    cumple_indicadores = models.BooleanField(null=True)
    cumple_final = models.BooleanField(null=True)
    # Contexto RAG crudo del retriever usado en cada evaluacion
    indicators_context_text = models.TextField(blank=True, default='')
    experience_context_text = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Result for Session {self.session_id}"


class SystemConfig(models.Model):
    threshold_objeto = models.FloatField(default=0.75)

    class Meta:
        verbose_name = "Configuracion del sistema"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
