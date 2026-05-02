# CLAUDE.md — Contexto del proyecto tendermod

## Proposito del sistema

**tendermod** es un sistema RAG (Retrieval-Augmented Generation) para evaluar si una empresa (proponente) cumple con los requisitos de una licitacion publica colombiana. Compara dos dimensiones:

1. **Indicadores financieros**: requisitos del pliego de condiciones (PDF) vs. indicadores reales de la empresa (SQLite).
2. **Experiencia**: requisitos del pliego (PDF) vs. experiencia registrada de la empresa en el RUP (SQLite).

El dominio es contratacion publica colombiana — los terminos clave son: licitacion, pliego de condiciones, proponente, RUP (Registro Unico de Proponentes), UNSPSC (codigos de clasificacion de bienes/servicios), SMMLV.

“When compacting, always preserve: the list of modified files, current test status, and any unresolved issues.”

---

## Stack tecnologico

- **Python 3.12** — manejado con Poetry
- **LangChain** (community, core, chroma, openai, text-splitters)
- **OpenAI** — modelo `gpt-4o-mini` para LLM, `text-embedding-3-small` para embeddings
- **ChromaDB** — vector store persistente
- **SQLite** — base de datos local de la empresa (indicadores + experiencia)
- **PyMuPDF** — carga de PDFs
- **Pandas / openpyxl** — carga de Excel a SQLite
- **Pydantic** — schemas de respuesta estructurada

Comandos utiles:
```bash
# Activar entorno
source .venv/bin/activate

# Ejecutar el sistema
python -m tendermod.main

# Instalar dependencias
poetry install
```

---

## Estructura de directorios

```
tendermod/
├── CLAUDE.md
├── pyproject.toml
├── .env                        # OPENAI_API_KEY, CHROMA_PERSIST_DIR, REDNEET_DB_PERSIST_DIR
├── data/
│   ├── *.pdf                   # PDFs de licitaciones (cargados por pdf_loader)
│   ├── chroma/                 # ChromaDB: chunks del PDF de licitacion
│   ├── chroma_experience/      # ChromaDB: experiencia de la empresa desde SQLite
│   └── redneet_db/
│       ├── redneet_database.db # SQLite: tablas "indicadores" y "experiencia"
│       ├── rib.xlsx            # Excel fuente de indicadores financieros
│       └── experiencia_rup.xlsx # Excel fuente de experiencia RUP
└── src/tendermod/
    ├── main.py                 # Punto de entrada y orquestador
    ├── config/
    │   └── settings.py         # Variables de entorno y paths
    ├── ingestion/
    │   ├── pdf_loader.py       # Carga PDFs desde data/*.pdf
    │   ├── chunking.py         # Divide docs en chunks (512 tokens, cl100k_base)
    │   ├── db_loader.py        # Invoca SQL Agent para consultar SQLite
    │   ├── experience_db_loader.py  # SQLite "experiencia" -> LangChain Documents
    │   ├── ingestion_flow.py        # Pipeline: PDF -> chunks -> ChromaDB licitacion
    │   └── ingestion_experience_flow.py  # Pipeline: SQLite -> ChromaDB experiencia
    ├── retrieval/
    │   ├── embeddings.py       # OpenAIEmbeddings (text-embedding-3-small)
    │   ├── vectorstore.py      # CRUD ChromaDB (create, read, delete)
    │   ├── retriever.py        # Retrievers MMR (indicadores) y similarity (experiencia)
    │   └── context_builder.py  # Ensambla contexto ampliado (wide_context) para LLM
    ├── data_sources/
    │   └── redneet_db/
    │       ├── xls_loader.py   # Carga Excel -> SQLite (load_db)
    │       └── sql_agent.py    # LangChain SQL Agent sobre SQLite
    └── evaluation/
        ├── schemas.py          # Pydantic: Indicator, MultipleIndicatorResponse, ExperienceResponse
        ├── prompts.py          # Todos los system/user prompts del sistema
        ├── llm_client.py       # Llamadas a OpenAI (run_llm_indices, run_llm_indicators_comparation)
        ├── indicators_inference.py   # RAG sobre PDF -> extrae indicadores -> MultipleIndicatorResponse
        ├── experience_inference.py   # RAG sobre PDF -> extrae requisitos experiencia -> ExperienceResponse
        ├── compare_indicators.py     # Orquesta comparacion de indicadores completa
        └── compare_experience.py     # Valida cumplimiento de experiencia (codigos UNSPSC via SQL)
```

---

## Flujos principales

### Flujo 1: Comparacion de indicadores financieros

```
PDF licitacion -> RAG (ChromaDB licitacion) -> GPT-4o-mini
    -> MultipleIndicatorResponse (Pydantic)
        -> SQL Agent -> SQLite tabla "indicadores"
            -> GPT-4o-mini (comparacion)
                -> "Cumple" / "No cumple" con argumentacion
```

Funcion de entrada: `compare_indicators.indicators_comparation()`

### Flujo 2: Validacion de experiencia

**Sub-flujo 2a — Extraccion de requisitos del pliego (RAG):**
```
PDF licitacion -> RAG (ChromaDB licitacion) -> GPT-4o-mini
    -> ExperienceResponse (codigos UNSPSC, valor, objeto, cantidad contratos)
```
Funcion: `experience_inference.get_experience()`

**Sub-flujo 2b — Verificacion directa contra SQLite (activo):**
```
Lista de codigos UNSPSC -> SQL directo a SQLite tabla "experiencia"
    -> lista de NUMERO RUP que cumplen los codigos minimos
```
Funcion: `compare_experience.check_compliance_experience()` -> `check_code_compliance()`

**Sub-flujo 2c — RAG sobre experiencia de la empresa:**
```
SQLite "experiencia" -> LangChain Documents -> ChromaDB experiencia
    -> similarity_search por objeto/descripcion
```
Funcion: `ingestion_experience_flow.ingest_experience_data()`

---

## Configuracion (.env)

```
OPENAI_API_KEY=sk-...
CHROMA_PERSIST_DIR=./data/chroma
CHROMA_EXPERIENCE_PERSIST_DIR=./data/chroma_experience
REDNEET_DB_PERSIST_DIR=./data/redneet_db
ENV=local
```

> **Atencion**: En `settings.py` hay un bug — `CHROMA_EXPERIENCE_PERSIST_DIR` lee la misma env var que `CHROMA_PERSIST_DIR`. Si se necesitan separadas, hay que corregir la key en el `.env` y en `settings.py`.

---

## Detalles tecnicos importantes

### Chunking (ingestion/chunking.py)
- Encoder: `cl100k_base` (tiktoken)
- Chunk size: 512 tokens
- Cada chunk tiene `metadata["chunk_id"]` = indice secuencial
- `wide_context()`: expande el contexto recuperado incluyendo chunks adyacentes (-2 a +3)

### Retrievers (retrieval/retriever.py)
- **Indicadores**: MMR (`search_type="mmr"`, k variable, fetch_k=15, lambda_mult=0.6)
- **Experiencia (PDF)**: Similarity (`search_type="similarity"`, k variable)

### ChromaDB (retrieval/vectorstore.py)
- `create_vectorstore()`: elimina la DB existente antes de crear (destructivo)
- `create_vectorstor_from_text()`: coleccion `"rup"`, IDs = `numero_rup`
- `read_vectorstore()`: lee sin borrar (modo consulta)

### SQL Agent (data_sources/redneet_db/sql_agent.py)
- LangChain `create_sql_agent` con `agent_type="openai-tools"`
- `sample_rows_in_table_info=500` — carga muchos ejemplos al contexto del agente
- Tabla `indicadores`: cargada desde `rib.xlsx`
- Tabla `experiencia`: cargada desde `experiencia_rup.xlsx`

### Schemas de respuesta (evaluation/schemas.py)
- `Indicator`: `{indicador: str, valor: Union[str, float]}`
- `MultipleIndicatorResponse`: `{answer: List[Indicator]}`
- `ExperienceResponse`: codigos UNSPSC, cantidad, objeto, contratos, valor, pagina, seccion

### Codigos UNSPSC (compare_experience.py)
- Se normalizan a prefijo de 6 digitos (`normalize_to_prefix6`)
- Validacion por `AND` o score minimo (`min_codigos`) sobre columnas de la tabla `experiencia`
- Resultado: lista de `NUMERO RUP` que cumplen

---

## Estado actual del desarrollo (marzo 2026)

### Implementado y funcionando
- Ingesta de PDF de licitacion a ChromaDB
- Ingesta de Excel (indicadores, experiencia) a SQLite
- Ingesta de experiencia SQLite a ChromaDB
- RAG sobre PDF para extraer indicadores financieros
- RAG sobre PDF para extraer requisitos de experiencia
- Comparacion de indicadores via SQL Agent + LLM
- Validacion de experiencia por codigos UNSPSC contra SQLite
- Validacion de objeto/descripcion por similitud semantica (ChromaDB, umbral 0.75)
- Campo `objeto_contrato` en `RupExperienceResult` para trazabilidad del contrato elegido
- Exportacion TXT con detalle completo por RUP (score, contrato elegido, campos globales)
- Exportacion Excel con columna `Contrato Elegido` en hoja Experiencia RUP
- Interfaz web Django (MVP) en `web/` con evaluacion rapida y resultados

### Pendiente (TODOs identificados en el codigo)
- `compare_experience.py`: validar valor total a acreditar de la experiencia (campo `valor_requerido_cop`)
- `main.py`: la funcion `indicators_routine()` referencia `evaluate_indicators_compliance` que no existe (codigo legacy)
- Mejorar separacion de `CHROMA_PERSIST_DIR` y `CHROMA_EXPERIENCE_PERSIST_DIR` en settings

---

## Convenciones del codigo

- El idioma del codigo/comentarios es mixto (ingles/espanol) — respetar el estilo existente por archivo
- Los prompts del sistema estan todos en `evaluation/prompts.py` — no dispersar prompts en otros archivos
- Los schemas Pydantic van en `evaluation/schemas.py`
- Las llamadas directas a OpenAI van en `evaluation/llm_client.py`
- Para nuevas validaciones de cumplimiento: crear funciones en `compare_*.py`, orquestar desde `main.py`
- Al agregar nuevos flujos de ingesta: seguir el patron de `ingestion_flow.py` o `ingestion_experience_flow.py`
