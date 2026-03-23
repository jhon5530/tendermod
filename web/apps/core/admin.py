from django.contrib import admin
from .models import AnalysisSession, AnalysisResult


@admin.register(AnalysisSession)
class AnalysisSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'pdf_filename', 'status', 'created_at', 'updated_at']
    list_filter = ['status']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ['id', 'session', 'cumple_experiencia', 'cumple_indicadores', 'cumple_final', 'created_at']
    list_filter = ['cumple_final']
    readonly_fields = ['created_at']
