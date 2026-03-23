---
name: decisiones_django_mvp
description: Decisiones arquitectónicas clave para el MVP Django de tendermod (2026-03-22)
type: project
---

## Decisión: Django como capa web sobre el backend Python existente
- Django vive en /web/ dentro del mismo repo (no repo separado)
- El package tendermod se importa directamente desde src/ via PYTHONPATH o pip install -e .
- Django NO reimplementa ninguna lógica RAG/LLM — solo orquesta y muestra resultados

## Decisión: Tareas largas con Celery + Redis (no threading)
- Las llamadas LLM duran 30-60 seg → se encolan con Celery
- Redis como broker y result backend
- Frontend usa polling AJAX cada 2-3 seg contra endpoint /api/task-status/<task_id>/

## Decisión: Persistencia entre pasos con Django ORM (no sesión pura)
- Modelo `AnalysisSession` en BD guarda estado del flujo multi-paso
- Los datos extraídos (ExperienceResponse, Indicators) se serializan como JSON en la BD
- La sesión Django solo guarda el session_id → apunta al modelo

## Decisión: Bootstrap 5 para CSS
- Sin build step (no Node/webpack en el MVP)
- CDN en templates base

## Decisión: Archivos subidos en data/ del proyecto tendermod
- PDFs a data/ (donde los espera pdf_loader.py)
- Excels a data/redneet_db/ (donde los espera xls_loader.py)
- Django MEDIA_ROOT apunta a data/uploads/ para archivos temporales adicionales

**Why:** Decisiones tomadas 2026-03-22 al diseñar el MVP.
**How to apply:** El agente django-frontend-builder debe seguir estas decisiones al implementar.
