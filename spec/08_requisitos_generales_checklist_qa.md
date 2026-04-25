# Spec 08 — Requisitos Generales: Checklist + Q&A del Pliego

## Problema

Los pliegos colombianos contienen tres categorías de requisitos. El sistema actualmente cubre dos:

| Ya cubierto | Pendiente |
|---|---|
| Indicadores financieros (RAG → SQLite) | Requisitos habilitantes generales |
| Experiencia UNSPSC (RAG → SQLite) | Documentos, certificaciones, garantías, seguros, personal |

No existe extracción estructurada de los demás requisitos habilitantes: "adjuntar cámara de comercio", "certificación ISO 9001", "póliza de seriedad", "personal mínimo requerido", etc.

Problema derivado: la app no tiene contexto de si la empresa posee esos requisitos, por lo que **no puede validarlos automáticamente**. La solución MVP delega la validación al usuario mediante un checklist editable.

---

## Decisiones arquitecturales

**Persistencia**: `general_requirements_json` va en `AnalysisSession` (consistente con `experience_requirements_json` e `indicators_requirements_json`). Los estados editados por el usuario se guardan en el mismo JSON, actualizando el campo `estado` por requisito. No requiere `AnalysisResult`.

**Q&A**: Se ejecuta síncronamente en el request (sin Celery). Es una consulta RAG + LLM liviana (~5-10s). Reutiliza el retriever existente sobre `chroma/` (pliego).

**Excel**: La hoja "Checklist General" se genera desde `session.general_requirements_json` directamente — permite exportar aunque no haya evaluación de experiencia/indicadores completada.

---

## Checklist de impacto por archivo

| Archivo | Tipo | Cambio |
|---|---|---|
| `src/tendermod/evaluation/schemas.py` | Modificar | + `GeneralRequirement`, `GeneralRequirementList` |
| `src/tendermod/evaluation/prompts.py` | Modificar | + `qna_system_message_general_requirements`, `PLIEGO_QA_SYSTEM_PROMPT` |
| `src/tendermod/evaluation/general_requirements_inference.py` | **Nuevo** | `get_general_requirements(k)`, `ask_pliego(question, k)` |
| `web/apps/core/models.py` | Modificar | + `general_requirements_json: TextField` en `AnalysisSession` |
| `web/apps/core/migrations/0004_*.py` | **Nuevo** | Migración del campo |
| `web/apps/analysis/tasks.py` | Modificar | + `extract_general_requirements_task` |
| `web/apps/analysis/views.py` | Modificar | + dispatch en `analysis_extract`, + `analysis_pliego_qa`, + `analysis_checklist_save`, render en `step2`/`results`/`export_excel` |
| `web/apps/analysis/urls.py` | Modificar | + 2 rutas nuevas |
| `web/templates/analysis/step1.html` | Modificar | + card extracción Requisitos Generales |
| `web/templates/analysis/step2.html` | Modificar | + tab "Requisitos Generales" + panel Q&A |
| `web/templates/analysis/results.html` | Modificar | + sección checklist con badges de estado |

---

## Sprint 1 — Backend base

### 1.1 `evaluation/schemas.py`

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

class GeneralRequirementList(BaseModel):
    requisitos: List[GeneralRequirement] = []
```

El campo `origen` distingue requisitos extraídos automáticamente de los añadidos por Q&A o manualmente — útil para auditoría y para la Fase 2.

### 1.2 `evaluation/prompts.py`

**`qna_system_message_general_requirements`** — prompt de extracción:

```
Eres un asistente especializado en contratación pública colombiana.
Extrae TODOS los requisitos habilitantes del pliego de condiciones,
EXCLUYENDO indicadores financieros (liquidez, endeudamiento, rentabilidad, capital)
y requisitos de experiencia UNSPSC (ya se procesan por separado).

Categorías a extraer:
- JURIDICO: RUP vigente, cámara de comercio, certificados tributarios, antecedentes judiciales
- TECNICO: certificaciones ISO, acreditaciones, equipos, software específico
- DOCUMENTACION: pólizas, garantías, formularios, cartas de presentación
- CAPACIDAD: personal mínimo, directores de obra, estructura organizacional
- FINANCIERO_OTRO: patrimonio líquido, capital de trabajo (no ratios financieros)
- OTRO: cualquier otro requisito habilitante no clasificable arriba

Reglas:
- Solo incluye requisitos EXPLÍCITAMENTE mencionados en el contexto
- No inventes ni inferas requisitos no presentes
- Asigna id secuencial desde 1
- estado siempre "PENDIENTE" (la app no puede validar contra la empresa)
- origen siempre "EXTRACCION"

Devuelve JSON exacto:
{"requisitos": [
  {"id": 1, "categoria": "JURIDICO", "descripcion": "...",
   "obligatorio": "SI", "pagina": "12", "seccion": "3.1 Habilitantes Jurídicos",
   "estado": "PENDIENTE", "origen": "EXTRACCION"}
]}
```

**`PLIEGO_QA_SYSTEM_PROMPT`** — prompt de Q&A:

```
Eres un asistente que responde preguntas sobre el pliego de condiciones de una licitación colombiana.
Responde SOLO con información del contexto proporcionado.
Si no encuentras la información, responde: "No se encontró información sobre eso en el pliego."
Sé conciso y específico. Incluye número de página o sección si está disponible en el contexto.
```

### 1.3 `evaluation/general_requirements_inference.py` (nuevo)

```python
from tendermod.config.settings import CHROMA_PERSIST_DIR
from tendermod.retrieval.embeddings import embed_docs
from tendermod.retrieval.vectorstore import read_vectorstore
from tendermod.retrieval.context_builder import wide_context
from tendermod.evaluation.schemas import GeneralRequirementList
from tendermod.evaluation.prompts import (
    qna_system_message_general_requirements,
    PLIEGO_QA_SYSTEM_PROMPT,
)
# Reutilizar la función de inicialización de cliente OpenAI existente en llm_client.py

_EXTRACTION_QUERY = (
    "requisitos habilitantes documentos certificaciones garantías pólizas "
    "personal jurídico técnico capacidad organizacional"
)

def get_general_requirements(k: int = 15) -> GeneralRequirementList:
    vectorstore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": k})
    docs = retriever.invoke(_EXTRACTION_QUERY)
    context = wide_context(docs, vectorstore)
    # Llamada a OpenAI con response_format=GeneralRequirementList (structured outputs)
    # Patrón idéntico al usado en experience_inference.py / indicators_inference.py


def ask_pliego(question: str, k: int = 8) -> str:
    """Responde preguntas en lenguaje natural sobre el pliego. Retorna string."""
    vectorstore = read_vectorstore(embed_docs(), path=CHROMA_PERSIST_DIR)
    retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": k})
    docs = retriever.invoke(question)
    context = wide_context(docs, vectorstore)
    # Llamada estándar a gpt-4o-mini, sin structured output
```

> **Nota de implementación**: No duplicar la inicialización del cliente OpenAI. Reutilizar la función que expone `llm_client.py`.

---

## Sprint 2 — Base de datos y Celery

### 2.1 `apps/core/models.py`

```python
# En AnalysisSession, después de general_info_text:
general_requirements_json = models.TextField(blank=True, default='')
```

### 2.2 Migración

```bash
python manage.py makemigrations core --name="add_general_requirements_to_session"
python manage.py migrate
```

### 2.3 `apps/analysis/tasks.py`

```python
@shared_task(bind=True, name='analysis.extract_general_requirements_task')
def extract_general_requirements_task(self, session_id):
    connection.close()
    from apps.core.models import AnalysisSession
    try:
        from tendermod.evaluation.general_requirements_inference import get_general_requirements

        session = AnalysisSession.objects.get(pk=session_id)
        session.celery_task_id = self.request.id
        session.save(update_fields=['celery_task_id', 'updated_at'])

        req_list = get_general_requirements(k=15)
        connection.close()

        session.general_requirements_json = req_list.model_dump_json()
        session.save(update_fields=['general_requirements_json', 'updated_at'])
        return {'status': 'ok', 'session_id': session_id, 'count': len(req_list.requisitos)}

    except Exception as exc:
        logger.error('Error extrayendo requisitos generales para sesion %s: %s', session_id, exc)
        raise
```

---

## Sprint 3 — Extracción en Step 1

### 3.1 `views.py` — `analysis_extract`

```python
elif action == 'general_requirements':
    task = extract_general_requirements_task.delay(session.pk)
```

Actualizar context de `analysis_step1`:

```python
'has_general_requirements': bool(session.general_requirements_json),
```

### 3.2 `step1.html`

Añadir tercer card usando el mismo patrón de botón + polling JS que los cards de experiencia e indicadores:

```html
<div class="card mb-3" id="card-general-req">
  <div class="card-body">
    <h6>Requisitos Generales</h6>
    <p class="text-muted small">Documentos, certificaciones, garantías, personal y otros habilitantes</p>
    {% if has_general_requirements %}
      <span class="badge bg-success">Extraído</span>
    {% else %}
      <button class="btn btn-sm btn-outline-primary" onclick="extract('general_requirements')">
        Extraer
      </button>
    {% endif %}
  </div>
</div>
```

---

## Sprint 4 — Checklist editable en Step 2 (Feature B) + Q&A

### 4.1 Dos nuevos endpoints en `views.py`

**`analysis_checklist_save`** — guarda estados editados por el usuario:

```python
@require_POST
def analysis_checklist_save(request, pk):
    """
    AJAX: recibe lista de {id, estado} y actualiza general_requirements_json.
    Body: {updates: [{id: 1, estado: "CUMPLE"}, ...]}
    """
    session = get_object_or_404(AnalysisSession, pk=pk)
    body = json.loads(request.body)
    updates = {item['id']: item['estado'] for item in body.get('updates', [])}

    from tendermod.evaluation.schemas import GeneralRequirementList
    req_list = GeneralRequirementList.model_validate_json(session.general_requirements_json)
    for req in req_list.requisitos:
        if req.id in updates:
            req.estado = updates[req.id]
    session.general_requirements_json = req_list.model_dump_json()
    session.save(update_fields=['general_requirements_json', 'updated_at'])
    return JsonResponse({'status': 'ok'})
```

**`analysis_pliego_qa`** — Q&A sincrónico + agregar como requisito opcional:

```python
@require_POST
def analysis_pliego_qa(request, pk):
    """
    Síncronamente: responde pregunta sobre el pliego.
    Si add_as_requirement=True, agrega la respuesta como GeneralRequirement (origen="QA").
    Body: {question: "...", add_as_requirement: bool, categoria: "OTRO"}
    """
    session = get_object_or_404(AnalysisSession, pk=pk)
    body = json.loads(request.body)
    question = body.get('question', '').strip()
    add_as_requirement = body.get('add_as_requirement', False)
    categoria = body.get('categoria', 'OTRO')

    from tendermod.evaluation.general_requirements_inference import ask_pliego
    from tendermod.evaluation.schemas import GeneralRequirementList, GeneralRequirement

    answer = ask_pliego(question, k=8)

    if add_as_requirement and 'No se encontró' not in answer:
        req_list = GeneralRequirementList()
        if session.general_requirements_json:
            req_list = GeneralRequirementList.model_validate_json(session.general_requirements_json)
        next_id = max((r.id for r in req_list.requisitos), default=0) + 1
        req_list.requisitos.append(GeneralRequirement(
            id=next_id,
            categoria=categoria,
            descripcion=f"[Q&A] {question}: {answer}",
            obligatorio="NO_ESPECIFICADO",
            estado="PENDIENTE",
            origen="QA",
        ))
        session.general_requirements_json = req_list.model_dump_json()
        session.save(update_fields=['general_requirements_json', 'updated_at'])

    return JsonResponse({'answer': answer, 'added': add_as_requirement})
```

### 4.2 `urls.py`

```python
path('<int:pk>/checklist/save/', views.analysis_checklist_save, name='checklist_save'),
path('<int:pk>/pliego/qa/', views.analysis_pliego_qa, name='pliego_qa'),
```

### 4.3 `step2.html` — nuevo tab "Requisitos Generales"

Añadir tercer tab al nav existente:

```html
<!-- Tab nav -->
<ul class="nav nav-tabs mb-3">
  <li class="nav-item"><a class="nav-link active" href="#tab-exp">Experiencia</a></li>
  <li class="nav-item"><a class="nav-link" href="#tab-ind">Indicadores</a></li>
  <li class="nav-item">
    <a class="nav-link" href="#tab-req">
      Requisitos Generales
      <span class="badge bg-secondary">{{ req_count }}</span>
    </a>
  </li>
</ul>

<!-- Tab: Requisitos Generales -->
<div class="tab-pane" id="tab-req">

  <!-- Checklist agrupado por categoría -->
  {% regroup general_requirements by categoria as req_by_cat %}
  {% for cat_group in req_by_cat %}
    <h6 class="mt-3 text-muted">{{ cat_group.grouper }}</h6>
    {% for req in cat_group.list %}
    <div class="d-flex align-items-center gap-3 mb-2 p-2 border rounded">
      <div class="flex-grow-1">
        <small class="text-muted">{{ req.seccion }} · Pág. {{ req.pagina }}</small>
        <p class="mb-0">{{ req.descripcion }}</p>
        {% if req.origen == "QA" %}<span class="badge bg-info">Q&A</span>{% endif %}
        {% if req.origen == "MANUAL" %}<span class="badge bg-warning">Manual</span>{% endif %}
      </div>
      <select class="form-select form-select-sm estado-select" style="width:150px"
              data-req-id="{{ req.id }}">
        <option value="PENDIENTE" {% if req.estado == "PENDIENTE" %}selected{% endif %}>Pendiente</option>
        <option value="CUMPLE"    {% if req.estado == "CUMPLE"    %}selected{% endif %}>Cumple</option>
        <option value="NO_CUMPLE" {% if req.estado == "NO_CUMPLE" %}selected{% endif %}>No Cumple</option>
        <option value="N/A"       {% if req.estado == "N/A"       %}selected{% endif %}>N/A</option>
      </select>
    </div>
    {% endfor %}
  {% empty %}
    <p class="text-muted">No hay requisitos generales extraídos. Ejecuta la extracción en el Paso 1.</p>
  {% endfor %}

  <button class="btn btn-success mt-2" id="btn-save-checklist">
    <i class="bi bi-save me-1"></i>Guardar estados
  </button>

  <!-- Panel Q&A del pliego -->
  <hr class="mt-4">
  <h6><i class="bi bi-chat-dots me-1"></i>Consultar el pliego</h6>
  <p class="text-muted small">
    Haz una pregunta sobre el pliego. Puedes agregar la respuesta como requisito adicional.
  </p>
  <div class="input-group mb-2">
    <input type="text" id="qa-question" class="form-control"
           placeholder="Ej: ¿Se requiere certificación ISO 27001?">
    <select id="qa-categoria" class="form-select" style="max-width:160px">
      <option value="OTRO">Otro</option>
      <option value="TECNICO">Técnico</option>
      <option value="JURIDICO">Jurídico</option>
      <option value="DOCUMENTACION">Documentación</option>
      <option value="CAPACIDAD">Capacidad</option>
    </select>
    <button class="btn btn-outline-primary" id="btn-qa-ask">Consultar</button>
  </div>
  <div id="qa-spinner" class="d-none text-center py-3">
    <div class="spinner-border spinner-border-sm text-primary"></div>
    <span class="ms-2 text-muted">Consultando el pliego...</span>
  </div>
  <div id="qa-result" class="alert alert-info d-none">
    <p id="qa-answer" class="mb-2"></p>
    <button class="btn btn-sm btn-outline-success" id="btn-qa-add">
      <i class="bi bi-plus-circle me-1"></i>Agregar como requisito
    </button>
  </div>

</div>
```

**JS para el tab** (añadir al final del template, dentro del bloque `{% block scripts %}`):

```javascript
// Guardar estados del checklist
document.getElementById('btn-save-checklist')?.addEventListener('click', () => {
  const updates = [...document.querySelectorAll('.estado-select')].map(s => ({
    id: parseInt(s.dataset.reqId), estado: s.value
  }));
  fetch("{% url 'analysis:checklist_save' pk=session.pk %}", {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
    body: JSON.stringify({updates})
  }).then(r => r.json()).then(d => {
    if (d.status === 'ok') showToast('Estados guardados correctamente', 'success');
    else showToast('Error al guardar: ' + d.error, 'danger');
  });
});

// Q&A: consultar el pliego
document.getElementById('btn-qa-ask')?.addEventListener('click', async () => {
  const question = document.getElementById('qa-question').value.trim();
  if (!question) return;
  document.getElementById('qa-result').classList.add('d-none');
  document.getElementById('qa-spinner').classList.remove('d-none');
  document.getElementById('btn-qa-ask').disabled = true;
  try {
    const resp = await fetch("{% url 'analysis:pliego_qa' pk=session.pk %}", {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
      body: JSON.stringify({question})
    });
    const data = await resp.json();
    document.getElementById('qa-answer').textContent = data.answer;
    document.getElementById('qa-result').classList.remove('d-none');
  } finally {
    document.getElementById('qa-spinner').classList.add('d-none');
    document.getElementById('btn-qa-ask').disabled = false;
  }
});

// Q&A: agregar respuesta como requisito
document.getElementById('btn-qa-add')?.addEventListener('click', async () => {
  const question = document.getElementById('qa-question').value.trim();
  const categoria = document.getElementById('qa-categoria').value;
  const resp = await fetch("{% url 'analysis:pliego_qa' pk=session.pk %}", {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
    body: JSON.stringify({question, add_as_requirement: true, categoria})
  });
  const data = await resp.json();
  if (data.added) showToast('Requisito agregado. Recarga la página para verlo.', 'success');
});
```

---

## Sprint 5 — Resultados y Excel (Feature A)

### 5.1 `views.py` — `analysis_results`

```python
general_requirements = []
if session.general_requirements_json:
    try:
        from tendermod.evaluation.schemas import GeneralRequirementList
        gr = GeneralRequirementList.model_validate_json(session.general_requirements_json)
        general_requirements = gr.requisitos
    except Exception as exc:
        logger.error('Error parseando general_requirements_json: %s', exc)
context['general_requirements'] = general_requirements
```

### 5.2 `results.html`

Añadir sección checklist después de la sección de indicadores:

```html
{% if general_requirements %}
<div class="card mb-4">
  <div class="card-header fw-semibold">
    <i class="bi bi-list-check me-2"></i>Checklist de Requisitos Generales
  </div>
  <div class="card-body">
    {% regroup general_requirements by categoria as req_by_cat %}
    {% for cat_group in req_by_cat %}
      <h6 class="text-muted mt-3">{{ cat_group.grouper }}</h6>
      {% for req in cat_group.list %}
      <div class="d-flex align-items-start gap-2 mb-1">
        {% if req.estado == "CUMPLE" %}
          <span class="badge bg-success">CUMPLE</span>
        {% elif req.estado == "NO_CUMPLE" %}
          <span class="badge bg-danger">NO CUMPLE</span>
        {% elif req.estado == "N/A" %}
          <span class="badge bg-secondary">N/A</span>
        {% else %}
          <span class="badge bg-warning text-dark">PENDIENTE</span>
        {% endif %}
        <span>{{ req.descripcion }}
          <small class="text-muted ms-1">· Pág. {{ req.pagina }}</small>
        </span>
      </div>
      {% endfor %}
    {% endfor %}
  </div>
</div>
{% endif %}
```

### 5.3 `export_excel` — Hoja "Checklist General"

Añadir en `views.py`, dentro de `export_excel`, después de la hoja Sub-Requisitos.
La hoja se genera desde `session.general_requirements_json` (no desde `result`):

```python
if session.general_requirements_json:
    try:
        from tendermod.evaluation.schemas import GeneralRequirementList
        gr = GeneralRequirementList.model_validate_json(session.general_requirements_json)
        ws_cl = wb.create_sheet('Checklist General')

        cl_headers = ['#', 'Categoría', 'Descripción', 'Obligatorio', 'Sección', 'Página', 'Estado', 'Origen']
        for col_num, header in enumerate(cl_headers, 1):
            cell = ws_cl.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')

        estado_fills = {
            'CUMPLE':    PatternFill('solid', fgColor='C6EFCE'),
            'NO_CUMPLE': PatternFill('solid', fgColor='FFC7CE'),
            'PENDIENTE': PatternFill('solid', fgColor='FFEB9C'),
            'N/A':       PatternFill('solid', fgColor='D9D9D9'),
        }

        for req in gr.requisitos:
            row_num = ws_cl.max_row + 1
            ws_cl.append([
                req.id, req.categoria, req.descripcion,
                req.obligatorio, req.seccion, req.pagina,
                req.estado, req.origen,
            ])
            fill = estado_fills.get(req.estado)
            if fill:
                for col in range(1, 9):
                    ws_cl.cell(row=row_num, column=col).fill = fill

        for col in ws_cl.columns:
            max_len = max((len(str(cell.value or '')) for cell in col), default=10)
            ws_cl.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)
    except Exception as exc:
        logger.warning('No se pudo generar hoja Checklist General: %s', exc)
```

---

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Recall bajo (requisitos no recuperados por RAG) | Medio | `k=15` + `wide_context()` + query amplia multi-término |
| Duplicados con experiencia/indicadores | Bajo | Exclusión explícita en el prompt |
| Hallucination (LLM inventa requisitos) | Bajo-Medio | Prompt con "solo si está en el contexto" + campo `pagina` obliga trazabilidad |
| Q&A síncrono bloquea request >30s | Bajo | Timeout de OpenAI en ~15s; si supera, mostrar mensaje y sugerir reintentar |
| Usuario confundido por "PENDIENTE" | Bajo | Tooltip en UI: "Validación manual requerida — marque el estado según sus documentos" |

---

## Proyección Fase 2

### Fase 2A — Perfil de empresa en SQLite (opción C)

Nueva tabla `empresa_certificaciones` en `redneet_db`:

```sql
CREATE TABLE empresa_certificaciones (
    id          INTEGER PRIMARY KEY,
    tipo        TEXT NOT NULL,        -- JURIDICO/TECNICO/DOCUMENTACION/CAPACIDAD
    nombre      TEXT NOT NULL,        -- "ISO 9001", "Cámara de Comercio"
    descripcion TEXT,
    vigente_hasta DATE,
    adjunto_path TEXT
);
```

Nueva task `auto_validate_requirements_task` que hace match semántico (embeddings) o keyword entre `general_requirements_json` y la tabla. Actualiza `estado` automáticamente a `CUMPLE`/`NO_CUMPLE`. Requiere UI de carga y mantenimiento del perfil (CRUD separado del flujo de análisis).

### Fase 2B — Upload de perfil como documento (opción D)

Nuevo pipeline de ingesta `ingestion_company_profile_flow.py` (patrón idéntico a `ingestion_experience_flow.py`). Nuevo ChromaDB en `chroma_company_profile/`. Task `auto_validate_from_profile_task` que por cada `GeneralRequirement` hace similarity search y pide al LLM evidencia de cumplimiento. Agrega campo `evidencia_texto` al schema para mostrar el fragmento del perfil que soporta el `CUMPLE`.

---

## Orden de ejecución recomendado

```
Sprint 1 (2-3h):  schemas → prompts → general_requirements_inference.py
Sprint 2 (30min): models.py → migración → task Celery
Sprint 3 (1h):    views.py (extract action) → step1.html (nuevo card)
Sprint 4 (3-4h):  views.py (checklist_save + pliego_qa) → urls.py → step2.html (tab + JS)
Sprint 5 (1-2h):  views.py (results context) → results.html → export_excel

Total estimado: 8-10h de desarrollo
```
