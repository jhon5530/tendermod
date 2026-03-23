---
name: tendermod backend state
description: Estado real del backend Python de tendermod — firmas, schemas y TODOs confirmados por lectura directa del código
type: project
---

## Stack confirmado
- Python 3.12 + Poetry (pyproject.toml)
- LangChain + OpenAI (gpt-4o-mini, text-embedding-3-small)
- ChromaDB persistente en data/chroma y data/chroma_experience
- SQLite en data/redneet_db/redneet_database.db
- Pydantic v2 (model_validate_json, ConfigDict)

## Funciones públicas y firmas exactas (verificadas 2026-03-22)

### ingestion_flow.py
- `ingest_documents() -> Chroma` — PDF → chunks → ChromaDB licitacion. Destructivo (elimina DB previa).

### ingestion_experience_flow.py
- `ingest_experience_data() -> Chroma` — SQLite experiencia → ChromaDB colección "rup".

### data_sources/redneet_db/xls_loader.py
- `load_db(tab_name: str, file_name: str) -> None` — Lee Excel desde REDNEET_DB_PERSIST_DIR, carga tabla SQLite (replace).

### evaluation/indicators_inference.py
- `get_indicators(user_input: str, k: int) -> Optional[MultipleIndicatorResponse]` — RAG sobre ChromaDB licitacion.
- `get_general_info(user_input: str, k: int) -> str` — RAG libre, retorna string (no Pydantic).

### evaluation/experience_inference.py
- `get_experience(user_input: str, k: int) -> Optional[ExperienceResponse]`

### evaluation/compare_indicators.py
- `indicators_comparation() -> Optional[IndicatorComplianceResult]`

### evaluation/compare_experience.py
- `experience_comparation() -> Optional[ExperienceResponse]` — Extrae requisitos del pliego.
- `check_compliance_experience(tender_experience: ExperienceResponse) -> ExperienceComplianceResult`

## Schemas Pydantic (evaluation/schemas.py)
- `Indicator`: {indicador: str, valor: Union[str, float]}
- `MultipleIndicatorResponse`: {answer: List[Indicator]}
- `ExperienceResponse`: listado_codigos, cantidad_codigos, objeto, cantidad_contratos, valor, pagina, seccion, regla_codigos, objeto_exige_relevancia
- `IndicatorComplianceResult`: cumple (Optional[bool]), detalle (str), indicadores_evaluados, indicadores_faltantes
- `RupExperienceResult`: numero_rup, cliente, valor_cop, cumple_codigos, cumple_valor, cumple_objeto, score_objeto, cumple_total
- `ExperienceComplianceResult`: codigos_requeridos, valor_requerido_cop, objeto_requerido, rups_evaluados, rups_candidatos_codigos, cantidad_contratos_requerida, rups_cumplen, total_valor_cop, rups_excluidos_por_objeto, objeto_exige_relevancia, cumple

## TODOs y bugs conocidos
- `settings.py` tenía bug en CHROMA_EXPERIENCE_PERSIST_DIR (ya corregido en código actual — lee env var correcta).
- `main.py` tiene el veredicto final comentado (líneas 69-73) — no hay bug funcional, solo código en desarrollo.
- `get_indicators()` en indicators_inference.py re-carga docs y los re-chunkea en cada llamada (costo extra).
- `get_experience()` también re-carga docs (mismo patrón — optimizable en future).
- No existe función `evaluate_indicators_compliance` — el comentario en CLAUDE.md es legacy, no hay código roto.

## Configuración (.env confirmada)
- CHROMA_PERSIST_DIR (licitacion)
- CHROMA_EXPERIENCE_PERSIST_DIR (experiencia empresa)
- REDNEET_DB_PERSIST_DIR (SQLite + Excels)
- OPENAI_API_KEY

**Why:** Lectura directa de código fuente 2026-03-22 para diseñar MVP Django.
**How to apply:** Usar estas firmas exactas al generar código Django que llame al backend.
