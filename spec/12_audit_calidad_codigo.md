# Spec 12 — Audit de Calidad de Código

## Contexto

Tras múltiples iteraciones de desarrollo (specs 01-11), se realizó un audit exhaustivo del codebase
para identificar bugs silenciosos, código duplicado, inconsistencias y deuda técnica acumulada.
El audit cubrió backend (`src/tendermod/`), web Django (`web/apps/`) y templates.

---

## Hallazgos críticos — bugs reales

### C1 · `exp_data.pop('umbral')` corrompe el dict antes de pasarlo a Celery
**Archivo:** `web/apps/analysis/views.py:242`

`umbral` se extrae con `.pop()`, removiéndolo del dict `exp_data` que luego se pasa a
`evaluate_experience_task.delay(exp_data)`. El objeto `ExperienceResponse` reconstruido
dentro de la tarea llega sin el campo `umbral`.

**Fix:** Cambiar `.pop()` por `.get()`:
```python
# ANTES
umbral = float(exp_data.pop('umbral', body.get('umbral', ...)))
# DESPUÉS
umbral = float(body.get('umbral', exp_data.get('umbral', SystemConfig.get_solo().threshold_objeto)))
```

### C2 · Typo `create_vectorstor_from_text` (falta 'e')
**Archivo:** `src/tendermod/retrieval/vectorstore.py:25`

El nombre incorrecto se propaga a `ingestion_experience_flow.py`. Funciona sólo porque ambos
usan el mismo typo, pero rompe si alguien intenta importar con el nombre correcto.

**Fix:** Renombrar a `create_vectorstore_from_text` en ambos archivos.

### C3 · `team_qa_query` sin try/except en JSON parsing
**Archivo:** `web/apps/analysis/views.py:988`

`json.loads(request.body)` lanza `json.JSONDecodeError` no capturado → HTTP 500.

**Fix:**
```python
try:
    body = json.loads(request.body)
except json.JSONDecodeError:
    return JsonResponse({'error': 'Body JSON inválido'}, status=400)
```

---

## Hallazgos altos — deuda técnica con impacto en mantenimiento

### A1 · `_get_pdf_path()` definida idénticamente en 3 archivos
**Archivos:**
- `src/tendermod/evaluation/indicators_inference.py:24`
- `src/tendermod/evaluation/experience_inference.py:23`
- `src/tendermod/evaluation/general_requirements_inference.py:52`

**Fix:** Extraer a `src/tendermod/evaluation/utils.py` y reemplazar las 3 definiciones por import.

```python
# evaluation/utils.py
from pathlib import Path
from tendermod.config.settings import CHROMA_PERSIST_DIR

def get_pdf_path() -> str:
    data_dir = Path(CHROMA_PERSIST_DIR).parent
    pdfs = list(data_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No se encontró PDF en {data_dir}")
    return str(pdfs[0])
```

### A2 · Lógica de evaluación de indicadores duplicada (~50 líneas)
**Archivo:** `web/apps/analysis/tasks.py:264-315` y `450-498`

`evaluate_indicators_task()` y `quick_evaluate_indicators_task()` repiten idénticamente:
- construcción de `tender_indicators_json`
- query a `get_specific_gold_indicator()`
- llamada a `get_general_info()` para presupuesto
- construcción de `indicadores_detalle`

**Fix:** Extraer función helper `_build_indicators_detalle(ind_list)` y llamarla desde ambas tareas.

### A3 · `download_pdf()` sin decorador `@require_GET`
**Archivo:** `web/apps/analysis/views.py:949`

`download_ocr()` (línea 931) sí tiene `@require_GET`. `download_pdf()` no.

**Fix:** Agregar `@require_GET` en línea 949.

### A4 · Task IDs de Redneet nunca se limpian de la sesión
**Archivo:** `web/apps/redneet/views.py:59, 91, 123`

`task_id_indicadores`, `task_id_experiencia`, `task_id_equipo` se guardan en sesión al lanzar
la tarea pero nunca se eliminan. El dashboard siempre mostrará los task IDs de la última tarea,
aunque ya haya terminado.

**Fix:** En el JavaScript de `dashboard.html`, limpiar el task ID de sesión al completar el polling
via un endpoint `POST /redneet/clear-task-id/`, o simplemente no persistir en sesión (usar
localStorage en el cliente).

### A5 · Mezcla `os.path` vs `pathlib.Path` en `data_sources/`
**Archivos:**
- `data_sources/redneet_db/xls_loader.py` — usa `os.path.join()`
- `data_sources/redneet_db/sql_agent.py:16` — usa `os.path.join()`
- `data_sources/redneet_db/team_query_builder.py:73` — usa `os.path.join()`

**Fix:** Reemplazar todos los `os.path.join(REDNEET_DB_PERSIST_DIR, ...)` por
`Path(REDNEET_DB_PERSIST_DIR) / ...` para consistencia con el resto del codebase.

### A6 · Función CSRF duplicada en 4 templates con versión rota en `team_qa.html`
**Archivos:**
- `templates/analysis/quick.html:170` — `getCSRF()`
- `templates/redneet/dashboard.html:289` — `getCsrfToken()`
- `templates/analysis/team_qa.html:131` — `getCsrfToken()` sin fallback a cookie ← ROTO
- `templates/analysis/step2.html:481` — `getCsrfToken()`

**Fix:** Agregar la función una sola vez en `static/js/task_polling.js` con nombre canónico
`getCsrfToken()` y fallback a cookie. Eliminar las definiciones locales de los 4 templates.

---

## Hallazgos medios — limpieza

| ID | Problema | Archivo | Acción |
|----|----------|---------|--------|
| M1 | Handler POST vacío (`pass`) en `analysis_step2()` | `web/apps/analysis/views.py:177` | Eliminar bloque `if request.method == 'POST': pass` |
| M2 | `import shutil` sin usar | `web/apps/analysis/views.py:5` | Eliminar |
| M3 | `import json` dentro de `merge_indicators()` (ya importado al tope) | `src/tendermod/evaluation/compare_indicators.py:60` | Eliminar importaciones internas |
| M4 | Código comentado y ejemplo `u2ser_input` | `src/tendermod/evaluation/compare_indicators.py:241-251` | Eliminar |
| M5 | `print()` mezclado con `logging` en evaluation/ | Múltiples archivos en `evaluation/` | Reemplazar prints con `logger.debug()` |
| M6 | URLs hardcodeadas en `static/js/task_polling.js` | `task_polling.js:15, 108, 151` | Aceptable por ahora — no hay reverse lookup en JS estático |

---

## Orden de ejecución recomendado

### Bloque 1 — Críticos (riesgo de bug en producción)
1. Fix C1: `.pop()` → `.get()` en views.py:242
2. Fix C2: renombrar `create_vectorstor_from_text` → `create_vectorstore_from_text`
3. Fix C3: try/except en `team_qa_query` views.py:988

### Bloque 2 — Altos (refactors sin cambio de comportamiento)
4. Fix A1: extraer `get_pdf_path()` a `evaluation/utils.py`
5. Fix A2: extraer `_build_indicators_detalle()` helper en tasks.py
6. Fix A3: agregar `@require_GET` a `download_pdf()`
7. Fix A5: estandarizar `pathlib.Path` en data_sources/

### Bloque 3 — Medios (limpieza)
8. Fix A6: unificar función CSRF en task_polling.js
9. Fix M1-M4: eliminar dead code e imports no usados
10. Fix M5: reemplazar print() con logging en evaluation/

---

## Verificación

Después de cada bloque:
- Levantar Django + Celery y correr una evaluación completa de extremo a extremo
- Verificar que los exports Excel y TXT siguen funcionando
- Verificar que `/redneet/`, `/analysis/` y `/analysis/team/` cargan sin errores
