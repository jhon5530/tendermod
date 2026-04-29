# Fase 1.2 — Extracción Comprehensiva de Requerimientos

> **Contexto.** El sistema extrae 15 ítems de un pliego AMP (CCENEG-094-01-AMP-2026) donde la
> referencia manual identifica 107. El gap es de 7x. Las causas son estructurales: queries
> hardcodeadas para pliegos FNA, scope limitado a "habilitantes", schema con 6 categorías fijas,
> y ausencia de discovery adaptativo. Este spec diseña la solución completa.
>
> **Archivos clave:**
> - `src/tendermod/evaluation/schemas.py` (línea 110 — `GeneralRequirement`)
> - `src/tendermod/evaluation/prompts.py` (línea 266 — `qna_system_message_general_requirements`)
> - `src/tendermod/evaluation/general_requirements_inference.py` (`HABILITANTES_QUERIES`, `get_general_requirements`)
> - `web/apps/analysis/tasks.py` (`extract_general_requirements_task`)
> - `web/apps/analysis/views.py` (`analysis_step2`, `analysis_checklist_save`, `analysis_pliego_qa`)
> - `web/templates/analysis/step2.html` (checklist por categoría)
> - `web/templates/analysis/results.html` (tabla de checklist general)
>
> **Objetivo:** pasar de 15 a ≥80 ítems en el pliego CCENEG-094-01-AMP-2026 manteniendo
> precisión ≥85%, sin romper sesiones existentes ni el flujo de pliegos FNA ya funcional.

---

## Diagnóstico: gap real por categoría

### Resultados actuales (15 ítems)

| Categoría actual | Ítems | Secciones del pliego AMP cubiertas |
|---|---|---|
| JURIDICO | 8 | Parcial 5.1.x |
| DOCUMENTACION | 2 | Parcial 5.1.x |
| CAPACIDAD | 1 | Parcial 5.4 |
| TECNICO | 3 | Parcial 5.4 |
| FINANCIERO_OTRO | 0 | — (5.2.1 ignorada) |
| OTRO | 1 | — |

### Referencia Claude Cowork (107 ítems)

| Tipo / Categoría | Ítems | Sección pliego AMP | En schema actual |
|---|---|---|---|
| Causal de Rechazo | 22 | 2.23.x | NO EXISTE |
| Experiencia | 18 | 5.3.x | NO (se procesa por separado) |
| Jurídico | 17 | 5.1.x | JURIDICO (parcial) |
| Documental | 13 | 5.1.x | DOCUMENTACION (parcial) |
| Técnico | 9 | 5.4 | TECNICO (parcial) |
| Financiero | 5 | 5.2.1 | FINANCIERO_OTRO (0 capturas) |
| Garantía | 5 | 5.1.9 | NO EXISTE |
| Evaluación-Técnico | 4 | 7.2.x | NO EXISTE |
| Evaluación-Económico | 2 | 7.1, 7.7 | NO EXISTE |
| Evaluación-Industria Nacional | 3 | 7.3.x | NO EXISTE |
| Evaluación-MiPymes/Mujeres | 3 | 7.4–7.6 | NO EXISTE |
| Organizacional | 2 | 5.2.x | FINANCIERO_OTRO (parcial) |
| Diferencial | 2 | 7.4–7.6 | NO EXISTE |
| Otro | 2 | varios | OTRO (parcial) |

### Causas raíz cuantificadas

| Causa | Ítems perdidos (estimado) | Solución |
|---|---|---|
| Queries con terminología 4.1.x FNA — no matchean secciones 2.x/5.x/7.x del AMP | ~50 | Queries dinámicas desde TOC |
| Scope de prompt = solo "habilitantes" | ~35 | Ampliar scope a todos los tipos |
| Schema sin categorías CAUSAL_RECHAZO, GARANTIA, EVALUACION | ~35 | Expandir schema |
| Sin discovery del TOC | ~50 | Pasada 0 (Discovery) |

Las causas se solapan: la misma raíz puede causar múltiples pérdidas. El fix del TOC resuelve el
problema de queries Y parcialmente el de scope, porque la sección determina el tipo.

---

## Resumen ejecutivo de fases

| Fase | Nombre | Ítems recuperados (est.) | Esfuerzo | Tiempo |
|---|---|---|---|---|
| **A** | Expansión del schema (nuevas categorías + campo `tipo`) | 0 directos (habilita B/C) | Bajo | 1–2 h |
| **B** | Nuevos prompts por tipo de requerimiento | +20–30 (tipos nuevos con prompts actuales) | Medio | 3–4 h |
| **C** | Queries dinámicas desde TOC (Discovery Pasada 0) | +30–50 (termina de cubrir AMP) | Medio-alto | 1 día |
| **D** | Extracción multi-pasada por tipo de sección | +10–15 (granularidad y precisión) | Alto | 1–2 días |
| **E** | Compatibilidad Django (vistas + templates + migración) | N/A (funcionalidad UI) | Medio | 0.5 día |

Orden de ejecución: A → B → E → C → D. Las fases A y B son bloqueantes para E; C y D son
mejoras independientes que aumentan el recall.

---

## FASE A — Expansión del schema

> **Por qué primero.** Todas las fases posteriores producen ítems con los nuevos tipos y
> categorías. Si el schema Pydantic rechaza esos valores, el JSON de salida del LLM falla con
> `ValidationError`. La expansión del schema es condición previa a cualquier otro cambio.

### A.1 Nuevas categorías y campo `tipo` en `GeneralRequirement`

**Archivo:** `src/tendermod/evaluation/schemas.py`

**Antes (línea 112):**
```python
class GeneralRequirement(BaseModel):
    id: int
    categoria: Literal["JURIDICO", "TECNICO", "DOCUMENTACION", "CAPACIDAD", "FINANCIERO_OTRO", "OTRO"]
    descripcion: str
    obligatorio: Literal["SI", "NO", "NO_ESPECIFICADO"] = "SI"
    pagina: str = "N/A"
    seccion: str = "N/A"
    estado: Literal["PENDIENTE", "CUMPLE", "NO_CUMPLE", "N/A"] = "PENDIENTE"
    origen: Literal["EXTRACCION", "QA", "MANUAL"] = "EXTRACCION"
```

**Después:**
```python
class GeneralRequirement(BaseModel):
    id: int
    categoria: Literal[
        "JURIDICO",
        "TECNICO",
        "DOCUMENTACION",
        "CAPACIDAD",
        "FINANCIERO_OTRO",
        "GARANTIA",
        "CAUSAL_RECHAZO",
        "EVALUACION",
        "OTRO",
    ]
    tipo: Literal[
        "HABILITANTE",
        "PUNTUABLE",
        "DOCUMENTAL",
        "GARANTIA",
        "CAUSAL_RECHAZO",
        "NO_ESPECIFICADO",
    ] = "NO_ESPECIFICADO"
    descripcion: str
    documento_formato: str = "N/A"      # nombre del formato/formulario exigido
    obligatorio: Literal["SI", "NO", "NO_ESPECIFICADO"] = "SI"
    pagina: str = "N/A"
    seccion: str = "N/A"
    estado: Literal["PENDIENTE", "CUMPLE", "NO_CUMPLE", "N/A"] = "PENDIENTE"
    origen: Literal["EXTRACCION", "QA", "MANUAL"] = "EXTRACCION"
```

**Cambios exactos:**
- `categoria`: añadir `"GARANTIA"`, `"CAUSAL_RECHAZO"`, `"EVALUACION"`. Eliminar ninguna
  categoría existente (retrocompatibilidad).
- `tipo`: campo nuevo con default `"NO_ESPECIFICADO"`. Los ítems de sesiones antiguas
  parseados con `model_validate_json` obtendrán `tipo="NO_ESPECIFICADO"` automáticamente
  gracias al default — retrocompatible sin migración de datos.
- `documento_formato`: campo nuevo con default `"N/A"`. Mismo mecanismo. Reemplaza el
  patrón actual de incluir "FORMATO No. X" en el campo `descripcion`.

**Retrocompatibilidad:** `GeneralRequirementList.model_validate_json(old_json)` no falla porque
los nuevos campos tienen defaults. Los ítems antiguos con `categoria="JURIDICO"` siguen siendo
válidos. No se requiere migración de datos en SQLite.

**Criterios de aceptación de Fase A:**
- [ ] `GeneralRequirement(id=1, categoria="CAUSAL_RECHAZO", tipo="CAUSAL_RECHAZO", descripcion="test")` no lanza `ValidationError`.
- [ ] `GeneralRequirementList.model_validate_json('{"requisitos":[{"id":1,"categoria":"JURIDICO","descripcion":"RUP"}]}')` produce `tipo="NO_ESPECIFICADO"` y `documento_formato="N/A"`.
- [ ] El JSON de salida del LLM (nuevo prompt Fase B) parsea sin errores.

---

## FASE B — Nuevos prompts por tipo de requerimiento

> **Por qué.** El prompt actual instruye al LLM a extraer "SOLO requisitos habilitantes" y
> usar 6 categorías. Ampliando el scope y definiendo los tipos explícitamente se cubre
> causales de rechazo, garantías y criterios de evaluación sin cambiar la arquitectura RAG.

### B.1 Reemplazar el system prompt en `prompts.py`

**Archivo:** `src/tendermod/evaluation/prompts.py` (línea 266)

Reemplazar la constante `qna_system_message_general_requirements` completa:

```python
qna_system_message_general_requirements = """
Eres un asistente especializado en contratación pública colombiana.
Tu tarea es extraer TODOS los requerimientos del pliego de condiciones del contexto proporcionado:
habilitantes, causales de rechazo, garantías, criterios de evaluación/ponderación, y documentales.

EXCLUYE únicamente:
- Indicadores financieros de ratio (liquidez, endeudamiento, rentabilidad, ROCE, ROE, ROA) —
  ya se procesan por separado en otro módulo.
- Requisitos de experiencia UNSPSC detallados — ya se procesan por separado.

== CATEGORÍAS ==
- JURIDICO      : RUP, cámara de comercio, certificados tributarios, antecedentes
- TECNICO       : certificaciones ISO, acreditaciones, normas técnicas, equipos, software
- DOCUMENTACION : formularios del pliego, cartas de presentación, paz y salvos, formatos
- CAPACIDAD     : personal mínimo, directores, estructura organizacional, oficinas
- FINANCIERO_OTRO : patrimonio líquido mínimo, capital de trabajo (monto fijo, no ratio),
                    ROA/ROE si el pliego los exige como habilitantes con valor mínimo fijo
- GARANTIA      : pólizas (seriedad, cumplimiento, estabilidad, responsabilidad civil, etc.)
- CAUSAL_RECHAZO: condiciones explícitas de rechazo de oferta (sección 2.x en AMPs)
- EVALUACION    : criterios de puntaje (técnicos, económicos, industria nacional, MiPymes)
- OTRO          : cualquier otro requerimiento no clasificable en las anteriores

== TIPOS ==
- HABILITANTE    : cumple/no-cumple; oferta inhabilitada si no lo tiene
- PUNTUABLE      : otorga puntaje; la oferta no se rechaza por no tenerlo
- DOCUMENTAL     : formulario o formato que debe acompañar la oferta
- GARANTIA       : póliza o garantía exigida
- CAUSAL_RECHAZO : condición que genera rechazo automático de la propuesta
- NO_ESPECIFICADO: cuando no hay suficiente contexto para determinar el tipo

== REGLAS CRÍTICAS ==

1) NUMERAL DE SECCIÓN (anti-alucinación):
   - El campo "seccion" DEBE ser el numeral exacto que aparece literalmente en el contexto
     (ej. "2.23.1", "5.1.3", "7.2.1").
   - Si el contexto NO contiene un numeral visible que ancle el requisito, devuelve "N/A".
   - JAMÁS infieras, completes ni inventes un número de sección.

2) TIPO vs CATEGORÍA:
   - Un ítem CAUSAL_RECHAZO: categoria="CAUSAL_RECHAZO", tipo="CAUSAL_RECHAZO".
   - Un ítem de puntaje (contiene "puntos", "puntaje", "máximo X puntos"): tipo="PUNTUABLE",
     categoria="EVALUACION" (o "TECNICO" si es criterio técnico puntuable).
   - Un formulario (contiene "FORMATO No.", "Anexo No.", "Formulario No."): tipo="DOCUMENTAL",
     categoria="DOCUMENTACION".
   - Una póliza: categoria="GARANTIA", tipo="GARANTIA".

3) DOCUMENTO/FORMATO:
   - Si el requisito menciona "FORMATO No. X", "ANEXO No. X", "FORMULARIO No. X", pon ese
     nombre exacto en el campo "documento_formato". Ej: "FORMATO No. 3".
   - Si no hay formato explícito, usa "N/A".

4) GRANULARIDAD:
   - Cada ítem numerado (2.23.1, 5.1.3, 7.2.1, …) es UN ítem separado.
   - Si una sección define múltiples condiciones de rechazo numeradas, cada una es un ítem.

5) COMPLETITUD Y DEDUPLICACIÓN:
   - Revisa el contexto completo antes de responder.
   - Si un mismo requisito aparece en varias secciones, inclúyelo UNA SOLA VEZ.

Devuelve únicamente JSON válido con este formato exacto:
{
  "requisitos": [
    {
      "id": 1,
      "categoria": "JURIDICO",
      "tipo": "HABILITANTE",
      "descripcion": "descripción exacta del requisito tal como aparece en el pliego",
      "documento_formato": "N/A",
      "obligatorio": "SI",
      "pagina": "12",
      "seccion": "5.1.1",
      "estado": "PENDIENTE",
      "origen": "EXTRACCION"
    }
  ]
}

Si no se encuentran requerimientos en el contexto, devuelve: {"requisitos": []}

IMPORTANTE: Devuelve ÚNICAMENTE el objeto JSON. Sin texto adicional. Sin markdown. Sin bloques de código.
"""
```

**Actualizar también el user message** (`qna_user_message_general_requirements`) para reflejar
el scope ampliado:

```python
qna_user_message_general_requirements = """
###Context
Here are some relevant excerpts from the tender document:
{context}

###Question
Extract ALL requirements (habilitantes, causales de rechazo, garantías, criterios de evaluación
y documentales) related to:
{question}
"""
```

**Criterios de aceptación de Fase B:**
- [ ] El LLM devuelve ítems con `tipo="CAUSAL_RECHAZO"` cuando el contexto contiene sección 2.23.x.
- [ ] El LLM devuelve ítems con `tipo="PUNTUABLE"` y `categoria="EVALUACION"` para secciones 7.x.
- [ ] El campo `documento_formato` se popula para ítems que mencionan "FORMATO No.".
- [ ] El JSON parsea sin `ValidationError` contra el schema expandido de Fase A.

---

## FASE C — Queries dinámicas desde TOC (Discovery Pasada 0)

> **Por qué.** La raíz del gap es que `HABILITANTES_QUERIES` usa terminología de pliegos FNA
> (4.1.x, SARLAFT, etc.) que no matchea embeddings del pliego AMP (2.x, 5.x, 7.x).
> Extrayendo el TOC del pliego real y generando queries desde sus títulos de sección, el
> retriever recupera los chunks correctos independientemente del tipo de pliego.

### C.1 Extractor de TOC nativo con PyMuPDF

**Archivo nuevo:** `src/tendermod/ingestion/toc_extractor.py`

PyMuPDF expone `doc.get_toc()` que devuelve `[(level, title, page), ...]`. Para pliegos
bien estructurados (mayoría de AMPs de Colombia Compra Eficiente), esto resuelve el 80%
del problema sin llamada LLM adicional.

```python
"""Extrae la Tabla de Contenido del pliego para generar queries de retrieval adaptativas.

Estrategia dual:
1. Primero intenta PyMuPDF doc.get_toc() (gratuito, instantáneo).
2. Si el TOC nativo está vacío (PDF mal estructurado), envía las primeras 6 páginas
   al LLM para que identifique las secciones con requerimientos.
"""
import logging
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Secciones que típicamente contienen requerimientos en pliegos colombianos.
# Se usan como fallback cuando el TOC nativo está vacío.
REQUIREMENT_SECTION_KEYWORDS = [
    "habilitante", "requisito", "rechazo", "causal", "garantía", "póliza",
    "evaluación", "puntaje", "capacidad", "experiencia", "jurídico", "técnico",
    "financiero", "documental", "formulario", "formato", "anexo",
]


def extract_toc_native(pdf_path: str) -> list[dict]:
    """Extrae el TOC usando el outline nativo del PDF (PyMuPDF)."""
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()  # [(level, title, page), ...]
    doc.close()

    if not toc:
        logger.info("[toc_extractor] TOC nativo vacío en %s", pdf_path)
        return []

    result = []
    for level, title, page in toc:
        result.append({
            "level": level,
            "title": title.strip(),
            "page": page,
            "number": _extract_number(title),
        })
    logger.info("[toc_extractor] TOC nativo: %d entradas desde %s", len(result), pdf_path)
    return result


def extract_toc_llm(pdf_path: str, llm_client, n_pages: int = 6) -> list[dict]:
    """Extrae el TOC enviando las primeras n_pages al LLM (fallback)."""
    doc = fitz.open(pdf_path)
    pages_text = "\n".join(
        doc[i].get_text() for i in range(min(n_pages, len(doc)))
    )
    doc.close()

    from tendermod.evaluation.prompts import TOC_EXTRACTION_SYSTEM, TOC_EXTRACTION_USER
    from tendermod.evaluation.llm_client import run_llm_raw_json

    result = run_llm_raw_json(
        system=TOC_EXTRACTION_SYSTEM,
        user=TOC_EXTRACTION_USER.format(pages_text=pages_text),
    )
    logger.info("[toc_extractor] TOC LLM: %d entradas", len(result))
    return result


def get_toc(pdf_path: str, llm_client=None) -> list[dict]:
    """Punto de entrada: TOC nativo; si está vacío, LLM fallback."""
    toc = extract_toc_native(pdf_path)
    if toc:
        return toc
    if llm_client is None:
        logger.warning("[toc_extractor] TOC vacío y sin llm_client — usando queries fallback")
        return []
    return extract_toc_llm(pdf_path, llm_client)


def toc_to_queries(toc: list[dict]) -> list[str]:
    """Convierte entradas del TOC en queries de retrieval.

    Filtra solo secciones con keywords de requerimientos y construye
    queries que combinan el numeral + título de sección.
    """
    if not toc:
        return []

    queries = []
    for entry in toc:
        title_lower = entry["title"].lower()
        is_relevant = any(kw in title_lower for kw in REQUIREMENT_SECTION_KEYWORDS)
        if is_relevant:
            number = entry.get("number", "")
            query = f"{number} {entry['title']}".strip()
            queries.append(query)

    logger.info("[toc_extractor] %d queries generadas desde TOC (%d entradas totales)",
                len(queries), len(toc))
    return queries


def _extract_number(title: str) -> str:
    """Extrae el numeral de un título de sección. Ej: '2.23.1 Causales de rechazo' -> '2.23.1'"""
    import re
    match = re.match(r"^\s*(\d+(?:\.\d+)*)\s*", title)
    return match.group(1) if match else ""
```

### C.2 Prompts para TOC LLM fallback

**Archivo:** `src/tendermod/evaluation/prompts.py` (agregar al final)

```python
TOC_EXTRACTION_SYSTEM = """Eres un extractor de estructura de documentos de licitación pública
colombiana. Se te darán las primeras páginas de un pliego de condiciones.
Extrae TODAS las entradas de la tabla de contenido (índice) que correspondan a secciones
con requerimientos, habilitantes, causales de rechazo, garantías, evaluación o documentos.

Devuelve ÚNICAMENTE JSON válido con esta estructura:
[
  {"level": 1, "title": "CAPÍTULO 2 — CONDICIONES DEL PROCESO", "page": 10, "number": "2"},
  {"level": 2, "title": "2.23 Causales de rechazo de la oferta", "page": 45, "number": "2.23"},
  {"level": 3, "title": "2.23.1 No presentar la oferta en el formulario habilitado", "page": 45, "number": "2.23.1"}
]

IMPORTANTE: Solo JSON. Sin texto adicional. Sin markdown."""

TOC_EXTRACTION_USER = """Páginas iniciales del pliego:

{pages_text}

Extrae la tabla de contenido."""
```

### C.3 Integrar TOC en `get_general_requirements`

**Archivo:** `src/tendermod/evaluation/general_requirements_inference.py`

```python
# Queries de fallback — se usan cuando el TOC está vacío (pliegos sin outline nativo
# y sin llm_client para el fallback LLM del TOC).
# Cubren terminología de pliegos FNA (4.1.x) Y terminología AMP Colombia Compra Eficiente (2.x, 5.x, 7.x).
FALLBACK_QUERIES: list[str] = [
    # -- Causales de rechazo (AMP 2.23.x) --
    "causal rechazo oferta propuesta inhábil inadmisible",
    "rechazo automático oferta no subsanable",
    # -- Jurídicos (FNA 4.1.1.x / AMP 5.1.x) --
    "carta presentación propuesta firma representante legal declaración juramento",
    "certificado existencia representación legal cámara comercio objeto social",
    "registro único proponentes RUP inscripción vigente firme",
    "garantía seriedad oferta póliza valor presupuesto oficial",
    "antecedentes fiscales disciplinarios judiciales contraloría procuraduría policía",
    "compromiso anticorrupción transparencia lavado activos SARLAFT",
    "habeas data autorización tratamiento datos personales",
    "seguridad social parafiscales aportes salud pensión ARL",
    # -- Garantías (AMP 5.1.9 / FNA) --
    "póliza garantía cumplimiento estabilidad responsabilidad civil calidad",
    "amparo cobertura garantía única asegurado beneficiario",
    # -- Técnicos (FNA 4.1.2.x / AMP 5.4) --
    "certificación fabricante distribuidor partner canal autorizado solución",
    "personal mínimo requerido perfiles profesional especialista certificaciones",
    "norma técnica ISO IEC NIST certificación acreditación sistema gestión",
    "manifestación aceptación requerimientos mínimos obligatorios anexo técnico",
    # -- Financieros (AMP 5.2.1 / FNA 4.1.3) --
    "patrimonio líquido capital de trabajo monto mínimo requerido",
    "ROA ROE indicador financiero habilitante valor mínimo exigido",
    # -- Evaluación/Ponderables (AMP 7.x) --
    "criterio evaluación puntaje puntos asignación técnico económico",
    "industria nacional MiPymes mujeres diferencial puntaje adicional",
    "propuesta económica precio evaluación económica ponderación",
]


def get_general_requirements(k: int = 3) -> GeneralRequirementList:
    docs = load_docs()
    all_chunks = chunk_docs(docs)

    vectorstore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever_experience(vectorstore, k=k)

    # --- PASADA 0: Discovery del TOC ---
    pdf_path = _get_pdf_path()   # helper que retorna el path del PDF actual en data/
    try:
        from tendermod.ingestion.toc_extractor import get_toc, toc_to_queries
        toc = get_toc(pdf_path)
        dynamic_queries = toc_to_queries(toc)
    except Exception as exc:
        logger.warning("[get_general_requirements] Error extrayendo TOC: %s — usando fallback", exc)
        dynamic_queries = []

    # Combinar queries dinámicas (TOC) con fallback (cubre pliegos sin TOC)
    queries = dynamic_queries if dynamic_queries else FALLBACK_QUERIES
    # Siempre agregar fallback si las queries dinámicas son < 5 (TOC parcial)
    if len(dynamic_queries) < 5:
        queries = list(dict.fromkeys(dynamic_queries + FALLBACK_QUERIES))  # deduplica preservando orden

    # --- PASADA 1: Retrieval y extracción ---
    retrieved_ids: set[int] = set()
    for query in queries:
        for doc in retriever.invoke(query):
            cid = doc.metadata.get("chunk_id")
            if cid is not None:
                retrieved_ids.add(cid)

    if not retrieved_ids:
        logger.warning("[get_general_requirements] No se recuperaron chunks del vectorstore")
        return GeneralRequirementList(requisitos=[])

    # Expandir vecinos y ordenar por posición en el documento
    expanded: set[int] = set()
    for cid in retrieved_ids:
        for offset in range(-_NEIGHBOR_BACK, _NEIGHBOR_FRONT + 1):
            neighbor = cid + offset
            if 0 <= neighbor < len(all_chunks):
                expanded.add(neighbor)

    context_parts = [all_chunks[i].page_content for i in sorted(expanded)]
    combined_context = "\n".join(context_parts)

    logger.info(
        "[get_general_requirements] %d queries → %d chunks únicos → %d con vecinos → %d chars (~%d tokens)",
        len(queries),
        len(retrieved_ids),
        len(expanded),
        len(combined_context),
        len(combined_context) // 4,
    )

    try:
        parsed = run_llm_general_requirements(combined_context, _QA_QUERY)
    except Exception as exc:
        logger.error("[get_general_requirements] Error llamando LLM: %s", exc)
        return GeneralRequirementList(requisitos=[])

    logger.info("[get_general_requirements] Extraidos %d requisitos", len(parsed.requisitos))
    return parsed


def _get_pdf_path() -> str:
    """Retorna el path del primer PDF encontrado en TENDERMOD_DATA_DIR."""
    import glob
    from tendermod.config.settings import REDNEET_DB_PERSIST_DIR
    # DATA_DIR está un nivel arriba de REDNEET_DB_PERSIST_DIR
    data_dir = str(REDNEET_DB_PERSIST_DIR).replace("/redneet_db", "")
    pdfs = glob.glob(f"{data_dir}/*.pdf")
    if not pdfs:
        raise FileNotFoundError(f"No se encontró PDF en {data_dir}")
    return pdfs[0]
```

**Nota sobre `_get_pdf_path`:** la ruta correcta de `data/` debe derivarse desde
`settings.py`. Si `settings.py` expone una constante `DATA_DIR`, usarla directamente.
Ajustar según el valor real de `CHROMA_PERSIST_DIR` (`./data/chroma` → `./data`).

**Criterios de aceptación de Fase C:**
- [ ] Para CCENEG-094-01-AMP-2026: `get_toc()` devuelve ≥20 entradas incluyendo sección 2.23.x.
- [ ] `toc_to_queries()` produce queries que incluyen "2.23 Causales de rechazo" y "5.1 Habilitantes".
- [ ] Para pliego FNA-VTTD-CP-002-2026: como el TOC nativo puede devolver entradas con terminología diferente, el fallback se activa y las 24 queries existentes cubren el pliego (regresión no rota).
- [ ] El log muestra "N queries generadas desde TOC (M entradas totales)".

---

## FASE D — Extracción multi-pasada por tipo de sección

> **Por qué.** Con TOC dinámico, el retriever recupera los chunks correctos pero los envía
> todos al LLM en un solo contexto combinado. Para secciones densas (22 causales de rechazo),
> el LLM puede omitir ítems por límite de contexto. La extracción por sección garantiza
> completitud.

### D.1 Extracción dirigida por sección del TOC

**Archivo:** `src/tendermod/evaluation/general_requirements_inference.py`

Agregar función `get_general_requirements_v2` que reemplaza progresivamente a
`get_general_requirements`. La función existente se mantiene como fallback.

```python
def get_general_requirements_v2(k: int = 5) -> GeneralRequirementList:
    """
    Extracción en dos pasadas:
    Pasada 0: TOC -> lista de secciones con requerimientos
    Pasada 1: por cada sección, retrieval dirigido + extracción LLM parcial
    Merge final: deduplicar por (seccion, descripcion[:50])
    """
    docs = load_docs()
    all_chunks = chunk_docs(docs)
    vectorstore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever_experience(vectorstore, k=k)

    pdf_path = _get_pdf_path()
    toc = get_toc(pdf_path)
    section_queries = toc_to_queries(toc) if toc else FALLBACK_QUERIES

    all_requisitos: list[GeneralRequirement] = []
    seen: set[tuple] = set()           # (seccion, descripcion_prefix)
    next_id = 1

    for query in section_queries:
        # Retrieval dirigido por sección
        retrieved_ids: set[int] = set()
        for doc in retriever.invoke(query):
            cid = doc.metadata.get("chunk_id")
            if cid is not None:
                retrieved_ids.add(cid)

        if not retrieved_ids:
            continue

        # Expandir vecinos (ventana más estrecha para extracción dirigida)
        expanded: set[int] = set()
        for cid in retrieved_ids:
            for offset in range(-1, 3):   # -1 a +2 (ventana reducida)
                neighbor = cid + offset
                if 0 <= neighbor < len(all_chunks):
                    expanded.add(neighbor)

        context = "\n".join(all_chunks[i].page_content for i in sorted(expanded))

        try:
            partial = run_llm_general_requirements(context, query)
        except Exception as exc:
            logger.warning("[get_general_requirements_v2] Error en sección '%s': %s", query, exc)
            continue

        # Merge con deduplicación
        for req in partial.requisitos:
            key = (req.seccion, req.descripcion[:50])
            if key not in seen:
                seen.add(key)
                req.id = next_id
                next_id += 1
                all_requisitos.append(req)

    logger.info("[get_general_requirements_v2] Total: %d requisitos tras merge", len(all_requisitos))
    return GeneralRequirementList(requisitos=all_requisitos)
```

### D.2 Activar v2 en la task de Celery

**Archivo:** `web/apps/analysis/tasks.py` (función `extract_general_requirements_task`)

```python
# Cambiar línea 59:
# ANTES:
req_list = get_general_requirements(k=15)

# DESPUÉS (cuando Fase D esté lista):
try:
    from tendermod.evaluation.general_requirements_inference import get_general_requirements_v2
    req_list = get_general_requirements_v2(k=5)
except Exception as exc:
    logger.warning("get_general_requirements_v2 falló (%s) — usando v1 fallback", exc)
    req_list = get_general_requirements(k=15)
```

**Criterios de aceptación de Fase D:**
- [ ] Para CCENEG-094-01-AMP-2026: ≥15 causales de rechazo extraídos (vs 0 actual).
- [ ] Para CCENEG-094-01-AMP-2026: ≥4 ítems de categoría EVALUACION (7.x).
- [ ] Para CCENEG-094-01-AMP-2026: total ≥80 ítems (vs 15 actual) — umbral de éxito.
- [ ] Para FNA-VTTD-CP-002-2026: los 24 habilitantes originales siguen apareciendo (regresión).
- [ ] El log reporta cuántos requisitos se extrajeron por pasada.

---

## FASE E — Compatibilidad Django

> Las Fases A–D no requieren cambios en la base de datos de Django porque `general_requirements_json`
> es un `TextField` sin schema fijo. Los nuevos campos en el schema Pydantic son opcionales con
> defaults. Sin embargo, la UI debe mostrar los nuevos tipos y categorías.

### E.1 Migración de base de datos

**No se requiere migración de esquema SQL.** El campo `AnalysisSession.general_requirements_json`
ya existe (migración 0004). Los nuevos campos `tipo` y `documento_formato` en
`GeneralRequirement` se serializan en JSON dentro del mismo `TextField` — no hay columna nueva.

Las sesiones antiguas se leen sin error porque los nuevos campos tienen default en Pydantic.
Las sesiones nuevas incluirán `tipo` y `documento_formato` en el JSON.

**Verificación:** ningún `model_validate_json` en `views.py` (líneas 185–189, 293–299) ni en
`tasks.py` (línea 62) rompe con el schema expandido. Todos usan `GeneralRequirementList.model_validate_json`
que tolera campos adicionales o faltantes con defaults.

### E.2 Actualizar `analysis_pliego_qa` para nuevas categorías

**Archivo:** `web/apps/analysis/views.py` (línea 355)

El endpoint `analysis_pliego_qa` acepta `categoria` del body y la pasa a
`GeneralRequirement(categoria=categoria, ...)`. Con las nuevas categorías, el frontend
debe poder enviar `"CAUSAL_RECHAZO"` o `"EVALUACION"`. No requiere cambios en Python,
pero el dropdown en el template debe actualizarse.

### E.3 Actualizar `step2.html` — checklist por tipo

**Archivo:** `web/templates/analysis/step2.html`

El checklist actual agrupa por `categoria`. Agregar agrupación secundaria por `tipo`
y añadir badge de color para tipo:

```html
<!-- Ejemplo de badge por tipo — agregar en el loop de requisitos -->
{% if req.tipo == "CAUSAL_RECHAZO" %}
    <span class="badge bg-danger ms-1">Causal Rechazo</span>
{% elif req.tipo == "PUNTUABLE" %}
    <span class="badge bg-info ms-1">Puntuable</span>
{% elif req.tipo == "GARANTIA" %}
    <span class="badge bg-warning text-dark ms-1">Garantía</span>
{% elif req.tipo == "HABILITANTE" %}
    <span class="badge bg-success ms-1">Habilitante</span>
{% elif req.tipo == "DOCUMENTAL" %}
    <span class="badge bg-secondary ms-1">Documental</span>
{% endif %}
```

Agregar al dropdown de categorías del Q&A las nuevas opciones:

```html
<option value="GARANTIA">GARANTIA</option>
<option value="CAUSAL_RECHAZO">CAUSAL_RECHAZO</option>
<option value="EVALUACION">EVALUACION</option>
```

### E.4 Actualizar `export_excel` — hoja Checklist General

**Archivo:** `web/apps/analysis/views.py` (línea 532)

Agregar columnas `Tipo` y `Documento/Formato` a la hoja "Checklist General":

```python
# ANTES (línea 533):
cl_headers = ['#', 'Categoria', 'Descripcion', 'Obligatorio', 'Seccion', 'Pagina', 'Estado', 'Origen']

# DESPUÉS:
cl_headers = ['#', 'Categoria', 'Tipo', 'Descripcion', 'Documento/Formato',
              'Obligatorio', 'Seccion', 'Pagina', 'Estado', 'Origen']

# ANTES (línea 548):
ws_cl.append([
    req.id, req.categoria, req.descripcion,
    req.obligatorio, req.seccion, req.pagina,
    req.estado, req.origen,
])

# DESPUÉS:
ws_cl.append([
    req.id, req.categoria, req.tipo, req.descripcion,
    req.documento_formato, req.obligatorio, req.seccion,
    req.pagina, req.estado, req.origen,
])
```

**Criterios de aceptación de Fase E:**
- [ ] `analysis_step2` renderiza sin error con sesiones antiguas (sin campo `tipo`).
- [ ] El badge de tipo se muestra en el checklist de step2.
- [ ] El Excel exportado incluye columnas Tipo y Documento/Formato.
- [ ] El dropdown Q&A incluye las 3 nuevas categorías.

---

## Plan de compatibilidad retroactiva (sesiones existentes)

| Escenario | Comportamiento |
|---|---|
| Sesión antigua sin campo `tipo` en JSON | `model_validate_json` asigna `tipo="NO_ESPECIFICADO"` — sin error |
| Sesión antigua sin campo `documento_formato` | `model_validate_json` asigna `documento_formato="N/A"` — sin error |
| Sesión antigua con `categoria="JURIDICO"` | Válido — las 6 categorías originales se mantienen en el Literal |
| Template step2 con req antiguo sin badge tipo | `req.tipo == "NO_ESPECIFICADO"` — no muestra badge (ninguna condición del if aplica) |
| Excel export con sesión antigua | `req.tipo="NO_ESPECIFICADO"`, `req.documento_formato="N/A"` — celdas con esos valores |
| `analysis_checklist_save` recibe `estado` para req antiguo | Sin cambio — solo actualiza campo `estado` que siempre existió |

No se requiere script de migración de datos. El único riesgo es una sesión donde el JSON
almacenado tenga `categoria` con un valor fuera de los 9 admitidos — imposible con el schema
Pydantic actual que nunca permitió valores distintos.

---

## Criterios de aceptación globales

### Pliego de prueba primario: CCENEG-094-01-AMP-2026

| Métrica | Estado actual | Meta mínima (éxito) | Meta ideal |
|---|---|---|---|
| Total ítems extraídos | 15 | **≥80** | ≥95 |
| Ítems CAUSAL_RECHAZO | 0 | ≥15 | ≥20 |
| Ítems categoría EVALUACION | 0 | ≥4 | ≥9 |
| Ítems categoría GARANTIA | 0 | ≥3 | ≥5 |
| Ítems JURIDICO | 8 | ≥14 | ≥17 |
| Ítems TECNICO | 3 | ≥7 | ≥9 |
| Precisión (no ruido) | ~90% | ≥85% | ≥90% |
| Secciones correctamente atribuidas | ~70% | ≥80% | ≥95% |

### Pliego de regresión: FNA-VTTD-CP-002-2026

| Métrica | Meta (no-regresión) |
|---|---|
| 24 habilitantes originales presentes | ≥22 de 24 |
| Cero ítems nuevos falsos positivos | ≤3 falsos positivos |

### Otras métricas operacionales

| Métrica | Límite aceptable |
|---|---|
| Tiempo de extracción (Celery task) | ≤90 segundos (vs ~30s actual) |
| Incremento de costo LLM por extracción | ≤3x el costo actual |
| `ValidationError` al parsear JSON del LLM | 0 errores en ≥95% de ejecuciones |

---

## Archivos a modificar — resumen

| Archivo | Tipo de cambio | Fase |
|---|---|---|
| `src/tendermod/evaluation/schemas.py` | Expand `GeneralRequirement`: +2 campos, +3 categorías, nuevo Literal `tipo` | A |
| `src/tendermod/evaluation/prompts.py` | Reemplazar `qna_system_message_general_requirements` + agregar `TOC_EXTRACTION_SYSTEM/USER` | B + C |
| `src/tendermod/ingestion/toc_extractor.py` | Archivo nuevo | C |
| `src/tendermod/evaluation/general_requirements_inference.py` | Reemplazar `HABILITANTES_QUERIES` por `FALLBACK_QUERIES`, integrar TOC en `get_general_requirements`, agregar `get_general_requirements_v2` | C + D |
| `web/apps/analysis/tasks.py` | Línea 59: cambiar `k=15` a llamada `v2` con fallback a `v1` | D |
| `web/apps/analysis/views.py` | Líneas 533+548: nuevas columnas en export Excel; líneas del dropdown Q&A en template | E |
| `web/templates/analysis/step2.html` | Badge por `tipo`, opciones nuevas en dropdown Q&A | E |

**Archivos que NO se modifican:**
- `web/apps/core/models.py` — sin cambio (campo `general_requirements_json` ya existe como `TextField`)
- `web/apps/core/migrations/` — sin nueva migración
- `web/apps/analysis/urls.py` — sin nuevas rutas
- `src/tendermod/evaluation/llm_client.py` — la función `run_llm_general_requirements` se reutiliza tal cual; solo se agrega `run_llm_raw_json` si se implementa el TOC LLM fallback

---

## Orden de implementación (PRs sugeridos)

**PR 1 (Bloqueante, ~3h):** Fase A + Fase B
- Expandir schema (`schemas.py`)
- Reemplazar system prompt (`prompts.py`)
- Verificar que `extract_general_requirements_task` no lanza `ValidationError` en ambos pliegos

**PR 2 (~4h):** Fase E (Django UI)
- Badge por tipo en `step2.html`
- Nuevas categorías en dropdown Q&A
- Nuevas columnas en export Excel
- Prueba manual con una sesión antigua: no debe romper

**PR 3 (~1 día):** Fase C (TOC Discovery)
- Nuevo `toc_extractor.py`
- Integrar en `get_general_requirements`
- Probar con CCENEG-094-01-AMP-2026: verificar que el TOC nativo resuelve el gap de secciones

**PR 4 (~1 día):** Fase D (extracción multi-pasada)
- `get_general_requirements_v2`
- Activar en `tasks.py` con fallback a v1
- Prueba de regresión con FNA-VTTD-CP-002-2026

---

## Anexo — Columnas de referencia Claude Cowork

Para validar la implementación contra la referencia, el dataset de salida debe ser
comparable con estas columnas:

```
ID | Categoría | Tipo | Sección Pliego | Requerimiento | Descripción |
Cumple | Documento/Formato Exigido | Observaciones
```

El mapping de columnas al schema Pydantic expandido es:

| Columna Referencia | Campo `GeneralRequirement` |
|---|---|
| ID | `id` |
| Categoría | `categoria` |
| Tipo | `tipo` |
| Sección Pliego | `seccion` |
| Requerimiento | `descripcion` (primera línea) |
| Cumple | `estado` |
| Documento/Formato Exigido | `documento_formato` |
| Observaciones | — (no modelado, candidato a campo futuro) |
