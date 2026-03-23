# Análisis Técnico: MVP Django — Interfaz Web tendermod

## Problema

El backend tendermod está completamente implementado (RAG, ChromaDB, SQLite, OpenAI gpt-4o-mini) pero solo es ejecutable desde línea de comandos (`python -m tendermod.main`). No existe una interfaz que permita a un usuario no técnico:

- Cargar los datos de la empresa (Excels con indicadores y experiencia RUP)
- Subir el PDF del pliego de condiciones
- Revisar y corregir la interpretación del LLM antes de evaluar
- Lanzar la evaluación de cumplimiento
- Ver y exportar los resultados

El objetivo es un **MVP web funcional** que exponga las capacidades existentes sin modificar el backend.

---

## Impacto Arquitectural

### Backend
- **Sin modificaciones.** Todas las funciones públicas se consumen tal como están.
- Restricción crítica: `ingest_documents()` y `load_db()` son stateless y leen desde paths fijos en `data/` — el frontend debe copiar los archivos antes de llamarlos.
- `indicators_comparation()` tiene query hardcodeada internamente — para el flujo de edición humana se deben usar las funciones de bajo nivel: `merge_indicators()` + `run_llm_indicators_comparation()`.

### Frontend Django (nuevo)
- Proyecto Django en `web/` como sibling del backend `src/`
- 3 apps: `core` (estado), `redneet` (ingesta empresa), `analysis` (flujo análisis)
- Celery + Redis para tareas largas (LLM calls de 30–60 segundos)
- Polling AJAX para feedback en tiempo real

### Base de datos
- `web/db.sqlite3` → Django ORM (sesiones de análisis, resultados)
- `data/redneet_db/redneet_database.db` → backend tendermod (NO tocar desde Django)
- Separación total: Django nunca escribe en la BD del backend

---

## Propuesta de Solución

### Estructura de directorios

```
tendermod/
├── src/tendermod/          # backend existente — NO modificar
├── data/                   # compartido: PDFs, Excels, ChromaDB, SQLite backend
└── web/                    # NUEVO — proyecto Django
    ├── manage.py
    ├── requirements.txt
    ├── tendermod_web/
    │   ├── settings/
    │   │   ├── base.py     # paths, celery, sys.path para importar tendermod
    │   │   └── local.py
    │   ├── urls.py
    │   ├── wsgi.py
    │   └── celery.py
    ├── apps/
    │   ├── core/           # modelos AnalysisSession + AnalysisResult, polling API
    │   ├── redneet/        # Vista 1: ingesta datos empresa
    │   └── analysis/       # Vista 2 y 3: flujo análisis
    ├── templates/
    │   ├── base.html
    │   ├── redneet/
    │   └── analysis/
    └── static/js/
        └── task_polling.js
```

### Modelos Django

```python
# apps/core/models.py

class AnalysisSession(models.Model):
    STATUS_CHOICES = [
        ('created', 'Creado'),
        ('ingesting_pdf', 'Ingiriendo PDF'),
        ('pdf_ready', 'PDF listo'),
        ('extracted', 'Requisitos extraídos'),
        ('evaluating', 'Evaluando'),
        ('completed', 'Completado'),
        ('error', 'Error'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created')
    pdf_filename = models.CharField(max_length=255, blank=True)
    experience_requirements_json = models.TextField(blank=True)  # ExperienceResponse.model_dump_json()
    indicators_requirements_json = models.TextField(blank=True)  # MultipleIndicatorResponse.model_dump_json()
    celery_task_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class AnalysisResult(models.Model):
    session = models.OneToOneField(AnalysisSession, on_delete=models.CASCADE)
    experience_result_json = models.TextField(blank=True)   # ExperienceComplianceResult.model_dump_json()
    indicators_result_json = models.TextField(blank=True)   # texto libre del LLM
    cumple_experiencia = models.BooleanField(null=True)
    cumple_indicadores = models.BooleanField(null=True)
    cumple_final = models.BooleanField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### URL Patterns

```
/                               → redirect a /redneet/
/redneet/                       → Vista 1: dashboard empresa
/redneet/upload-indicadores/    → POST: subir rib.xlsx
/redneet/upload-experiencia/    → POST: subir experiencia_rup.xlsx

/analysis/                      → lista de sesiones
/analysis/new/                  → nueva sesión + subida PDF
/analysis/<id>/step1/           → extracción de requisitos (3 botones)
/analysis/<id>/step2/           → edición humana + botones evaluación
/analysis/<id>/results/         → resultados finales
/analysis/<id>/export/excel/
/analysis/<id>/export/text/

/api/task-status/<task_id>/     → JSON polling endpoint
/api/db-status/                 → conteo registros SQLite empresa
```

### Flujo de datos end-to-end

```
[Usuario sube PDF]
  → PDFUploadForm → shutil.copy → data/<filename>.pdf
  → AnalysisSession(status='ingesting_pdf')
  → Celery: ingest_pdf_task → ingest_documents() → status='pdf_ready'
  → JS habilita botones de extracción

[Usuario click "Buscar requisitos Experiencia"]
  → POST AJAX /analysis/<id>/step1/extract/ {action:"experience"}
  → Celery: extract_experience_task → experience_comparation()
  → session.experience_requirements_json = exp.model_dump_json()
  → JS polling → SUCCESS → habilitar "Continuar al Paso 2"

[Usuario edita Form A en Paso 2]
  → ExperienceEditForm pre-poblado desde experience_requirements_json

[Usuario click "Evaluar Experiencia"]
  → POST AJAX {action:"experience", experience_data:{...}}
  → Celery: evaluate_experience_task
      → ExperienceResponse(**experience_data)
      → check_compliance_experience(exp) → ExperienceComplianceResult
      → AnalysisResult.experience_result_json = result.model_dump_json()
  → JS polling → SUCCESS → redirect a /results/
```

### Manejo de tareas largas: Celery + Polling

```python
# apps/core/views.py
from celery.result import AsyncResult

def task_status(request, task_id):
    result = AsyncResult(task_id)
    return JsonResponse({
        'status': result.status,        # PENDING | STARTED | SUCCESS | FAILURE
        'result': result.result if result.successful() else None,
        'error': str(result.result) if result.failed() else None,
    })
```

```javascript
// static/js/task_polling.js
function pollTask(taskId, onSuccess, onFailure, intervalMs = 2500) {
    const interval = setInterval(() => {
        fetch(`/api/task-status/${taskId}/`)
            .then(r => r.json())
            .then(data => {
                if (data.status === 'SUCCESS') { clearInterval(interval); onSuccess(data.result); }
                else if (data.status === 'FAILURE') { clearInterval(interval); onFailure(data.error); }
            });
    }, intervalMs);
}
```

### Formularios clave

```python
# apps/analysis/forms.py

class ExperienceEditForm(forms.Form):
    """Form A — Validación humana de ExperienceResponse extraído del pliego."""
    listado_codigos = forms.CharField(
        label="Códigos UNSPSC (separados por coma)",
        widget=forms.Textarea(attrs={'rows': 3}), required=False
    )
    cantidad_codigos = forms.CharField(label="Cantidad de códigos", required=False)
    objeto = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}), required=False)
    cantidad_contratos = forms.CharField(required=False)
    valor = forms.CharField(label="Valor a acreditar (ej: 500 SMMLV, $100.000.000, 100% del presupuesto)", required=False)
    pagina = forms.CharField(required=False)
    seccion = forms.CharField(required=False)
    regla_codigos = forms.ChoiceField(choices=[('ALL','Todos (AND)'), ('AT_LEAST_ONE','Al menos uno (OR)')])
    objeto_exige_relevancia = forms.ChoiceField(choices=[('SI','SI'), ('NO','NO'), ('NO_ESPECIFICADO','No especificado')])

# IndicatorsEditForm: django formset dinámico
#   una fila por indicador: {indicador: CharField readonly, valor: CharField editable}
```

### Tareas Celery

| Task | Función backend | Actualiza |
|------|-----------------|-----------|
| `ingest_pdf_task(session_id)` | `ingest_documents()` | `session.status='pdf_ready'` |
| `load_indicadores_task()` | `load_db("indicadores","rib.xlsx")` | — |
| `load_experiencia_task()` | `load_db("experiencia","experiencia_rup.xlsx")` + `ingest_experience_data()` | — |
| `extract_experience_task(session_id)` | `experience_comparation()` | `session.experience_requirements_json` |
| `extract_indicators_task(session_id)` | `get_indicators(query, k=2)` | `session.indicators_requirements_json` |
| `extract_general_info_task(session_id)` | `get_general_info(query, k=2)` | log/display |
| `evaluate_experience_task(session_id, exp_dict)` | `check_compliance_experience(ExperienceResponse(**exp_dict))` | `AnalysisResult.experience_result_json` |
| `evaluate_indicators_task(session_id, ind_list)` | `merge_indicators()` + `run_llm_indicators_comparation()` | `AnalysisResult.indicators_result_json` |

> **Nota:** Para indicadores editados se usan las funciones de bajo nivel porque `indicators_comparation()` tiene query interna hardcodeada y no acepta parámetros externos.

### Integración del backend en Django

```python
# web/tendermod_web/settings/base.py
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
TENDERMOD_SRC = BASE_DIR.parent / 'src'
if str(TENDERMOD_SRC) not in sys.path:
    sys.path.insert(0, str(TENDERMOD_SRC))

TENDERMOD_DATA_DIR = BASE_DIR.parent / 'data'
TENDERMOD_DB_DIR = BASE_DIR.parent / 'data' / 'redneet_db'

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
```

---

## Plan de Implementación

### Fase 1 — Scaffold + Vista 1 (Ingesta Redneet)
1. Crear `web/` con `django-admin startproject tendermod_web .`
2. Crear apps `core`, `redneet`, `analysis` (`python manage.py startapp`)
3. Escribir `requirements.txt`: `django>=4.2, celery>=5.3, redis>=5.0, python-dotenv, openpyxl`
4. Configurar `settings/base.py` con paths, sys.path, Celery
5. Crear `web/tendermod_web/celery.py`
6. Crear modelos `AnalysisSession`, `AnalysisResult` + migraciones
7. Implementar `redneet/views.py`: dashboard, upload_indicadores, upload_experiencia
8. Implementar `redneet/tasks.py`: load_indicadores_task, load_experiencia_task
9. Crear `core/views.py`: task_status, db_status
10. Crear `templates/base.html` Bootstrap 5 CDN + `redneet/dashboard.html`

**Entregable:** Vista 1 funcional — subir Excels y ver conteo de registros.

### Fase 2 — Paso 1: Subida PDF + Extracción
1. `analysis/views.py`: `analysis_new`, `analysis_step1`, `analysis_extract`
2. `analysis/tasks.py`: `ingest_pdf_task`, `extract_experience_task`, `extract_indicators_task`, `extract_general_info_task`
3. `static/js/task_polling.js`: función genérica de polling AJAX
4. Templates: `analysis/new.html`, `analysis/step1.html` con spinners Bootstrap

**Entregable:** PDF se sube, se ingesta y se extraen requisitos con feedback visual.

### Fase 3 — Paso 2: Validación humana + Evaluación
1. `analysis/forms.py`: `ExperienceEditForm`, `IndicatorsEditForm` (formset dinámico)
2. `analysis/views.py`: `analysis_step2`, `analysis_evaluate`
3. `analysis/tasks.py`: `evaluate_experience_task`, `evaluate_indicators_task`
4. Template `analysis/step2.html` con formularios editables y botones de evaluación

**Entregable:** Usuario edita requisitos extraídos y lanza evaluación completa.

### Fase 4 — Resultados + Exportación
1. `analysis/views.py`: `analysis_results`, `export_excel`, `export_text`
2. Template `analysis/results.html`: tablas con badges Cumple/No cumple
3. Exportación Excel con `openpyxl` (2 hojas: "Indicadores", "Experiencia RUP")
4. Exportación texto plano con resumen ejecutivo
5. `analysis/list.html`: historial de sesiones

**Entregable:** MVP completo funcional end-to-end.

---

## Funciones backend a reutilizar (sin modificar)

| Función | Archivo |
|---------|---------|
| `ingest_documents()` | `src/tendermod/ingestion/ingestion_flow.py` |
| `ingest_experience_data()` | `src/tendermod/ingestion/ingestion_experience_flow.py` |
| `load_db(tab_name, file_name)` | `src/tendermod/data_sources/redneet_db/xls_loader.py` |
| `experience_comparation()` | `src/tendermod/evaluation/compare_experience.py` |
| `check_compliance_experience(exp)` | `src/tendermod/evaluation/compare_experience.py` |
| `get_indicators(query, k)` | `src/tendermod/evaluation/indicators_inference.py` |
| `get_general_info(query, k)` | `src/tendermod/evaluation/indicators_inference.py` |
| `merge_indicators(tender, gold)` | `src/tendermod/evaluation/compare_indicators.py` |
| `run_llm_indicators_comparation(merged, info)` | `src/tendermod/evaluation/llm_client.py` |

---

## Verificación

```bash
# Instalar dependencias
cd web && pip install -r requirements.txt

# Redis (requerido para Celery)
redis-server &

# Migraciones Django
python manage.py migrate

# Worker Celery
celery -A tendermod_web worker --loglevel=info &

# Servidor Django
python manage.py runserver
```

**Flujo de prueba end-to-end:**
1. `/redneet/` — Subir `rib.xlsx` y `experiencia_rup.xlsx` → verificar conteo de registros
2. `/analysis/new/` — Subir PDF del pliego ANE → esperar spinner de ingestión
3. `/analysis/1/step1/` — Click "Buscar requisitos Experiencia" → esperar spinner
4. `/analysis/1/step2/` — Verificar Form A pre-poblado con `ExperienceResponse` correcto
5. Click "Evaluar Experiencia" → esperar spinner
6. `/analysis/1/results/` — Verificar `valor_requerido_cop = $373,534,215` y CUMPLE
7. Descargar Excel → verificar hojas "Indicadores" y "Experiencia RUP"
8. Descargar TXT → verificar resumen ejecutivo legible
