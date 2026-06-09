# Arquitectura de extracción de requisitos de pliegos

Documento de referencia para validar e implementar un sistema de extracción de requisitos de pliegos de condiciones inspirado en el enfoque agente + skills de Cowork, integrable en software de licitaciones.

---

## 1. Objetivo

Sustituir el enfoque clásico de "un único prompt al LLM con el pliego entero" por una arquitectura agente con anclaje a la fuente, que produzca un entregable estructurado, auditable y trazable. El sistema debe optimizar tres ejes:

- **Cobertura**: ningún requisito del pliego se pierde.
- **Precisión**: cada requisito refleja literalmente lo que dice el pliego.
- **Trazabilidad**: cada extracción enlaza a la cláusula, página y texto fuente.

---

## 2. Arquitectura de alto nivel

### 2.1 Visión general

El sistema se organiza en cinco capas funcionales, ejecutadas como un pipeline orquestado por un agente.

| Capa | Responsabilidad | Output |
|------|-----------------|--------|
| Ingesta | Recibir el pliego y normalizar el formato | Documento normalizado |
| Parsing determinístico | Extraer texto estructurado con código, no con el LLM | Documento JSON con páginas, cláusulas, tablas |
| Descomposición | Partir el pliego en secciones lógicas y crear plan de tareas | TodoList por sección |
| Extracción anclada | Recorrer el documento sección a sección extrayendo requisitos con cita literal | Requisitos con trazabilidad |
| Verificación y entrega | Subagente verificador + entrega estructurada | XLSX/JSON auditable |

### 2.2 Principios de diseño

1. **Determinismo donde sea posible**: el parsing del PDF/DOCX se hace con librerías, no con el LLM. El LLM solo interpreta texto ya extraído.
2. **Anclaje a la fuente**: cada requisito extraído lleva metadatos de origen (página, cláusula, texto literal).
3. **Descomposición**: nunca un único prompt sobre todo el documento. Siempre sección a sección.
4. **Doble pasada**: un agente extractor y un agente verificador independiente.
5. **Salida estructurada**: el entregable es una tabla auditable, no un texto narrativo.
6. **Idempotencia**: reejecutar el pipeline sobre el mismo pliego produce el mismo resultado.

### 2.3 Diagrama lógico

```
┌──────────────────┐
│  Pliego (PDF)    │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────┐      ┌─────────────────────┐
│  Capa de parsing         │─────▶│  Documento parseado │
│  (pdfplumber, OCR)       │      │  (JSON estructurado)│
└────────┬─────────────────┘      └─────────────────────┘
         │
         ▼
┌──────────────────────────┐      ┌─────────────────────┐
│  Orquestador / Planner   │─────▶│  Plan de tareas     │
│  (clasificación secciones)│      │  (TodoList)         │
└────────┬─────────────────┘      └─────────────────────┘
         │
         ▼
┌──────────────────────────┐      ┌─────────────────────┐
│  Agente extractor        │◀────▶│  Índice de cláusulas│
│  (LLM + grep + citas)    │      │  (búsqueda local)   │
└────────┬─────────────────┘      └─────────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Agente verificador      │
│  (segunda pasada)        │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Capa de entrega         │
│  (XLSX, JSON, API)       │
└──────────────────────────┘
```

### 2.4 Componentes y responsabilidades

| Componente | Tipo | Responsabilidad principal |
|------------|------|---------------------------|
| `IngestService` | Servicio | Recibe el pliego, valida formato, dispara el pipeline |
| `ParserService` | Servicio determinístico | Extrae texto, tablas y estructura del documento |
| `OCRService` | Servicio determinístico | Procesa páginas escaneadas |
| `SectionClassifier` | LLM ligero | Clasifica secciones del pliego |
| `Planner` | Orquestador | Genera el plan de tareas a partir de las secciones |
| `ExtractorAgent` | LLM agente | Extrae requisitos por sección con citas |
| `VerifierAgent` | LLM agente | Revisa la extracción y detecta omisiones |
| `TraceabilityStore` | Base de datos | Almacena requisitos con metadatos de origen |
| `DeliveryService` | Servicio | Genera XLSX/JSON y expone la API |

---

## 3. Arquitectura de bajo nivel

### 3.1 Capa de ingesta

**Responsabilidad**: recibir el archivo, validar y normalizar.

Validaciones mínimas: formato (PDF, DOCX, ODT), tamaño, integridad, detección de PDF escaneado vs. PDF con texto.

Interfaz:

```python
class IngestRequest:
    document_id: str
    file_path: str
    tender_id: str
    metadata: dict

class IngestResponse:
    document_id: str
    normalized_path: str
    document_type: Literal["pdf_text", "pdf_scan", "docx", "odt"]
    page_count: int
    requires_ocr: bool
```

### 3.2 Capa de parsing determinístico

**Responsabilidad**: convertir el documento en una estructura JSON navegable, preservando páginas, cláusulas, tablas y numeración.

Librerías recomendadas:

- `pdfplumber` o `pymupdf` para PDFs con texto.
- `python-docx` para DOCX.
- `tesseract` o `paddleocr` para OCR de PDFs escaneados.
- `camelot` o `tabula-py` para tablas complejas.

Esquema de salida:

```json
{
  "document_id": "uuid",
  "pages": [
    {
      "page_number": 1,
      "text": "...",
      "blocks": [
        {
          "block_id": "p1_b3",
          "type": "paragraph|heading|table|list",
          "text": "...",
          "bbox": [x0, y0, x1, y1],
          "clause_ref": "5.2.1"
        }
      ],
      "tables": [
        {
          "table_id": "p1_t1",
          "rows": [["...", "..."]],
          "headers": ["...", "..."]
        }
      ]
    }
  ],
  "outline": [
    {"clause_ref": "5", "title": "Requisitos técnicos", "page_start": 12, "page_end": 28}
  ]
}
```

Reglas críticas:

- Detectar la numeración de cláusulas con regex (`^\d+(\.\d+)*\s+`).
- Preservar bbox para reconstruir el contexto visual y citas.
- Marcar bloques que requieren OCR si la confianza baja de un umbral.

### 3.3 Capa de descomposición

**Responsabilidad**: clasificar las secciones del pliego y generar el plan de tareas.

Tipos de sección típicos en un pliego de condiciones español:

- Objeto del contrato.
- Requisitos administrativos.
- Solvencia económica y financiera.
- Solvencia técnica o profesional.
- Requisitos técnicos del producto/servicio.
- Criterios de adjudicación.
- Plazos y forma de ejecución.
- Garantías.
- Penalizaciones.
- Documentación a aportar.

Cada sección genera una `ExtractionTask`:

```python
class ExtractionTask:
    task_id: str
    section_type: SectionType
    clause_refs: list[str]
    page_start: int
    page_end: int
    extraction_schema: RequirementSchema
    status: Literal["pending", "in_progress", "extracted", "verified", "failed"]
```

El `SectionClassifier` puede ser un LLM ligero (Haiku) con un prompt corto y few-shot examples, ya que solo clasifica títulos y primeras líneas, no el contenido completo.

### 3.4 Capa de extracción anclada

**Responsabilidad**: recorrer cada `ExtractionTask` y extraer requisitos con cita literal.

Esquema canónico de un requisito:

```json
{
  "requirement_id": "uuid",
  "tender_id": "uuid",
  "section_type": "tecnico",
  "title": "Disponibilidad mínima del servicio",
  "description": "El adjudicatario deberá garantizar una disponibilidad del servicio igual o superior al 99,5% medida en cómputo mensual.",
  "type": "obligatorio|valorable|informativo",
  "category": "SLA",
  "source": {
    "clause_ref": "7.3.2",
    "page": 24,
    "block_id": "p24_b7",
    "literal_text": "El adjudicatario deberá garantizar una disponibilidad...",
    "bbox": [72, 410, 540, 470]
  },
  "evidence_required": ["Memoria técnica con plan de continuidad"],
  "deadline": null,
  "amount": null,
  "confidence": 0.92,
  "extracted_by": "ExtractorAgent v1.2",
  "extracted_at": "2026-05-09T10:32:00Z"
}
```

Prompt al `ExtractorAgent` (resumen de la estructura, no el texto literal completo):

- Recibe **solo la sección** asignada, no todo el pliego.
- Recibe el esquema canónico que debe rellenar.
- Tiene acceso a una herramienta `search_in_section(query)` para verificar literales.
- Debe rechazar requisitos que no pueda anclar a un fragmento literal.
- Sale en JSON estricto validado contra el esquema.

Anti-alucinación:

1. Validación de cita: el `literal_text` debe encontrarse exactamente en el bloque referenciado.
2. Validación de cláusula: el `clause_ref` debe existir en el outline.
3. Si la validación falla, el requisito se descarta y se reintenta o se marca para revisión humana.

### 3.5 Capa de verificación

**Responsabilidad**: una segunda pasada independiente sobre cada sección para detectar omisiones e imprecisiones.

El `VerifierAgent`:

- Recibe la sección original más la lista de requisitos extraídos.
- Su tarea explícita es **encontrar requisitos que falten**, no validar los existentes.
- Devuelve un diff: `missed_requirements`, `imprecise_requirements`, `false_positives`.

Métricas de calidad por sección:

```python
class SectionQualityReport:
    section_type: SectionType
    extracted_count: int
    missed_count: int
    imprecise_count: int
    false_positive_count: int
    coverage_score: float    # 1 - missed / (extracted + missed)
    precision_score: float   # 1 - false_positives / extracted
    requires_human_review: bool
```

Si `coverage_score < 0.95` o `precision_score < 0.9`, la sección se marca para revisión humana antes de la entrega.

### 3.6 Capa de entrega

**Responsabilidad**: producir los entregables finales y exponerlos.

Formatos de salida:

1. **XLSX auditable**, una hoja por sección, columnas: ID, Tipo, Categoría, Requisito, Cláusula, Página, Texto literal, Documentación a aportar, Cumplimiento, Observaciones.
2. **JSON canónico** para integraciones con el software de licitaciones existente.
3. **Resumen ejecutivo** en DOCX con riesgos y requisitos críticos.

API recomendada:

```
POST   /api/v1/tenders/{id}/extract           → lanza pipeline
GET    /api/v1/tenders/{id}/extraction        → estado y progreso
GET    /api/v1/tenders/{id}/requirements      → lista de requisitos
GET    /api/v1/tenders/{id}/requirements/{rid}→ requisito individual con cita
GET    /api/v1/tenders/{id}/quality-report    → métricas de calidad
POST   /api/v1/tenders/{id}/export            → genera XLSX/DOCX
```

---

## 4. Modelo de datos

### 4.1 Entidades principales

```
Tender (1) ─── (N) Document
Document (1) ─── (N) Section
Section (1) ─── (N) Requirement
Requirement (1) ─── (1) Source
Section (1) ─── (1) QualityReport
ExtractionRun (1) ─── (N) AgentExecution
```

### 4.2 Tabla `requirements` (esquema mínimo)

| Columna | Tipo | Descripción |
|---------|------|-------------|
| id | UUID PK | Identificador del requisito |
| tender_id | UUID FK | Licitación asociada |
| document_id | UUID FK | Documento de origen |
| section_type | ENUM | Tipo de sección |
| title | VARCHAR | Título corto |
| description | TEXT | Descripción normalizada |
| type | ENUM | obligatorio / valorable / informativo |
| category | VARCHAR | Categoría libre (SLA, garantía, etc.) |
| clause_ref | VARCHAR | Cláusula del pliego |
| page | INT | Página de origen |
| literal_text | TEXT | Texto literal citado |
| bbox | JSONB | Coordenadas del bloque |
| evidence_required | JSONB | Documentación a aportar |
| deadline | DATE | Plazo si aplica |
| amount | NUMERIC | Importe si aplica |
| confidence | NUMERIC | 0–1 |
| extraction_run_id | UUID FK | Ejecución que lo generó |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

---

## 5. Orquestación

### 5.1 Estados del pipeline

```
INGESTED → PARSED → CLASSIFIED → EXTRACTING → VERIFYING → DELIVERABLE_READY
                              │            │
                              └─ FAILED ───┘
```

### 5.2 Concurrencia

Las secciones son independientes, por lo que la extracción y verificación se pueden paralelizar por sección. Recomendación: pool de workers con límite por tenant para controlar coste de tokens.

### 5.3 Reintentos y degradación

- Reintento automático con backoff si el `ExtractorAgent` devuelve JSON inválido.
- Si falla 3 veces, la sección se marca como `requires_human_review`.
- Si el OCR tiene confianza baja en una página, se notifica al usuario antes de extraer.

---

## 6. Validación de la mejora

### 6.1 Métricas objetivo

Antes de migrar producción, fijar baseline con el sistema actual sobre un set representativo de pliegos.

| Métrica | Definición | Objetivo |
|---------|------------|----------|
| Cobertura | requisitos detectados / requisitos reales (gold set) | ≥ 0,97 |
| Precisión | requisitos correctos / requisitos detectados | ≥ 0,95 |
| Trazabilidad | requisitos con cita verificable / total | 1,00 |
| Tasa de alucinación | requisitos sin cita válida / total | ≤ 0,01 |
| Tiempo medio por pliego | minutos por pliego de 100 páginas | ≤ 10 min |
| Coste por pliego | tokens × tarifa | medir y reducir 30% iter. |

### 6.2 Gold set

Construir un dataset de **20–30 pliegos representativos** anotados manualmente por expertos en licitaciones. Cada pliego anotado incluye la lista canónica de requisitos esperados con su cláusula y texto literal. Este gold set es la referencia para todas las métricas.

### 6.3 Procedimiento de validación

1. Ejecutar el sistema actual sobre el gold set, registrar métricas.
2. Ejecutar el sistema nuevo sobre el gold set, registrar métricas.
3. Comparar por sección y por tipo de requisito.
4. Validar muestreo manual con expertos sobre 10% de los requisitos extraídos.
5. Aceptación si se cumplen todos los objetivos de la tabla 6.1.

### 6.4 Criterios de aceptación para producción

- Todas las métricas objetivo cumplidas en el gold set.
- Test de regresión automático sobre 5 pliegos canary cada release.
- Panel de observabilidad con métricas por ejecución.
- Plan de rollback documentado.

---

## 7. Roadmap de implementación

### Fase 1 — Cimientos (3–4 semanas)

- Capa de ingesta y parsing con pdfplumber + OCR.
- Esquema canónico de requisitos y modelo de datos.
- Construcción del gold set inicial (10 pliegos).

### Fase 2 — Extracción agente (4–6 semanas)

- `SectionClassifier` y `Planner`.
- `ExtractorAgent` con esquema estricto y validación de citas.
- Pipeline secuencial end-to-end sobre 1 pliego.

### Fase 3 — Verificación y calidad (3–4 semanas)

- `VerifierAgent` y métricas por sección.
- Paralelización por sección.
- Panel de observabilidad.

### Fase 4 — Entrega e integración (3 semanas)

- Generación XLSX/DOCX.
- API REST para el software de licitaciones.
- Flujo de revisión humana para secciones marcadas.

### Fase 5 — Hardening (2–3 semanas)

- Optimización de coste de tokens.
- Caching y reuso entre pliegos similares.
- Pruebas de carga.

---

## 8. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| PDFs con texto en imágenes mal escaneadas | OCR con detección de confianza y aviso al usuario |
| Pliegos muy heterogéneos por organismo | Plantillas de clasificación por entidad emisora |
| Coste de tokens elevado | Modelo ligero para clasificación, caching de secciones repetidas |
| Cambios en estructura del pliego entre revisiones | Pipeline idempotente con re-extracción incremental |
| Alucinaciones residuales | Validación de cita literal obligatoria; descartar lo no anclable |
| Latencia en pliegos grandes | Paralelización por sección y ejecución asíncrona |

---

## 9. Decisiones de arquitectura abiertas

Listado de decisiones a confirmar antes de implementar:

1. ¿Modelo único para extractor y verificador, o modelos distintos para diversidad?
2. ¿Almacenamiento de citas con bbox para reconstrucción visual o solo texto literal?
3. ¿Persistencia de los pliegos parseados como caché reutilizable?
4. ¿Integración como microservicio independiente o como módulo del software de licitaciones?
5. ¿Soporte multilingüe inicial o solo español?
6. ¿Flujo de feedback humano que retroalimente el gold set?

---

## 10. Próximos pasos sugeridos

- Validar este documento con el equipo de licitaciones y el equipo técnico.
- Construir el gold set inicial sobre 10 pliegos reales.
- Prototipar la fase 1 sobre un pliego representativo.
- Definir los KPIs concretos de éxito para la dirección.
