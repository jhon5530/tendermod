# Spec 11 — Módulo "Evaluación Equipo"

## Objetivo

Agregar la capacidad de ingestar datos del equipo de trabajo
(`CERTIFICACIONES_PERSONAL.xlsx`) y consultar esos datos en lenguaje natural mediante un
SQL Agent (LangChain + GPT-4o-mini), integrado a la interfaz web existente.

---

## Excel de entrada

**Archivo:** `CERTIFICACIONES_PERSONAL.xlsx`

| Hoja | Tabla SQLite | Columnas |
|------|-------------|----------|
| `Personas` | `personas` | Persona, Cargo |
| `Certificaciones` | `certificaciones` | Persona, Cargo, Categoria, Certificacion, Descripcion, Fecha_Expedicion, Fecha_Expiracion, Vencimiento |

- 30 personas, 350 certificaciones (~11,7 cert/persona)

---

## Decisiones de arquitectura

| Decisión | Elección | Razón |
|----------|----------|-------|
| Almacenamiento | Misma SQLite (`redneet_database.db`) | Sin nueva infraestructura |
| Búsqueda | SQL Agent (sin ChromaDB) | Datos tabulares estructurados; SQL > RAG vectorial para conteos y filtros |
| SQL Agent scope | `include_tables=["personas","certificaciones"]` | Evita ruido con `indicadores` y `experiencia` |
| Q&A web | Endpoint síncrono (como `analysis_pliego_qa`) | Simple; SQL Agent responde en ~10 s |
| Carga Excel | Celery task (patrón Redneet) | Consistencia con `rib.xlsx` / `experiencia_rup.xlsx` |

---

## Archivos creados / modificados

### Backend

| Archivo | Acción |
|---------|--------|
| `src/tendermod/data_sources/redneet_db/team_loader.py` | NUEVO — `load_team_db()` |
| `src/tendermod/data_sources/redneet_db/sql_agent.py` | MODIFICADO — añade `build_team_sql_agent()` |
| `src/tendermod/evaluation/team_inference.py` | NUEVO — `ask_team()` |

### Web

| Archivo | Acción |
|---------|--------|
| `web/apps/redneet/forms.py` | MODIFICADO — añade `EquipoUploadForm` |
| `web/apps/redneet/tasks.py` | MODIFICADO — añade `load_team_task` |
| `web/apps/redneet/views.py` | MODIFICADO — añade `upload_equipo`, actualiza `dashboard` |
| `web/apps/redneet/urls.py` | MODIFICADO — añade `upload-equipo/` |
| `web/apps/core/views.py` | MODIFICADO — `db_status` incluye conteo `personas` y `certificaciones` |
| `web/apps/analysis/views.py` | MODIFICADO — añade `team_qa`, `team_qa_query` |
| `web/apps/analysis/urls.py` | MODIFICADO — añade `team/` y `team/query/` |
| `web/templates/analysis/team_qa.html` | NUEVO — interfaz de chat Q&A |
| `web/templates/redneet/dashboard.html` | MODIFICADO — card de carga de equipo |
| `web/templates/base.html` | MODIFICADO — link "Evaluacion Equipo" en sidebar |

---

## Flujo completo

```
Usuario carga CERTIFICACIONES_PERSONAL.xlsx → /redneet/upload-equipo/
    → Django view copia a TENDERMOD_DB_DIR/certificaciones_personal.xlsx
    → load_team_task (Celery) → team_loader.load_team_db()
        → SQLite: tabla personas (30 filas) + tabla certificaciones (350 filas)

Usuario navega a /analysis/team/
    → Escribe pregunta en lenguaje natural
    → POST /analysis/team/query/ → team_qa_query view
        → ask_team(question) → build_team_sql_agent().invoke(question)
            → GPT-4o-mini genera SQL → consulta SQLite → respuesta
    → Respuesta aparece en historial del chat
```

---

## Verificación

1. Subir `CERTIFICACIONES_PERSONAL.xlsx` desde `/redneet/` → confirmar conteos en las
   cards de status (personas: 30, certificaciones: 350).
2. Navegar a `/analysis/team/` → preguntar
   "¿Cuántas personas tienen certificación Cisco CCNA?" → confirmar respuesta coherente.
3. Verificar preguntas adicionales:
   - "¿Quiénes tienen el cargo de Project Manager?"
   - "Lista las certificaciones con vencimiento en 2025"
   - "¿Cuántas personas hay con certificaciones de seguridad?"
4. Verificar que `/analysis/`, `/redneet/` y demás flujos siguen funcionando sin cambios.

---

## Estado de implementación

- [x] `team_loader.py` — creado
- [x] `sql_agent.py` — `build_team_sql_agent()` agregado
- [x] `team_inference.py` — creado
- [x] `forms.py` (redneet) — `EquipoUploadForm` agregado
- [x] `tasks.py` (redneet) — `load_team_task` agregado
- [x] `views.py` (redneet) — `upload_equipo` + dashboard actualizado
- [x] `urls.py` (redneet) — URL agregada
- [x] `core/views.py` — `db_status` actualizado
- [x] `views.py` (analysis) — `team_qa` + `team_qa_query` agregados
- [x] `urls.py` (analysis) — URLs agregadas
- [x] `team_qa.html` — creado
- [x] `dashboard.html` (redneet) — card de equipo agregada
- [x] `base.html` — link en sidebar agregado
