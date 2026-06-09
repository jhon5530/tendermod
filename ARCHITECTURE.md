# ARCHITECTURE.md — Arquitectura y flujo de evaluación de tendermod

## Stack tecnológico

- **Django** — interfaz web, vistas, formularios
- **Celery** (`--pool=solo`) + **Redis** — ejecución asíncrona de tareas pesadas
- **tendermod backend** (Python/LangChain/OpenAI/ChromaDB/SQLite) — lógica de RAG y evaluación

---

## Modelos principales (`web/apps/core/models.py`)

| Modelo | Propósito |
|---|---|
| `AnalysisSession` | Una sesión por evaluación. Almacena JSONs intermedios y el estado del proceso |
| `AnalysisResult` | Resultado final ligado 1-a-1 con la sesión. Guarda `cumple_final` y JSONs de resultado |
| `SystemConfig` | Configuración global (umbral de similitud para objeto del contrato, etc.) |

**Campos clave de `AnalysisSession`:**
- `status` — estado del proceso (created → ingesting_pdf → pdf_ready → evaluating → completed / error)
- `indicators_requirements_json` — MultipleIndicatorResponse extraído del pliego
- `experience_requirements_json` — ExperienceResponse extraído del pliego
- `general_info_text` — texto libre con presupuesto, objeto y número del proceso
- `general_requirements_json` — GeneralRequirementList (checklist completo del pliego)
- `team_profiles_json` — ProfileRequirementList con perfiles de equipo requeridos
- `ocr_document_path` — ruta al .docx generado si se aplicó OCR

**Campos clave de `AnalysisResult`:**
- `cumple_indicadores`, `cumple_experiencia`, `cumple_equipo`, `cumple_final`
- `indicators_result_json` — IndicatorComplianceResult con detalle por indicador
- `experience_result_json` — ExperienceComplianceResult con detalle por RUP
- `team_compliance_json` — TeamProfileComplianceList con evaluación por perfil
- `indicators_context_text`, `experience_context_text` — chunks RAW del retriever (auditoría)

---

## Flujo de evaluación automática (modo AUTO)

El usuario sube un PDF y elige "Auto". La vista `analysis_new` crea la sesión y lanza la primera tarea Celery. El frontend (`auto.html`) orquesta el resto vía polling de tareas.

```
1. [Celery] ingest_pdf_task
     PDF → PyMuPDF (+ OCR si aplica) → ChromaDB licitación
     session.status: created → ingesting_pdf → pdf_ready

2. [Celery — 5 tareas de extracción, lanzadas en paralelo]
     ├── extract_indicators_task
     │     RAG sobre ChromaDB → GPT-4o-mini → MultipleIndicatorResponse
     │     Guarda: session.indicators_requirements_json
     │
     ├── extract_experience_task
     │     RAG sobre ChromaDB → GPT-4o-mini → ExperienceResponse
     │     Guarda: session.experience_requirements_json
     │
     ├── extract_general_info_task
     │     RAG sobre ChromaDB → texto libre (presupuesto, objeto, número proceso)
     │     Guarda: session.general_info_text
     │
     ├── extract_general_requirements_task
     │     Por capítulos completos (sin RAG) → bloques ≤20K chars → LLM en paralelo
     │     → GeneralRequirementList (habilitantes, puntuables, documentales, etc.)
     │     Guarda: session.general_requirements_json
     │
     └── extract_team_profiles_task
           RAG sobre ChromaDB → GPT-4o-mini → ProfileRequirementList
           Guarda: session.team_profiles_json

3. [Celery — 3 tareas de evaluación, lanzadas en paralelo]
     ├── evaluate_indicators_task(ind_list)
     │     merge_indicators() → empareja pliego vs. SQLite (SQL Agent)
     │     _parse_budget_from_text() → resuelve umbrales POE-relativos ("15% del POE")
     │     run_llm_indicators_comparation() → veredicto + detalle por indicador
     │     Guarda: result.indicators_result_json, result.cumple_indicadores
     │
     ├── evaluate_experience_task(exp_dict)
     │     check_compliance_experience() → SQLite directo por UNSPSC
     │     + ChromaDB experiencia (similitud semántica objeto, umbral configurable)
     │     Guarda: result.experience_result_json, result.cumple_experiencia
     │
     └── evaluate_team_profiles_task()
           evaluate_team_profiles() → SQLite equipo vs. perfiles extraídos del pliego
           Guarda: result.team_compliance_json, result.cumple_equipo

4. cumple_final = cumple_indicadores AND cumple_experiencia
   (cumple_equipo se guarda aparte, no entra en cumple_final aún)
```

---

## Modo manual (paso a paso)

Igual que el auto pero con intervención humana entre extracción y evaluación:

- **Paso 1** — El usuario lanza las tareas de extracción individualmente desde la UI.
- **Paso 2** — El usuario revisa y edita los JSONs extraídos (indicadores, experiencia, perfiles) antes de lanzar la evaluación. Útil cuando el LLM extrajo mal algún indicador o código UNSPSC.

---

## Modo rápido (sin PDF)

El usuario pega texto libre con los requisitos. El LLM extrae `MultipleIndicatorResponse` o `ExperienceResponse` del texto y ejecuta directamente el paso 3 (evaluación), saltándose la ingesta y extracción RAG.

Tareas involucradas: `quick_evaluate_indicators_task`, `quick_evaluate_experience_task`.

---

## Tareas Celery (`web/apps/analysis/tasks.py`)

| Tarea | Fase | Descripción |
|---|---|---|
| `ingest_pdf_task` | Ingesta | PDF → ChromaDB licitación |
| `extract_indicators_task` | Extracción | RAG → indicadores del pliego |
| `extract_experience_task` | Extracción | RAG → requisitos de experiencia |
| `extract_general_info_task` | Extracción | RAG → presupuesto/objeto/número |
| `extract_general_requirements_task` | Extracción | Capítulos → checklist general |
| `extract_team_profiles_task` | Extracción | RAG → perfiles de equipo |
| `evaluate_indicators_task` | Evaluación | Empareja pliego vs. SQLite → LLM |
| `evaluate_experience_task` | Evaluación | UNSPSC + similitud semántica |
| `evaluate_team_profiles_task` | Evaluación | Perfiles vs. equipo en SQLite |
| `quick_evaluate_indicators_task` | Rápido | Texto libre → indicadores → evaluación |
| `quick_evaluate_experience_task` | Rápido | Texto libre → experiencia → evaluación |

---

## Lógica del backend (`src/tendermod/`)

### Evaluación de indicadores (`compare_indicators.py`)

1. `merge_indicators(tender_json, gold_json, presupuesto)` — empareja cada indicador del pliego con su valor en SQLite. Parsea condición y umbral con regex que maneja variantes del español.
2. `_parse_budget_from_text(text)` — extrae el POE del texto general_info (patrón `$X.XXX.XXX.XXX`).
3. `_compute_cumple(valor_empresa, condicion, umbral)` — cálculo determinístico de cumplimiento. Retorna `None` si algún valor es `None`.
4. `run_llm_indicators_comparation(emparejados, general_info)` — LLM produce argumentación textual + veredicto final.

### Evaluación de experiencia (`compare_experience.py`)

1. `check_compliance_experience(exp_response, similarity_threshold)` — dispatcher que elige modo GLOBAL o MULTI_CONDICION según el pliego.
2. Modo **GLOBAL**: normaliza códigos UNSPSC a prefijo de 6 dígitos → SQL directo → filtra por similitud semántica del objeto (ChromaDB experiencia).
3. Modo **MULTI_CONDICION**: evalúa cada sub-requisito por separado (cada uno puede tener sus propios códigos, valor mínimo y objeto).

### Extracción de requisitos generales (`general_requirements_inference.py`)

- Detecta capítulos via TOC nativo → complementa con detección visual tipográfica si cobertura < 95%.
- Fusiona capítulos en bloques ≤ 20K chars → llama LLM en paralelo por bloque.
- Cada componente con puntaje propio (dentro de tabla/lista) se extrae como ítem PUNTUABLE independiente.

---

## Outputs disponibles

| Formato | Contenido |
|---|---|
| Página de resultados | Veredicto por dimensión con detalle LLM |
| Excel (`.xlsx`) | 4 hojas: Indicadores / Experiencia RUP / Checklist General / Equipo de Trabajo |
| TXT | Resumen ejecutivo con detalle por RUP |
| Contexto RAG (`.txt`) | Chunks exactos que alimentaron al LLM (para auditoría) |
| OCR Word (`.docx`) | Documento generado por OCR si el PDF era imagen |

---

## Vistas Django (`web/apps/analysis/views.py`)

| Vista | Ruta | Descripción |
|---|---|---|
| `analysis_list` | `/` | Historial de sesiones |
| `analysis_new` | `/new/` | Subida de PDF, creación de sesión |
| `analysis_step1` | `/<pk>/step1/` | Extracción manual (Paso 1) |
| `analysis_extract` | `/<pk>/extract/` | AJAX: lanza tarea de extracción |
| `analysis_step2` | `/<pk>/step2/` | Revisión y evaluación manual (Paso 2) |
| `analysis_evaluate` | `/<pk>/evaluate/` | AJAX: lanza tarea de evaluación |
| `analysis_auto` | `/<pk>/auto/` | Evaluación automática con barra de progreso |
| `analysis_results` | `/<pk>/results/` | Página de resultados |
| `analysis_quick` | `/quick/` | Evaluación rápida sin PDF |
| `analysis_pliego_qa` | `/<pk>/pliego-qa/` | Q&A sobre el pliego via RAG |
| `analysis_checklist_save` | `/<pk>/checklist/save/` | AJAX: guarda estados del checklist |
| `team_qa` | `/team-qa/` | Chat en lenguaje natural contra SQLite equipo |
| `export_excel` | `/<pk>/export/excel/` | Descarga Excel |
| `export_text` | `/<pk>/export/txt/` | Descarga TXT |
| `export_context` | `/<pk>/export/context/` | Descarga contexto RAG |
