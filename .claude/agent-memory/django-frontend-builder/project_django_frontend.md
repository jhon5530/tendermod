---
name: django-frontend-architecture
description: Architecture decisions and file layout of the tendermod Django MVP frontend
type: project
---

The Django MVP frontend lives at `/Users/johnvelasco/Documents/APPs/tendermod/web/`.

**Why:** Spec at `spec/04_mvp_django_interfaz_web.md` defines all requirements. Django was chosen for quick scaffolding; Celery+Redis for async LLM calls.

**How to apply:** When extending the frontend, follow the established structure and do NOT modify anything in `src/tendermod/`.

## Django project structure

```
web/
├── manage.py
├── requirements.txt          # django>=4.2, celery>=5.3, redis>=5.0, python-dotenv, openpyxl
├── db.sqlite3                # Django ORM DB (created after migrate)
├── tendermod_web/
│   ├── __init__.py           # imports celery app
│   ├── celery.py             # Celery app config
│   ├── settings/
│   │   ├── base.py           # sys.path injection for tendermod, Celery, paths
│   │   └── local.py
│   ├── urls.py               # root URL config
│   └── wsgi.py
├── apps/
│   ├── core/                 # AnalysisSession + AnalysisResult models, task_status, db_status
│   ├── redneet/              # Excel upload views + Celery tasks
│   └── analysis/             # PDF upload, extraction, evaluation, results, export, quick eval
├── templates/
│   ├── base.html             # Bootstrap 5 CDN, sidebar nav, messages block
│   ├── redneet/dashboard.html
│   └── analysis/
│       ├── new.html          # PDF upload
│       ├── step1.html        # Extraction triggers with AJAX spinners
│       ├── step2.html        # Human validation forms + evaluation
│       ├── results.html      # Tables with CUMPLE/NO CUMPLE badges
│       ├── list.html         # Session history
│       └── quick.html        # Evaluacion Rapida: textarea + AJAX eval without PDF
└── static/js/
    └── task_polling.js       # pollTask(), launchExtraction(), launchEvaluation() helpers
```

## URL patterns (all verified resolving)

| URL | name |
|-----|------|
| /redneet/ | redneet:dashboard |
| /redneet/upload-indicadores/ | redneet:upload_indicadores |
| /redneet/upload-experiencia/ | redneet:upload_experiencia |
| /analysis/ | analysis:list |
| /analysis/new/ | analysis:new |
| /analysis/quick/ | analysis:quick |
| /analysis/quick/evaluate/ | analysis:quick_evaluate |
| /analysis/<pk>/step1/ | analysis:step1 |
| /analysis/<pk>/step1/extract/ | analysis:extract |
| /analysis/<pk>/step2/ | analysis:step2 |
| /analysis/<pk>/step2/evaluate/ | analysis:evaluate |
| /analysis/<pk>/results/ | analysis:results |
| /analysis/<pk>/export/excel/ | analysis:export_excel |
| /analysis/<pk>/export/text/ | analysis:export_text |
| /api/task-status/<task_id>/ | task_status |
| /api/db-status/ | db_status |

## Key integration patterns

- `settings/base.py` injects `../../src` into `sys.path` so `import tendermod.*` works in all contexts (Django requests + Celery workers).
- `.env` is loaded via `load_dotenv(BASE_DIR.parent / '.env')` in `base.py`.
- All backend calls happen inside Celery tasks (`apps/*/tasks.py`), never in the request cycle.
- Files are copied before calling backend functions: PDFs to `TENDERMOD_DATA_DIR/`, Excels to `TENDERMOD_DB_DIR/`.
- Pydantic schemas serialized with `.model_dump_json()` and restored with `Model.model_validate_json()`.
- `indicators_comparation()` is NOT used for evaluation — uses `merge_indicators()` + `run_llm_indicators_comparation()` instead (avoids hardcoded query).

## Celery tasks

| Task | Backend function |
|------|-----------------|
| load_indicadores_task | load_db('indicadores', 'rib.xlsx') |
| load_experiencia_task | load_db('experiencia', 'experiencia_rup.xlsx') + ingest_experience_data() |
| ingest_pdf_task | ingest_documents() |
| extract_experience_task | experience_comparation() |
| extract_indicators_task | get_indicators(query, k=2) |
| extract_general_info_task | get_general_info(query, k=2) |
| evaluate_experience_task | check_compliance_experience(ExperienceResponse) |
| evaluate_indicators_task | merge_indicators() + run_llm_indicators_comparation() |
| quick_evaluate_experience_task | run_llm_quick_experience(text) + check_compliance_experience() |
| quick_evaluate_indicators_task | run_llm_quick_indicators(text) + merge_indicators() + run_llm_indicators_comparation() |

## New LLM client functions (src/tendermod/evaluation/llm_client.py)

- `run_llm_quick_experience(text)` — uses ChatOpenAI.with_structured_output(ExperienceResponse), prompts from QUICK_EXPERIENCE_*
- `run_llm_quick_indicators(text)` — uses ChatOpenAI.with_structured_output(MultipleIndicatorResponse), prompts from QUICK_INDICATORS_*
- Both prompts are defined in `evaluation/prompts.py` as module-level constant (system) + callable (user).

## Evaluacion Rapida integration pattern

- `analysis_quick` (GET): renders quick.html, passes `quick_session_id` from Django session.
- `analysis_quick_evaluate` (POST JSON): action=experience|indicators|reset. Creates AnalysisSession with pdf_filename='[Evaluacion Rapida]', status='pdf_ready'. Stores pk in `request.session['quick_session_id']`.
- The quick session can be reused across multiple evaluations (both exp and ind can be stored in the same AnalysisResult).

## Running

```bash
cd web
# Install deps (use the project venv: ../.venv)
pip install -r requirements.txt

# Migrations
python manage.py migrate

# Redis (required for Celery)
redis-server &

# Celery worker
celery -A tendermod_web worker --loglevel=info &

# Django dev server
python manage.py runserver
```
