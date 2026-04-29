# Plan de Mejora — Extracción de Requisitos Habilitantes (Tendermod)

> **Contexto.** Tendermod usa RAG sobre PDFs de pliegos colombianos para extraer requisitos habilitantes. La cobertura actual es incompleta: faltan ~15% de habilitantes jurídicos, hay sub-extracción en técnicos (no detalla perfiles), y se confunden secciones habilitantes (4.1.x) con ponderables (4.2.x). El cuello de botella es el **retrieval**, no el LLM. Este plan ordena las mejoras de mayor a menor impacto.
>
> **Archivos clave:**
> - `src/tendermod/evaluation/prompts.py` (línea 266 system prompt, línea 310 user prompt)
> - `src/tendermod/evaluation/general_requirements_inference.py` (3 queries de búsqueda)
>
> **Objetivo global:** llegar a ≥95% de recall de habilitantes en pliegos típicos del FNA / Colombia Compra Eficiente, manteniendo precisión ≥90%.

---

## Resumen ejecutivo

| Fase | Nombre | Impacto | Esfuerzo | Tiempo estimado |
|---|---|---|---|---|
| 1 | Expansión de queries + endurecimiento del prompt | **Alto** | Bajo | 2–3 h |
| 2 | Pasada de auto-crítica / verificación de completitud | **Alto** | Bajo-medio | 3–4 h |
| 3 | Chunking jerárquico con breadcrumb de sección | Alto | Medio | 1 día |
| 4 | Extracción en dos pasadas (TOC → secciones) | Medio-alto | Medio-alto | 1–2 días |
| 5 | Modo full-context (long-context) opcional | Medio | Bajo | 0.5 día |

---

## FASE 1 — Expansión de queries y endurecimiento del prompt

> **Por qué primero.** Resuelve ~80% de los huecos detectados con dos archivos editados y cero cambios arquitectónicos.

### 1.1 Reemplazar las 3 queries genéricas por 24 queries específicas

**Archivo:** `src/tendermod/evaluation/general_requirements_inference.py`

**Antes** (las 3 queries actuales son demasiado genéricas y dejan fuera términos como *fabricante*, *Habeas Data*, *transaccional*, *manifestación de aceptación*).

**Después:**

```python
# src/tendermod/evaluation/general_requirements_inference.py

HABILITANTES_QUERIES: list[str] = [
    # --- JURÍDICOS (4.1.1.x) ---
    "carta presentación propuesta firma representante legal declaración juramento",
    "certificado existencia representación legal cámara comercio objeto social",
    "documento identificación cédula ciudadanía representante legal",
    "constitución consorcio unión temporal porcentaje participación integrantes",
    "registro único proponentes RUP inscripción vigente firme",
    "registro único tributario RUT DIAN",
    "garantía seriedad oferta póliza valor presupuesto oficial",
    "certificación pagos seguridad social parafiscales aportes salud pensión ARL SENA ICBF",
    "antecedentes fiscales contraloría general república boletín responsables",
    "antecedentes disciplinarios procuraduría SIRI sistema información sanciones",
    "antecedentes judiciales policía nacional ministerio defensa",
    "medidas correctivas registro nacional código nacional policía convivencia",
    "deudores alimentarios morosos REDAM",
    "compromiso anticorrupción transparencia ética pública",
    "autorización notificación electrónica comunicaciones",
    "acuerdo confidencialidad información reservada",
    "lavado activos financiación terrorismo SARLAFT participación accionaria beneficiario final",
    "poder apoderado facultades suscribir presentación personal",
    "habeas data autorización tratamiento datos personales Ley 1581",
    "firma transaccional SECOP plataforma electrónica suscripción contrato",

    # --- TÉCNICOS (4.1.2.x) ---
    "certificación fabricante distribuidor partner canal autorizado solución",
    "manifestación aceptación requerimientos mínimos obligatorios anexo técnico",
    "personal mínimo requerido perfiles profesional especialista tecnólogo experiencia certificaciones",
    "experiencia general específica habilitante contratos UNSPSC clasificador bienes servicios",
]

# Mantener compatibilidad con código existente: la query "agregada"
# se construye uniendo las queries específicas con separador.
def build_general_requirements_query() -> str:
    return " | ".join(HABILITANTES_QUERIES)
```

**Acción para Claude Code:**
1. Localiza las 3 queries actuales en `general_requirements_inference.py` y reemplázalas por la lista anterior.
2. Si el retriever acepta múltiples queries en paralelo, **ejecuta una llamada por query** (recomendado) en lugar de concatenar. Aumenta `top_k` por query a 3–5 chunks.
3. Deduplica los chunks recuperados antes de enviar al LLM (por hash del texto o por `chunk_id`).

**Criterios de aceptación:**
- [ ] El módulo expone `HABILITANTES_QUERIES` con ≥24 queries.
- [ ] El retriever ejecuta una búsqueda por query y deduplica resultados.
- [ ] En el pliego de prueba `FNA-VTTD-CP-002-2026`, los chunks recuperados incluyen las secciones 4.1.1.18, 4.1.1.19, 4.1.1.20, 4.1.2.1 (certificación fabricante) y 4.1.2.2.

---

### 1.2 Endurecer el system prompt: anti-alucinación de sección y separación habilitante/ponderable

**Archivo:** `src/tendermod/evaluation/prompts.py` (línea 266 aprox.)

Agregar al final del system prompt actual el siguiente bloque:

```text
REGLAS CRÍTICAS DE EXTRACCIÓN:

1) NUMERAL DE SECCIÓN (anti-alucinación):
   - Para cada requisito, el campo "seccion" DEBE ser el numeral exacto
     que aparece literalmente en el contexto (ej. "4.1.1.18", "4.1.2.2").
   - Si el contexto recibido NO contiene un numeral visible que ancle el
     requisito, devuelve "seccion": "N/A".
   - JAMÁS infieras, completes ni inventes un número de sección.

2) HABILITANTE vs PONDERABLE (anti-confusión):
   - HABILITANTES están en el Capítulo 4.1 (4.1.1.x jurídicos, 4.1.2.x
     técnicos, 4.1.3.x financieros). Son cumple / no cumple.
   - PONDERABLES están en el Capítulo 4.2.x. Otorgan PUNTAJE.
   - Si el texto contiene "puntaje", "puntos", "asignación de puntaje",
     "máximo X puntos" → es PONDERABLE. NO lo incluyas en este checklist.
   - Si dudas entre ambos, prefiere NO incluirlo y márcalo en un campo
     "warnings" del JSON.

3) CITA LITERAL OBLIGATORIA:
   - Cada requisito extraído debe incluir "cita_literal": una frase corta
     textual del contexto (≤200 caracteres) que lo justifique.
   - Si no puedes citar literalmente, NO extraigas el requisito.

4) FORMATOS:
   - Si el requisito menciona "FORMATO No. X", inclúyelo en el campo
     "formato": "FORMATO No. X". Si no lo menciona, "formato": null.

5) GRANULARIDAD:
   - Cada requisito numerado (4.1.1.1, 4.1.1.2, …) es UN ítem separado,
     incluso si comparten párrafo. NO los agrupes.
   - Si una sección define varios sub-requisitos (ej. perfiles de personal
     en 4.1.2.3 con Especialista + Tecnólogo), cada perfil es un ítem.
```

**Acción para Claude Code:**
1. Abre `src/tendermod/evaluation/prompts.py`.
2. Localiza la constante `qna_system_message_general_requirements` (línea ~266).
3. Inyecta el bloque anterior antes del cierre del prompt y antes de la instrucción anti-markdown.
4. Asegúrate de que el JSON de salida documentado incluye los nuevos campos: `seccion`, `cita_literal`, `formato`, `warnings`.

**Criterios de aceptación:**
- [ ] El prompt incluye las 5 reglas explícitas.
- [ ] El esquema JSON de respuesta documenta los campos `seccion`, `cita_literal`, `formato`, `warnings`.
- [ ] En la prueba con FNA, NO aparece "ISO 9001/45001" mislabeleado como 4.1.2.1.

---

### 1.3 Test de regresión

**Archivo nuevo:** `tests/evaluation/test_phase1_recall.py`

```python
"""Test de recall mínimo tras Fase 1.

El pliego FNA-VTTD-CP-002-2026 debe extraer estos habilitantes obligatorios.
"""
EXPECTED_HABILITANTES_FNA = {
    "4.1.1.1", "4.1.1.2", "4.1.1.3", "4.1.1.4", "4.1.1.5",
    "4.1.1.6", "4.1.1.7", "4.1.1.8", "4.1.1.9", "4.1.1.10",
    "4.1.1.11", "4.1.1.12", "4.1.1.13", "4.1.1.14", "4.1.1.15",
    "4.1.1.16", "4.1.1.17", "4.1.1.18", "4.1.1.19", "4.1.1.20",
    "4.1.2.1", "4.1.2.2", "4.1.2.3", "4.1.2.4",
}

def test_recall_habilitantes_fna(extraction_result):
    extracted_sections = {item["seccion"] for item in extraction_result}
    missing = EXPECTED_HABILITANTES_FNA - extracted_sections
    assert not missing, f"Faltantes tras Fase 1: {sorted(missing)}"
```

**Definition of done de la Fase 1:**
- [ ] Los 24 habilitantes del pliego FNA-VTTD-CP-002-2026 aparecen en el resultado.
- [ ] No hay items mislabeleados con secciones del Capítulo 4.2.
- [ ] El test `test_recall_habilitantes_fna` pasa.

---

## FASE 2 — Pasada de auto-crítica / verificación de completitud

> **Por qué.** Garantiza recall cerca del 100% incluso cuando el retriever falle, usando el conocimiento del LLM sobre la estructura típica de pliegos colombianos.

### 2.1 Nuevo módulo: `verifier.py`

**Archivo nuevo:** `src/tendermod/evaluation/verifier.py`

```python
"""Pasada de auto-crítica que verifica completitud y dispara re-retrieval.

Funciona en dos llamadas:
1. critique(): el LLM revisa la lista extraída y reporta faltantes + queries sugeridas.
2. re_extract(): si hay faltantes, se hace retrieval con las nuevas queries y
   se extraen los requisitos que faltaban.
"""

from typing import Any
import json

CRITIQUE_SYSTEM = """Eres un auditor de extracciones de pliegos colombianos.
Conoces la estructura típica de requisitos habilitantes en contratación pública
(Manuales de Contratación de entidades como FNA, Colombia Compra Eficiente,
Decreto 1082 de 2015).

Habilitantes JURÍDICOS típicos (no exhaustivo):
- Carta de presentación
- Certificado existencia y representación legal
- Documento identificación rep. legal
- Constitución consorcio/UT (si aplica)
- RUP, RUT
- Garantía de seriedad
- Pagos seguridad social y parafiscales
- Antecedentes fiscales (Contraloría)
- Antecedentes disciplinarios (Procuraduría / SIRI)
- Antecedentes judiciales (Policía)
- Medidas correctivas
- REDAM
- Compromiso anticorrupción
- Autorización notificación electrónica
- Acuerdo de confidencialidad
- Prevención lavado de activos / SARLAFT
- Poder (si aplica apoderado)
- Habeas Data / autorización tratamiento datos personales
- Firma transaccional SECOP II

Habilitantes TÉCNICOS típicos:
- Certificación de fabricante (cuando se contratan equipos/marcas)
- Manifestación de aceptación de requerimientos mínimos
- Personal mínimo (perfiles + experiencia + certificaciones)
- Experiencia general y específica del oferente

FORMATOS típicos: FORMATO No. 1 a FORMATO No. ~24 (numeración varía por pliego).

Tarea: dada una lista de requisitos extraídos, identifica posibles faltantes
y sugiere queries de búsqueda específicas para recuperarlos."""

CRITIQUE_USER = """Lista de requisitos extraídos:
{extracted_json}

Devuelve EXCLUSIVAMENTE un JSON válido con esta estructura:
{{
  "faltantes_probables": [
    {{
      "nombre_tentativo": "Autorización tratamiento de datos personales",
      "categoria": "JURIDICO",
      "razon": "No aparece y es estándar en pliegos colombianos",
      "query_sugerida": "habeas data autorización datos personales Ley 1581"
    }}
  ],
  "duplicados": [],
  "sospechosos_mal_clasificados": [
    {{
      "item_id": 18,
      "razon": "Descripción habla de ISO 9001 con puntaje, parece ponderable y no habilitante"
    }}
  ]
}}"""


def critique_extraction(llm_client, extracted: list[dict]) -> dict:
    """Ejecuta la auto-crítica y devuelve el JSON con faltantes sugeridos."""
    response = llm_client.complete(
        system=CRITIQUE_SYSTEM,
        user=CRITIQUE_USER.format(extracted_json=json.dumps(extracted, ensure_ascii=False)),
        temperature=0.0,
        response_format="json",
    )
    return json.loads(response)


def fill_gaps(llm_client, retriever, extracted: list[dict], critique: dict) -> list[dict]:
    """Para cada faltante, hace re-retrieval con su query_sugerida y extrae."""
    new_items: list[dict] = []
    for gap in critique.get("faltantes_probables", []):
        chunks = retriever.search(gap["query_sugerida"], top_k=5)
        if not chunks:
            continue
        # Usar el extractor existente con el contexto enfocado
        items = extract_from_chunks(llm_client, chunks)
        new_items.extend(items)
    return dedupe_by_section(extracted + new_items)
```

**Integración en el pipeline existente:**

```python
# src/tendermod/evaluation/general_requirements_inference.py (al final del flujo)

def run_extraction(pdf_path: str) -> list[dict]:
    chunks = retrieve_for_all_queries(pdf_path)
    extracted = extract_with_llm(chunks)              # pasada principal (Fase 1)
    critique = critique_extraction(llm, extracted)    # NUEVO (Fase 2)
    if critique.get("faltantes_probables"):
        extracted = fill_gaps(llm, retriever, extracted, critique)
    return extracted
```

**Criterios de aceptación:**
- [ ] `verifier.py` expone `critique_extraction()` y `fill_gaps()`.
- [ ] La auto-crítica devuelve JSON válido y los faltantes aterrizan en re-retrieval.
- [ ] El pipeline corre con 1 sola llamada extra al LLM si no hay faltantes (early-exit).
- [ ] El log muestra cuántos faltantes detectó la crítica y cuántos se rescataron.

**Definition of done de la Fase 2:**
- [ ] En el pliego FNA, si artificialmente se sabotea la Fase 1 quitando una query, la Fase 2 recupera el requisito faltante.
- [ ] El campo `sospechosos_mal_clasificados` se loguea como warning para revisión humana.

---

## FASE 3 — Chunking jerárquico con breadcrumb de sección

> **Por qué.** Resuelve la mis-atribución de numerales (el caso "4.2.2.1 ISO" mislabeleado como "4.1.2.1") inyectando metadata estructural en cada chunk.

### 3.1 Detector de jerarquía de secciones

**Archivo nuevo:** `src/tendermod/ingestion/section_parser.py`

```python
"""Parser de jerarquía de secciones para pliegos colombianos.

Detecta encabezados con patrones tipo:
- "CAPÍTULO PRIMERO", "CAPÍTULO SEGUNDO", ...
- "4.1.1.18 PODER" (numeración multinivel)
- "4.2.2.1 PLAN DE ASEGURAMIENTO..."
"""

import re
from dataclasses import dataclass

CHAPTER_RE = re.compile(r"^CAP[IÍ]TULO\s+(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|\w+)",
                        re.IGNORECASE | re.MULTILINE)
NUMBERED_RE = re.compile(r"^\s*(\d+(?:\.\d+){1,4})\.?\s+([A-ZÁÉÍÓÚÑ][^\n]{3,120})$",
                         re.MULTILINE)

@dataclass
class Section:
    number: str            # "4.1.1.18"
    title: str             # "PODER"
    chapter: str           # "CAPÍTULO CUARTO"
    page: int
    breadcrumb: str        # "Capítulo Cuarto > 4.1 > 4.1.1 > 4.1.1.18 PODER"
    char_start: int
    char_end: int

def parse_sections(full_text: str, page_map: dict[int, int]) -> list[Section]:
    """Recorre el texto completo y devuelve la lista ordenada de secciones."""
    # ... implementación que rellena breadcrumb usando jerarquía por puntos.
    ...
```

### 3.2 Chunker que respeta secciones

**Archivo a modificar:** `src/tendermod/ingestion/chunker.py` (o equivalente)

Cada chunk debe llevar metadata estructural y un encabezado embebido:

```python
def make_chunks(sections: list[Section], full_text: str, max_tokens: int = 800) -> list[Chunk]:
    chunks = []
    for section in sections:
        body = full_text[section.char_start:section.char_end]
        for sub in split_by_tokens(body, max_tokens=max_tokens, overlap=80):
            header = (
                f"[SECCIÓN {section.number}: {section.title}]\n"
                f"[BREADCRUMB: {section.breadcrumb}]\n"
                f"[PÁGINA: {section.page}]\n\n"
            )
            chunks.append(Chunk(
                text=header + sub,
                metadata={
                    "section_number": section.number,
                    "section_title": section.title,
                    "breadcrumb": section.breadcrumb,
                    "chapter": section.chapter,
                    "page": section.page,
                    "is_habilitante": section.number.startswith("4.1."),
                    "is_ponderable": section.number.startswith("4.2."),
                }
            ))
    return chunks
```

### 3.3 Re-indexar el corpus existente

**Acción para Claude Code:**
1. Implementa `section_parser.py` y modifica el chunker.
2. Agrega un script `scripts/reindex_corpus.py` que reprocese los PDFs ya cargados.
3. Verifica que la metadata `section_number` y `breadcrumb` esté disponible en los retrievers (ej. en payload del vector store).

**Criterios de aceptación:**
- [ ] Cada chunk tiene metadata estructural correcta.
- [ ] El header `[SECCIÓN 4.1.1.18: PODER]` aparece en el texto del chunk.
- [ ] Test unitario: dado un PDF con sección "4.1.1.18 PODER", el chunk respectivo tiene `section_number == "4.1.1.18"`.

**Definition of done de la Fase 3:**
- [ ] El LLM ya no inventa numerales: extrae `seccion` desde el header del chunk.
- [ ] Filtros por metadata permiten ejecutar consultas tipo `is_habilitante=True` para acotar el universo.

---

## FASE 4 — Extracción en dos pasadas (TOC outline → secciones dirigidas)

> **Por qué.** Pasa de "esperamos que el retriever encuentre todo" a "sabemos exactamente qué secciones existen y extraemos cada una".

### 4.1 Extractor de Tabla de Contenido

**Archivo nuevo:** `src/tendermod/ingestion/toc_extractor.py`

```python
"""Extrae la Tabla de Contenido del pliego para enumerar secciones canónicas."""

TOC_SYSTEM = """Extrae la Tabla de Contenido del pliego. Para cada entrada,
devuelve numeral, título, página. Devuelve JSON: [{"number": "4.1.1.18",
"title": "PODER", "page": 51}, ...]. SOLO incluye entradas con numeración."""

def extract_toc(pdf_first_pages_text: str, llm_client) -> list[dict]:
    """Ejecuta el LLM solo sobre las primeras 5–8 páginas (que tienen el TOC)."""
    ...
```

### 4.2 Extracción dirigida por sección

**Archivo a modificar:** `src/tendermod/evaluation/general_requirements_inference.py`

```python
def run_extraction_v2(pdf_path: str) -> list[dict]:
    # 1. Outline desde TOC
    toc = extract_toc(read_first_pages(pdf_path), llm)
    target_sections = [
        s for s in toc
        if s["number"].startswith("4.1.")  # solo habilitantes
    ]

    # 2. Por cada sección, retrieval dirigido + extracción
    results = []
    for section in target_sections:
        query = f"{section['number']} {section['title']}"
        chunks = retriever.search(
            query=query,
            top_k=5,
            filter={"section_number": section["number"]},  # usa metadata Fase 3
        )
        item = extract_single_section(llm, section, chunks)
        if item:
            results.append(item)

    # 3. Auto-crítica final (Fase 2)
    return apply_critique_pass(results)
```

**Criterios de aceptación:**
- [ ] El TOC se extrae correctamente (≥95% de las secciones reales del pliego).
- [ ] La extracción dirigida usa metadata `section_number` para filtrar.
- [ ] Si una sección del TOC no produce extracción, se loguea como warning.

**Definition of done de la Fase 4:**
- [ ] Recall ≥98% en el pliego FNA-VTTD-CP-002-2026.
- [ ] Test sobre 3 pliegos distintos (FNA + 2 más) con recall ≥95% cada uno.

---

## FASE 5 — Modo full-context (long-context) opcional

> **Por qué.** Para pliegos ≤200 páginas, mandar el PDF completo a Claude Sonnet 4.5 (200K tokens) elimina por completo el problema de retrieval. Cuesta más por extracción pero es la línea base de máxima calidad para validación / golden dataset.

### 5.1 Nuevo entrypoint

**Archivo nuevo:** `src/tendermod/evaluation/full_context_inference.py`

```python
"""Modo full-context: envía el PDF completo al LLM, sin RAG.

Útil para:
- Generar golden dataset de validación.
- Procesar pliegos críticos donde la cobertura debe ser máxima.
- Comparar contra el resultado del pipeline RAG (regression testing).
"""

def extract_full_context(pdf_path: str, llm_client) -> list[dict]:
    pdf_bytes = read_pdf_as_bytes(pdf_path)
    response = llm_client.complete_with_pdf(
        system=qna_system_message_general_requirements,  # mismo prompt
        pdf=pdf_bytes,
        user="Extrae TODOS los requisitos habilitantes del Capítulo 4.1 del pliego.",
        max_tokens=8000,
        temperature=0.0,
    )
    return json.loads(response)
```

### 5.2 Modo dual configurable

```python
# config.yaml
extraction:
  mode: "rag"          # "rag" | "full_context" | "hybrid"
  full_context_max_pages: 200
  hybrid_validate_against_full: false   # corre ambos y compara
```

**Criterios de aceptación:**
- [ ] Flag de configuración para alternar modo.
- [ ] Modo `hybrid` corre ambos y reporta diff (ítems en uno y no en el otro).
- [ ] Documentación de costo aproximado por extracción.

**Definition of done de la Fase 5:**
- [ ] El modo full-context produce el mismo resultado que la extracción manual de referencia (golden) en ≥95% de los ítems.

---

## Anexo A — Tests de regresión sugeridos

```
tests/
├── fixtures/
│   ├── FNA-VTTD-CP-002-2026.pdf
│   └── golden/
│       └── FNA-VTTD-CP-002-2026.json    # 24 habilitantes esperados
├── evaluation/
│   ├── test_phase1_recall.py            # Fase 1
│   ├── test_phase2_critique.py          # Fase 2
│   └── test_phase4_targeted.py          # Fase 4
└── ingestion/
    ├── test_section_parser.py           # Fase 3
    └── test_toc_extractor.py            # Fase 4
```

## Anexo B — Métricas a monitorear

| Métrica | Meta tras Fase 1 | Meta tras Fase 2 | Meta tras Fase 4 |
|---|---|---|---|
| Recall habilitantes | ≥85% | ≥95% | ≥98% |
| Precisión (no incluir ponderables) | ≥90% | ≥95% | ≥98% |
| % secciones correctamente atribuidas | ≥80% | ≥85% | ≥99% |
| Costo LLM por extracción (USD) | +20% vs hoy | +30% vs hoy | +50% vs hoy |

## Anexo C — Orden de ejecución sugerido para Claude Code

1. **PR 1**: Fase 1.1 (queries) + Fase 1.2 (prompt) + Fase 1.3 (test). Mergeable en un día.
2. **PR 2**: Fase 2 completa (verifier + integración).
3. **PR 3**: Fase 3 (chunking jerárquico + reindex).
4. **PR 4**: Fase 4 (TOC + extracción dirigida).
5. **PR 5**: Fase 5 (modo full-context, opcional).

Cada PR debe pasar el test de la fase anterior antes de mergearse.
