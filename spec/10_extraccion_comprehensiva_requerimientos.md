# Fase 1.2 — Extracción Comprehensiva de Requerimientos

> **Contexto.** El sistema extrae 15 ítems de un pliego AMP (CCENEG-094-01-AMP-2026) donde la
> referencia manual identifica 107. El gap es de 7x. Las causas son estructurales: queries
> hardcodeadas para pliegos FNA, scope limitado a "habilitantes", schema con 6 categorías fijas,
> y ausencia de discovery adaptativo.
>
> **Enfoque resuelto:** En lugar de usar ChromaDB/RAG para extraer requerimientos generales,
> se extrae el texto completo del PDF por capítulos y se envía directamente al LLM. Esto
> elimina el problema de embedding mismatch entre terminología FNA y AMP, y garantiza cobertura
> completa del contenido relevante.
>
> **Hallazgo crítico:** `doc.get_toc()` (PyMuPDF) retorna `[]` para al menos el pliego FNA
> (FNA test9.pdf). El TOC nativo NO puede ser la estrategia primaria — necesita fallback robusto.
>
> **Archivos clave:**
> - `src/tendermod/evaluation/schemas.py` (línea 110 — `GeneralRequirement`)
> - `src/tendermod/evaluation/prompts.py` (línea 266 — `qna_system_message_general_requirements`)
> - `src/tendermod/evaluation/general_requirements_inference.py` (`get_general_requirements`)
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

| Causa | Ítems perdidos (estimado) | Solución propuesta |
|---|---|---|
| Queries con terminología 4.1.x FNA — no matchean secciones 2.x/5.x/7.x del AMP | ~50 | Eliminar dependencia de ChromaDB para extracción de requerimientos |
| Scope de prompt = solo "habilitantes" | ~35 | Ampliar scope en prompts (Fase B) |
| Schema sin categorías CAUSAL_RECHAZO, GARANTIA, EVALUACION | ~35 | Expandir schema (Fase A) |
| Fragmentación del contexto (chunks de 512 tokens) | ~15 | Extracción por capítulo completo (Fase C) |

---

## Resumen ejecutivo de fases

| Fase | Nombre | Ítems recuperados (est.) | Esfuerzo | Tiempo |
|---|---|---|---|---|
| **A** | Expansión del schema (nuevas categorías + campo `tipo`) | 0 directos (habilita B/C) | Bajo | 1–2 h |
| **B** | Nuevos prompts por tipo de requerimiento | +20–30 (tipos nuevos con prompts actuales) | Medio | 3–4 h |
| **C** | Extracción por capítulos completos (reemplaza RAG para esta feature) | +30–60 (termina de cubrir AMP) | Medio-alto | 1 día |
| **D** | Detección robusta de límites de capítulo (sin TOC nativo) | +10–15 (cobertura total en FNA) | Medio | 4–6 h |
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
> causales de rechazo, garantías y criterios de evaluación sin cambiar la arquitectura.

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

## FASE C — Extracción por capítulos completos (reemplaza RAG para esta feature)

> **Cambio arquitectónico principal.** La extracción de requerimientos generales deja de
> usar ChromaDB. En lugar de fragmentar el PDF en chunks de 512 tokens, hacer queries de
> embeddings y ensamblar contexto parcial, se extrae el texto completo de cada capítulo
> relevante y se envía directamente al LLM. ChromaDB se mantiene para las otras features
> (experiencia, indicadores, Q&A sobre el pliego).
>
> **Por qué este cambio resuelve el gap:**
> - **Embedding mismatch eliminado:** queries FNA no encuentran secciones AMP porque los
>   embeddings de "4.1.1.x cámara comercio" y "5.1.3 certificados" son similares pero no
>   idénticos. Enviando el texto completo del capítulo, el LLM ve todo.
> - **Contexto coherente:** un capítulo de 10 páginas es 3K–8K tokens — gpt-4o-mini maneja
>   hasta 128K. No hay "lost in the middle" porque cada llamada procesa un capítulo.
> - **Cobertura garantizada:** si el capítulo está en el PDF, está en el contexto del LLM.

### C.0 Análisis del presupuesto de tokens

| Tipo de pliego | Páginas totales | Tokens totales (est.) | Capítulos relevantes | Tokens por capítulo |
|---|---|---|---|---|
| FNA test9.pdf | ~90 páginas | ~97K tokens | 3–5 capítulos | 5K–20K tokens |
| AMP CCENEG-094 (~120 páginas) | ~120 páginas | ~130K tokens | 5–7 capítulos | 5K–25K tokens |
| Pliego grande (~250 páginas) | ~250 páginas | ~270K tokens | 8–12 capítulos | 5K–30K tokens |

**Estrategia recomendada:** extracción por capítulo (no documento completo). Incluso para
pliegos de 250 páginas, cada capítulo cabe dentro de los 128K de gpt-4o-mini. El documento
completo supera el límite a partir de ~120 páginas.

**Costo estimado:** 1 llamada LLM por capítulo relevante. Para un pliego típico (5–7 capítulos),
esto representa 5–7 llamadas vs. 1 llamada actual. El costo sube ~5x pero la cobertura pasa
de 14% a ≥80%.

### C.1 Nuevo archivo: `chapter_extractor.py`

**Archivo nuevo:** `src/tendermod/ingestion/chapter_extractor.py`

```python
"""
Extrae texto del PDF por rangos de página para extracción de requerimientos sin RAG.

Estrategia de detección de límites de capítulo (en orden de prioridad):
1. TOC nativo de PyMuPDF (doc.get_toc()) — instantáneo, sin costo LLM.
2. LLM sobre primeras páginas — cuando el PDF no tiene outline nativo (ej. FNA test9.pdf).
3. Heurística de texto — fallback final para PDFs sin TOC visible en primeras páginas.
"""
import logging
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Keywords que indican secciones con requerimientos en pliegos colombianos.
REQUIREMENT_KEYWORDS = [
    "habilitante", "requisito", "rechazo", "causal", "garantía", "póliza",
    "evaluación", "puntaje", "capacidad", "experiencia", "jurídico", "técnico",
    "financiero", "documental", "formulario", "formato", "anexo", "criterio",
]

# Patrón heurístico para detectar títulos de sección en el texto del PDF.
# Detecta líneas que comienzan con un numeral como "2.", "2.3", "2.3.1", "CAPÍTULO 2".
_SECTION_HEADER_PATTERN = re.compile(
    r"^(?:CAPÍTULO\s+\d+|CAPITULO\s+\d+|\d+(?:\.\d+){0,3})\s+\S",
    re.MULTILINE | re.IGNORECASE,
)


def extract_page_range(pdf_path: str, start_page: int, end_page: int) -> str:
    """Extrae el texto de las páginas [start_page, end_page) del PDF (índice 0-based)."""
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(start_page, min(end_page, len(doc))):
        pages.append(doc[i].get_text())
    doc.close()
    return "\n".join(pages)


def extract_full_text(pdf_path: str) -> str:
    """Extrae el texto completo del PDF página por página."""
    doc = fitz.open(pdf_path)
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    return "\n".join(pages)


def get_chapter_ranges_native(pdf_path: str) -> list[dict]:
    """
    Obtiene rangos de capítulo usando el TOC nativo del PDF.
    Retorna lista de {'title': str, 'start_page': int, 'end_page': int}.
    Retorna [] si el PDF no tiene TOC nativo.
    """
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()    # [(level, title, page_1based), ...]
    n_pages = len(doc)
    doc.close()

    if not toc:
        logger.info("[chapter_extractor] TOC nativo vacío en %s", pdf_path)
        return []

    # Convertir TOC a rangos (start, end) — página 0-based.
    entries = [{"title": t, "start": p - 1} for _, t, p in toc]
    chapters = []
    for i, entry in enumerate(entries):
        end = entries[i + 1]["start"] if i + 1 < len(entries) else n_pages
        chapters.append({
            "title": entry["title"],
            "start_page": entry["start"],
            "end_page": end,
        })

    logger.info("[chapter_extractor] TOC nativo: %d capítulos en %s", len(chapters), pdf_path)
    return chapters


def get_chapter_ranges_llm(pdf_path: str, n_pages_scan: int = 10) -> list[dict]:
    """
    Detecta capítulos enviando las primeras n_pages_scan páginas al LLM.
    Usado cuando el TOC nativo está vacío (ej. FNA test9.pdf).
    Retorna lista de {'title': str, 'start_page': int, 'end_page': int}.
    """
    doc = fitz.open(pdf_path)
    n_total = len(doc)
    first_pages_text = "\n".join(
        f"[Página {i + 1}]\n{doc[i].get_text()}"
        for i in range(min(n_pages_scan, n_total))
    )
    doc.close()

    from tendermod.evaluation.llm_client import run_llm_chapter_detection
    chapters_raw = run_llm_chapter_detection(first_pages_text, n_total)

    # chapters_raw es una lista de {'title': str, 'start_page': int (1-based), 'end_page': int (1-based)}
    # Convertir a 0-based.
    chapters = []
    for ch in chapters_raw:
        chapters.append({
            "title": ch.get("title", ""),
            "start_page": max(0, ch.get("start_page", 1) - 1),
            "end_page": min(n_total, ch.get("end_page", n_total)),
        })

    logger.info("[chapter_extractor] LLM detectó %d capítulos en %s", len(chapters), pdf_path)
    return chapters


def get_chapter_ranges_heuristic(pdf_path: str) -> list[dict]:
    """
    Detecta capítulos por heurística de texto: busca líneas que comiencen con
    numerales de sección o la palabra CAPÍTULO.
    Fallback de último recurso — menos preciso que LLM pero sin costo adicional.
    """
    doc = fitz.open(pdf_path)
    n_pages = len(doc)
    boundaries = []
    for i in range(n_pages):
        text = doc[i].get_text()
        if _SECTION_HEADER_PATTERN.search(text):
            # Encontrar el primer match para usar como título aproximado.
            match = _SECTION_HEADER_PATTERN.search(text)
            if match:
                title = match.group(0).strip()[:80]
                boundaries.append({"title": title, "start_page": i})
    doc.close()

    if not boundaries:
        # Sin estructura detectable: tratar todo el documento como un solo bloque.
        logger.warning("[chapter_extractor] Heurística no detectó estructura en %s — bloque único", pdf_path)
        return [{"title": "Documento completo", "start_page": 0, "end_page": n_pages}]

    chapters = []
    for i, b in enumerate(boundaries):
        end = boundaries[i + 1]["start_page"] if i + 1 < len(boundaries) else n_pages
        chapters.append({
            "title": b["title"],
            "start_page": b["start_page"],
            "end_page": end,
        })
    logger.info("[chapter_extractor] Heurística: %d capítulos en %s", len(chapters), pdf_path)
    return chapters


def get_chapter_ranges(pdf_path: str, use_llm: bool = True) -> list[dict]:
    """
    Punto de entrada unificado. Intentos en orden:
    1. TOC nativo (gratuito, instantáneo).
    2. LLM sobre primeras páginas (si use_llm=True).
    3. Heurística de texto (siempre disponible).
    """
    chapters = get_chapter_ranges_native(pdf_path)
    if chapters:
        return chapters

    if use_llm:
        try:
            chapters = get_chapter_ranges_llm(pdf_path)
            if chapters:
                return chapters
        except Exception as exc:
            logger.warning("[chapter_extractor] LLM fallback falló: %s — usando heurística", exc)

    return get_chapter_ranges_heuristic(pdf_path)


def filter_relevant_chapters(chapters: list[dict]) -> list[dict]:
    """
    Filtra capítulos que probablemente contengan requerimientos,
    usando REQUIREMENT_KEYWORDS en el título.
    """
    relevant = [
        ch for ch in chapters
        if any(kw in ch["title"].lower() for kw in REQUIREMENT_KEYWORDS)
    ]
    if not relevant:
        # Si ningún título matchea, incluir todos (el pliego puede usar títulos atípicos).
        logger.warning(
            "[chapter_extractor] Ningún capítulo con keywords de requerimiento — incluyendo todos"
        )
        return chapters
    logger.info(
        "[chapter_extractor] %d/%d capítulos relevantes seleccionados",
        len(relevant), len(chapters),
    )
    return relevant
```

### C.2 Nuevas funciones en `llm_client.py`

**Archivo:** `src/tendermod/evaluation/llm_client.py`

Agregar dos funciones al final del archivo:

```python
def run_llm_chapter_detection(pages_text: str, total_pages: int) -> list[dict]:
    """
    Llama al LLM para detectar capítulos y sus rangos de página desde las primeras
    páginas del PDF. Retorna lista de dicts con title, start_page, end_page (1-based).
    """
    from tendermod.evaluation.prompts import (
        CHAPTER_DETECTION_SYSTEM,
        CHAPTER_DETECTION_USER,
    )
    import json

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    user_content = CHAPTER_DETECTION_USER.replace("{pages_text}", pages_text).replace(
        "{total_pages}", str(total_pages)
    )
    messages = [
        SystemMessage(content=CHAPTER_DETECTION_SYSTEM),
        HumanMessage(content=user_content),
    ]
    response = llm.invoke(messages)
    raw = response.content.strip()

    # Limpiar markdown si viene envuelto
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("[run_llm_chapter_detection] JSON inválido: %s — raw: %s", exc, raw[:200])
        return []


def run_llm_requirements_from_chapter(chapter_text: str, chapter_title: str) -> "GeneralRequirementList":
    """
    Extrae requerimientos de un capítulo completo del pliego.
    Igual que run_llm_general_requirements pero con prompt adaptado a capítulo único.
    """
    from tendermod.evaluation.schemas import GeneralRequirementList
    from tendermod.evaluation.prompts import (
        qna_system_message_general_requirements,
        qna_user_message_general_requirements,
    )
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(GeneralRequirementList)
    user_content = (
        qna_user_message_general_requirements
        .replace("{context}", chapter_text)
        .replace("{question}", f"requerimientos en el capítulo: {chapter_title}")
    )
    messages = [
        SystemMessage(content=qna_system_message_general_requirements),
        HumanMessage(content=user_content),
    ]
    return structured_llm.invoke(messages)
```

Agregar `import re` si no existe en `llm_client.py`.

### C.3 Nuevos prompts en `prompts.py`

**Archivo:** `src/tendermod/evaluation/prompts.py` (agregar al final)

```python
CHAPTER_DETECTION_SYSTEM = """Eres un extractor de estructura de documentos de licitación
pública colombiana. Se te darán las primeras páginas de un pliego de condiciones.
Tu tarea es identificar TODOS los capítulos o secciones principales del documento con sus
rangos de página.

Devuelve ÚNICAMENTE JSON válido con esta estructura (páginas en base 1):
[
  {"title": "CAPÍTULO 1 — GENERALIDADES DEL PROCESO", "start_page": 1, "end_page": 9},
  {"title": "2. CONDICIONES DEL PROCESO", "start_page": 10, "end_page": 55},
  {"title": "2.23 Causales de rechazo de la oferta", "start_page": 45, "end_page": 55},
  {"title": "5. HABILITANTES Y EVALUACIÓN", "start_page": 56, "end_page": 95}
]

REGLAS:
- Incluir tanto capítulos principales (nivel 1) como subsecciones importantes (nivel 2–3)
  que contengan: habilitantes, requisitos, causales de rechazo, garantías, evaluación.
- Si el índice del documento menciona páginas exactas, usar esas páginas.
- Si no hay página exacta visible, estimar razonablemente.
- El campo end_page es EXCLUSIVO — la sección termina ANTES de esa página.
- SOLO JSON. Sin texto adicional. Sin markdown."""

CHAPTER_DETECTION_USER = """Total de páginas del documento: {total_pages}

Primeras páginas del pliego (donde suele estar el índice/tabla de contenido):

{pages_text}

Identifica todos los capítulos y secciones con sus rangos de página."""
```

### C.4 Reemplazar `get_general_requirements` en `general_requirements_inference.py`

**Archivo:** `src/tendermod/evaluation/general_requirements_inference.py`

Reemplazar la función `get_general_requirements` con la versión basada en capítulos.
Conservar las imports existentes y añadir las nuevas. La función `ask_pliego` NO cambia
(sigue usando ChromaDB para Q&A interactivo).

```python
import logging
import glob
from pathlib import Path

from tendermod.config.settings import CHROMA_PERSIST_DIR
from tendermod.evaluation.llm_client import (
    run_llm_general_requirements,
    run_llm_requirements_from_chapter,
    run_llm_indices,
)
from tendermod.evaluation.prompts import (
    PLIEGO_QA_SYSTEM_PROMPT,
    qna_user_message_pliego_qa,
)
from tendermod.evaluation.schemas import GeneralRequirementList, GeneralRequirement
from tendermod.ingestion.chapter_extractor import (
    get_chapter_ranges,
    filter_relevant_chapters,
    extract_page_range,
)
from tendermod.ingestion.chunking import chunk_docs
from tendermod.ingestion.pdf_loader import load_docs
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.retriever import create_retriever_experience
from tendermod.retrieval.vectorstore import read_vectorstore
from tendermod.retrieval.context_builder import build_context

logger = logging.getLogger(__name__)

# Límite de tokens por capítulo antes de enviar al LLM.
# gpt-4o-mini soporta 128K; dejamos margen para system prompt + output.
_MAX_CHAPTER_TOKENS = 90_000
_MAX_CHAPTER_CHARS = _MAX_CHAPTER_TOKENS * 4   # aprox 4 chars/token


def _get_pdf_path() -> str:
    """Retorna el path del primer PDF encontrado en data/."""
    chroma_path = Path(CHROMA_PERSIST_DIR)
    data_dir = chroma_path.parent   # data/chroma -> data/
    pdfs = list(data_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No se encontró PDF en {data_dir}")
    return str(pdfs[0])


def get_general_requirements(k: int = 3) -> GeneralRequirementList:
    """
    Extrae requerimientos generales del pliego por capítulos completos.

    Flujo:
    1. Detectar capítulos del PDF (TOC nativo → LLM → heurística).
    2. Filtrar capítulos relevantes (por keywords en título).
    3. Por cada capítulo, extraer texto y llamar al LLM.
    4. Hacer merge deduplicando por (seccion, descripcion[:60]).
    """
    pdf_path = _get_pdf_path()

    chapters = get_chapter_ranges(pdf_path, use_llm=True)
    relevant_chapters = filter_relevant_chapters(chapters)

    if not relevant_chapters:
        logger.warning("[get_general_requirements] No se detectaron capítulos relevantes")
        return GeneralRequirementList(requisitos=[])

    all_requisitos: list[GeneralRequirement] = []
    seen: set[tuple] = set()
    next_id = 1

    for chapter in relevant_chapters:
        title = chapter["title"]
        start = chapter["start_page"]
        end = chapter["end_page"]
        n_pages = end - start

        chapter_text = extract_page_range(pdf_path, start, end)
        n_chars = len(chapter_text)
        n_tokens_est = n_chars // 4

        logger.info(
            "[get_general_requirements] Capítulo '%s' (pág %d–%d, ~%d tokens)",
            title, start + 1, end, n_tokens_est,
        )

        if n_chars > _MAX_CHAPTER_CHARS:
            # Capítulo demasiado largo: dividir en sub-bloques de 90K tokens.
            sub_size = _MAX_CHAPTER_CHARS
            sub_blocks = [
                chapter_text[i: i + sub_size]
                for i in range(0, n_chars, sub_size)
            ]
            logger.info(
                "[get_general_requirements] Capítulo grande → %d sub-bloques", len(sub_blocks)
            )
        else:
            sub_blocks = [chapter_text]

        for block in sub_blocks:
            try:
                partial = run_llm_requirements_from_chapter(block, title)
            except Exception as exc:
                logger.error(
                    "[get_general_requirements] Error en capítulo '%s': %s", title, exc
                )
                continue

            for req in partial.requisitos:
                key = (req.seccion, req.descripcion[:60].lower())
                if key not in seen:
                    seen.add(key)
                    req.id = next_id
                    next_id += 1
                    all_requisitos.append(req)

    logger.info(
        "[get_general_requirements] %d capítulos → %d requerimientos únicos",
        len(relevant_chapters), len(all_requisitos),
    )
    return GeneralRequirementList(requisitos=all_requisitos)


def ask_pliego(question: str, k: int = 8) -> str:
    """Responde preguntas en lenguaje natural sobre el pliego. Retorna string."""
    docs = load_docs()
    chunks = chunk_docs(docs)

    vectorstore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = create_retriever_experience(vectorstore, k)

    context_for_query = build_context(retriever, chunks, question, k=k)

    user_message = qna_user_message_pliego_qa
    user_message = user_message.replace("{context}", context_for_query)
    user_message = user_message.replace("{question}", question)

    response = run_llm_indices(PLIEGO_QA_SYSTEM_PROMPT, user_message)
    return response
```

**Nota importante:** `ask_pliego` conserva ChromaDB/RAG porque el Q&A interactivo se beneficia
del retrieval semántico (no necesita cobertura total del documento, sino respuesta precisa).

**Criterios de aceptación de Fase C:**
- [ ] Para FNA test9.pdf (sin TOC nativo): `get_chapter_ranges_native` retorna `[]`, el LLM fallback detecta al menos 5 capítulos con sus páginas.
- [ ] Para CCENEG-094-01-AMP-2026 (con TOC nativo): `get_chapter_ranges_native` retorna ≥15 entradas incluyendo sección 2.23.x y 5.1.x.
- [ ] `filter_relevant_chapters` selecciona al menos las secciones de habilitantes, causales y evaluación en ambos pliegos.
- [ ] El log muestra "N capítulos → M requerimientos únicos" con M > 50 para el pliego AMP.
- [ ] No hay `ValidationError` en ninguna llamada LLM.

---

## FASE D — Detección robusta de límites de capítulo sin TOC nativo

> **Por qué.** La Fase C asume que el LLM puede detectar capítulos desde las primeras páginas.
> Para pliegos donde el índice es poco claro o está en páginas internas, la detección puede
> fallar o producir rangos incorrectos. Esta fase añade validación y mejora la heurística.

### D.1 Validación de rangos de capítulo

Agregar a `chapter_extractor.py`:

```python
def validate_chapter_ranges(chapters: list[dict], n_total_pages: int) -> list[dict]:
    """
    Valida y corrige rangos detectados:
    - Clamp al rango [0, n_total_pages].
    - Eliminar capítulos con start >= end (vacíos).
    - Ordenar por start_page.
    - Si dos capítulos se solapan, recortar el anterior.
    """
    valid = []
    for ch in chapters:
        start = max(0, min(ch.get("start_page", 0), n_total_pages - 1))
        end = max(start + 1, min(ch.get("end_page", n_total_pages), n_total_pages))
        valid.append({**ch, "start_page": start, "end_page": end})

    valid.sort(key=lambda c: c["start_page"])

    # Recortar solapamientos.
    for i in range(len(valid) - 1):
        if valid[i]["end_page"] > valid[i + 1]["start_page"]:
            valid[i]["end_page"] = valid[i + 1]["start_page"]

    return [ch for ch in valid if ch["start_page"] < ch["end_page"]]
```

Integrar en `get_chapter_ranges`:

```python
def get_chapter_ranges(pdf_path: str, use_llm: bool = True) -> list[dict]:
    doc = fitz.open(pdf_path)
    n_pages = len(doc)
    doc.close()

    chapters = get_chapter_ranges_native(pdf_path)
    if not chapters and use_llm:
        try:
            chapters = get_chapter_ranges_llm(pdf_path)
        except Exception as exc:
            logger.warning("[chapter_extractor] LLM fallback falló: %s — usando heurística", exc)

    if not chapters:
        chapters = get_chapter_ranges_heuristic(pdf_path)

    return validate_chapter_ranges(chapters, n_pages)
```

### D.2 Logging granular por capítulo

En `get_general_requirements` (Fase C.4), agregar al final del loop:

```python
        logger.info(
            "[get_general_requirements] '%s': %d requerimientos (total acumulado: %d)",
            title, len(partial.requisitos) if partial else 0, len(all_requisitos),
        )
```

Esto permite detectar capítulos que no producen resultados (posible gap o capítulo irrelevante).

### D.3 Estrategia de re-intento para capítulos sin resultados

Si un capítulo relevante retorna 0 requerimientos, puede ser porque:
- El capítulo es de tipo introductorio (no tiene requerimientos reales).
- El rango de página está mal detectado.

Agregar a `get_general_requirements` después del loop:

```python
    if len(all_requisitos) < 10:
        logger.warning(
            "[get_general_requirements] Solo %d requisitos extraídos — posible fallo de detección."
            " Intentando extracción sobre capítulos no seleccionados.",
            len(all_requisitos),
        )
        # Re-intentar con los capítulos descartados por filter_relevant_chapters.
        remaining = [ch for ch in chapters if ch not in relevant_chapters]
        for chapter in remaining[:5]:    # Límite de 5 para no disparar costo.
            chapter_text = extract_page_range(pdf_path, chapter["start_page"], chapter["end_page"])
            if len(chapter_text) < 500:   # Capítulo vacío o de portada.
                continue
            try:
                partial = run_llm_requirements_from_chapter(chapter_text, chapter["title"])
                for req in partial.requisitos:
                    key = (req.seccion, req.descripcion[:60].lower())
                    if key not in seen:
                        seen.add(key)
                        req.id = next_id
                        next_id += 1
                        all_requisitos.append(req)
            except Exception as exc:
                logger.warning("[get_general_requirements] Re-intento falló en '%s': %s",
                               chapter["title"], exc)
```

**Criterios de aceptación de Fase D:**
- [ ] `validate_chapter_ranges` normaliza rangos solapados sin pérdida de cobertura.
- [ ] El log reporta cuántos requerimientos produce cada capítulo.
- [ ] Para FNA test9.pdf: el re-intento no se activa (≥10 requisitos en primera pasada).
- [ ] Para AMP CCENEG-094: el re-intento no se activa (≥80 requisitos en primera pasada).

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

**Verificación:** ningún `model_validate_json` en `views.py` ni en `tasks.py` rompe con el
schema expandido. Todos usan `GeneralRequirementList.model_validate_json` que tolera campos
adicionales o faltantes con defaults.

### E.2 Actualizar `analysis_pliego_qa` para nuevas categorías

**Archivo:** `web/apps/analysis/views.py`

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

**Archivo:** `web/apps/analysis/views.py`

Agregar columnas `Tipo` y `Documento/Formato` a la hoja "Checklist General":

```python
# ANTES:
cl_headers = ['#', 'Categoria', 'Descripcion', 'Obligatorio', 'Seccion', 'Pagina', 'Estado', 'Origen']

# DESPUÉS:
cl_headers = ['#', 'Categoria', 'Tipo', 'Descripcion', 'Documento/Formato',
              'Obligatorio', 'Seccion', 'Pagina', 'Estado', 'Origen']

# ANTES:
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

## Impacto arquitectónico: qué cambia y qué no cambia

### ChromaDB — rol reducido para extracción de requerimientos generales

| Feature | Antes | Después |
|---|---|---|
| Extracción requerimientos generales | ChromaDB + RAG | **Extracción directa por capítulos (sin ChromaDB)** |
| Q&A sobre el pliego (`ask_pliego`) | ChromaDB + RAG | ChromaDB + RAG (sin cambio) |
| Extracción indicadores financieros | ChromaDB + RAG | ChromaDB + RAG (sin cambio) |
| Extracción requisitos de experiencia | ChromaDB + RAG | ChromaDB + RAG (sin cambio) |
| Ingesta de experiencia RUP | ChromaDB colección "rup" | ChromaDB colección "rup" (sin cambio) |

ChromaDB sigue siendo necesario. Solo se elimina su uso para la extracción de requerimientos
generales, donde el RAG era el cuello de botella de recall.

### Costo LLM estimado por extracción

| Escenario | Llamadas LLM | Tokens de entrada (est.) | Costo estimado (gpt-4o-mini) |
|---|---|---|---|
| Antes (1 llamada, contexto parcial) | 1 | ~6K tokens | ~$0.001 |
| Después — pliego FNA típico (5 capítulos) | 5 | ~30K tokens | ~$0.006 |
| Después — pliego AMP típico (7 capítulos) | 7 | ~50K tokens | ~$0.010 |
| Después — pliego grande (12 capítulos) | 12 | ~90K tokens | ~$0.018 |

El costo sube de $0.001 a ~$0.01–0.018 por extracción — aceptable dado que se ejecuta
una vez por sesión. El tiempo de extracción sube de ~10s a ~30–60s (5–12 llamadas secuenciales).

### Llamadas paralelas (optimización futura)

Las llamadas LLM por capítulo son independientes entre sí. Para reducir el tiempo de
extracción a ~10–15s, se pueden paralelizar con `asyncio.gather()` o `ThreadPoolExecutor`.
Esta optimización se puede implementar post-validación funcional.

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

No se requiere script de migración de datos.

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

### Métricas operacionales

| Métrica | Límite aceptable |
|---|---|
| Tiempo de extracción (Celery task) | ≤90 segundos |
| Incremento de costo LLM por extracción | ≤20x el costo actual (~$0.02 máximo) |
| `ValidationError` al parsear JSON del LLM | 0 errores en ≥95% de ejecuciones |

---

## Archivos a modificar — resumen

| Archivo | Tipo de cambio | Fase |
|---|---|---|
| `src/tendermod/evaluation/schemas.py` | Expand `GeneralRequirement`: +2 campos, +3 categorías, nuevo Literal `tipo` | A |
| `src/tendermod/evaluation/prompts.py` | Reemplazar `qna_system_message_general_requirements` + agregar `CHAPTER_DETECTION_SYSTEM/USER` | B + C |
| `src/tendermod/ingestion/chapter_extractor.py` | **Archivo nuevo** — detección de capítulos + extracción de texto por rango de página | C + D |
| `src/tendermod/evaluation/llm_client.py` | + `run_llm_chapter_detection()` + `run_llm_requirements_from_chapter()` | C |
| `src/tendermod/evaluation/general_requirements_inference.py` | Reemplazar `get_general_requirements` con versión basada en capítulos (sin ChromaDB) | C + D |
| `web/apps/analysis/views.py` | Nuevas columnas en export Excel; dropdown Q&A | E |
| `web/templates/analysis/step2.html` | Badge por `tipo`, opciones nuevas en dropdown Q&A | E |

**Archivos que NO se modifican:**
- `web/apps/core/models.py` — sin cambio (campo `general_requirements_json` ya existe como `TextField`)
- `web/apps/core/migrations/` — sin nueva migración
- `web/apps/analysis/urls.py` — sin nuevas rutas
- `web/apps/analysis/tasks.py` — la llamada a `get_general_requirements(k=15)` sigue siendo válida; el parámetro `k` se ignora en la nueva implementación (no hay retriever)
- `src/tendermod/retrieval/vectorstore.py` — sin cambio
- `src/tendermod/retrieval/retriever.py` — sin cambio

---

## Orden de implementación (PRs sugeridos)

**PR 1 (Bloqueante, ~3h):** Fase A + Fase B
- Expandir schema (`schemas.py`)
- Reemplazar system prompt (`prompts.py`)
- Verificar que el LLM retorna JSON válido con los nuevos tipos

**PR 2 (~1 día):** Fase C (extracción por capítulos)
- Nuevo `chapter_extractor.py`
- Nuevas funciones en `llm_client.py`
- Nuevos prompts `CHAPTER_DETECTION_SYSTEM/USER`
- Reemplazar `get_general_requirements` en `general_requirements_inference.py`
- Prueba con FNA test9.pdf: verificar que LLM fallback detecta capítulos
- Prueba con CCENEG-094-01-AMP-2026: verificar ≥80 ítems

**PR 3 (~4h):** Fase D (robustez) + Fase E (Django UI)
- `validate_chapter_ranges` y logging granular
- Badge por tipo en `step2.html`
- Nuevas categorías en dropdown Q&A
- Nuevas columnas en export Excel
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

## Anexo — Comportamiento esperado de detección por tipo de pliego

| Tipo de PDF | `get_toc()` | Estrategia activa | Tiempo detección |
|---|---|---|---|
| AMP Colombia Compra Eficiente (bien estructurado) | ≥20 entradas | TOC nativo | <1s |
| FNA test9.pdf (sin outline nativo) | 0 entradas | LLM sobre primeras 10 páginas | ~3s |
| PDF escaneado sin texto embebido | 0 entradas | LLM → posiblemente falla → heurística | ~3s + fallback |
| PDF con índice en páginas 2–4 | 0 entradas (sin outline) | LLM sobre primeras 10 páginas | ~3s |
