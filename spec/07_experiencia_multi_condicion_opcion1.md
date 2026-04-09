# Spec 07 — Experiencia Multi-Condición (Opción 1)

## Problema

El numeral 4.1.2.4.2 "Experiencia Específica" de licitaciones como `10- PROYECTO DE REGLAS DE PARTICIPACION.pdf` define múltiples sub-requisitos independientes donde **cada uno debe ser satisfecho por al menos un contrato distinto**:

1. Al menos 1 contrato con suministro e instalación de UPSs en Datacenters.
2. Al menos 1 contrato con suministro e instalación de refrigeración de precisión en Datacenters.
3. Al menos 1 contrato con mantenimientos de UPSs en Datacenters.
4. Al menos 1 contrato con mantenimientos de refrigeración de precisión en Datacenters.

El sistema actual evalúa **un solo `objeto`** con similitud semántica y reporta CUMPLE cuando no debería.

---

## Diagnóstico — Cadena de fallas

**Fallo 1 — Extracción (LLM + prompt):**
El prompt pregunta por "the required purpose" en singular. El LLM colapsa los 4 sub-requisitos en uno solo (generalmente el primero). Los otros 3 se pierden silenciosamente.

**Fallo 2 — Schema Pydantic:**
`ExperienceResponse.objeto` es `str`. No hay representación de sub-requisitos independientes.

**Fallo 3 — Lógica de evaluación:**
`check_compliance_experience()` hace una sola `similarity_search` contra todos los RUPs con un único `objeto_requerido`. Un contrato relevante para sub-req 1 puede no serlo para sub-req 3, pero el sistema los trata como equivalentes.

**Fallo 4 — Contratos distintos no se verifican:**
El pliego exige que cada sub-requisito sea cubierto por un contrato DISTINTO. El sistema actual no tiene ningún mecanismo para esta restricción.

---

## Solución — Opción 1: Modo GLOBAL / MULTI_CONDICION

Agregar soporte para dos modos de evaluación. El modo `GLOBAL` preserva el flujo actual sin cambios. El modo `MULTI_CONDICION` activa la nueva lógica multi-sub-requisito.

---

## Cambios detallados

### 1. `evaluation/schemas.py`

#### Nueva clase: `ExperienceSubRequirement`

```python
class ExperienceSubRequirement(BaseModel):
    """Un sub-requisito de experiencia específica del pliego."""
    descripcion: str = Field(
        description="Descripción exacta del sub-requisito tal como aparece en el pliego"
    )
    codigos_unspsc: List[str] = Field(
        default=[],
        description="Códigos UNSPSC específicos de este sub-req (hereda globales si vacío)"
    )
    cantidad_minima_contratos: int = Field(
        default=1,
        description="Mínimo de contratos distintos que deben cubrir este sub-requisito"
    )
    valor_minimo: str = Field(
        default="None",
        description="Valor mínimo para este sub-req específico. 'None' si no aplica."
    )
    objeto_exige_relevancia: Literal["SI", "NO", "NO_ESPECIFICADO"] = Field(
        default="NO_ESPECIFICADO"
    )
```

#### Nueva clase: `SubRequirementComplianceResult`

```python
class SubRequirementComplianceResult(BaseModel):
    """Resultado de evaluación para un sub-requisito individual."""
    indice: int
    descripcion: str
    rups_candidatos: List[Union[int, str]] = []
    rup_elegido: Optional[Union[int, str]] = None
    score_objeto: Optional[float] = None
    objeto_contrato: Optional[str] = None
    cumple: bool = False
```

#### Cambios en `ExperienceResponse`

Agregar al final de la clase (después de `objeto_exige_relevancia`):

```python
modo_evaluacion: Literal["GLOBAL", "MULTI_CONDICION"] = Field(
    default="GLOBAL",
    alias="Modo evaluacion",
    description="MULTI_CONDICION cuando el pliego exige contratos distintos por actividad"
)
sub_requisitos: List[ExperienceSubRequirement] = Field(
    default=[],
    alias="Sub requisitos",
    description="Lista de sub-requisitos. Vacía en modo GLOBAL."
)
```

#### Cambios en `ExperienceComplianceResult`

Agregar al final:

```python
modo_evaluacion: str = Field(default="GLOBAL")
sub_requisitos_resultado: List[SubRequirementComplianceResult] = Field(default=[])
sub_requisitos_cumplidos: int = Field(default=0)
sub_requisitos_totales: int = Field(default=0)
```

El campo `cumple` existente sigue siendo el veredicto final:
- Modo `GLOBAL`: comportamiento actual sin cambios.
- Modo `MULTI_CONDICION`: `True` solo si **todos** los sub-requisitos tienen `cumple=True`.

---

### 2. `evaluation/prompts.py`

#### En `qna_system_message_experience` — agregar preguntas 8 y 9

```
8- Does the tender list MULTIPLE INDEPENDENT experience sub-requirements, where each must be
   satisfied by at least ONE SEPARATE contract? Look for patterns like:
   - "Al menos un (1) contrato con [X]" followed by "Al menos un (1) contrato con [Y]"
   - A numbered list where each item describes a different type of work/supply
   Answer "MULTI_CONDICION" if such a pattern exists. Answer "GLOBAL" in all other cases.

9- If you answered "MULTI_CONDICION" in question 8, extract each sub-requirement as a
   separate entry in "Sub requisitos". For each sub-requirement provide:
   - descripcion: the exact description from the pliego
   - codigos_unspsc: UNSPSC codes specific to this sub-req (inherit global list if not specified individually)
   - cantidad_minima_contratos: minimum number of contracts required (default 1)
   - valor_minimo: minimum value if specified per sub-req, otherwise "None"
   - objeto_exige_relevancia: "SI" if linked to the object of this process, "NO_ESPECIFICADO" otherwise
   If you answered "GLOBAL", return an empty list [].
   NEVER put the general object description as a sub-requisito.
```

#### Actualizar el JSON de respuesta ejemplo en el prompt

```json
{
    "Listado de codigos": [],
    "Cuantos codigos": " ",
    "Objeto": " ",
    "Cantidad de contratos": " ",
    "Valor a acreditar": " ",
    "Pagina": " ",
    "Seccion": " ",
    "Regla codigos": "AT_LEAST_ONE",
    "Objeto exige relevancia": "NO_ESPECIFICADO",
    "Modo evaluacion": "GLOBAL",
    "Sub requisitos": []
}
```

Ejemplo con sub-requisitos:
```json
{
    "Modo evaluacion": "MULTI_CONDICION",
    "Sub requisitos": [
        {
            "descripcion": "Al menos 1 contrato con suministro e instalación de UPSs en Datacenters",
            "codigos_unspsc": ["432217"],
            "cantidad_minima_contratos": 1,
            "valor_minimo": "None",
            "objeto_exige_relevancia": "SI"
        }
    ]
}
```

#### Actualizar `QUICK_EXPERIENCE_USER_PROMPT`

Agregar al final de las instrucciones: si el texto describe múltiples sub-requisitos independientes (patrón "al menos 1 contrato para cada actividad"), extraer cada uno en `sub_requisitos` e indicar `modo_evaluacion: "MULTI_CONDICION"`.

---

### 3. `evaluation/compare_experience.py`

#### Refactoring: extraer `_check_global_experience()`

El cuerpo actual de `check_compliance_experience()` se extrae a `_check_global_experience()` sin cambios de lógica.

#### Nueva función: `check_multi_condition_experience()`

**Algoritmo:**

```
Entradas:
  - tender_experience: ExperienceResponse (sub_requisitos poblados)
  - rups_candidatos_codigos: list (pool pre-filtrado por códigos UNSPSC)
  - similarity_threshold: float

Para cada sub_requisito:
    1. similarity_search en ChromaDB experiencia con la descripcion del sub-req (k = suficiente)
    2. Para cada RUP en pool: obtener score máximo
    3. Candidatos = RUPs con score >= similarity_threshold

Asignación greedy (contratos distintos):
    - Ordenar sub-requisitos por len(candidatos) ASC (más restrictivos primero)
    - Para cada sub-req:
        - Elegir el RUP disponible con mayor score
        - Sacar ese RUP del pool
        - Si no hay candidatos disponibles → cumple=False

Resultado:
    - cumple global = ALL(sub_req.cumple for sub_req in resultado)
```

#### Bifurcación en `check_compliance_experience()`

```python
def check_compliance_experience(tender_experience, similarity_threshold):
    # Paso 1: filtro por códigos UNSPSC (igual que hoy)
    rups_codigos = check_code_compliance(...)

    # Paso 2: bifurcación
    if (tender_experience.modo_evaluacion == "MULTI_CONDICION"
            and tender_experience.sub_requisitos):
        return check_multi_condition_experience(
            tender_experience, rups_codigos, similarity_threshold
        )
    else:
        return _check_global_experience(tender_experience, rups_codigos, similarity_threshold)
```

---

### 4. `web/templates/analysis/step2.html`

Agregar sección condicional después del campo `umbral`, visible solo cuando `exp_data.modo_evaluacion == "MULTI_CONDICION"`:

```html
{% if exp_data.modo_evaluacion == "MULTI_CONDICION" %}
<div class="col-12 mt-3">
    <label class="form-label fw-semibold">
        Sub-requisitos de Experiencia Específica
        <span class="badge bg-info text-dark ms-1">Multi-condición</span>
    </label>
    <div id="sub-requisitos-container">
        {% for sub in exp_data.sub_requisitos %}
        <div class="card border mb-2 sub-req-card" data-index="{{ forloop.counter0 }}">
            <div class="card-body py-2">
                <div class="row g-2 align-items-center">
                    <div class="col-1 text-center fw-bold text-muted">{{ forloop.counter }}</div>
                    <div class="col-7">
                        <input type="text" class="form-control form-control-sm sub-req-desc"
                               value="{{ sub.descripcion }}">
                    </div>
                    <div class="col-2">
                        <input type="text" class="form-control form-control-sm sub-req-codigos"
                               value="{{ sub.codigos_unspsc|join:', ' }}"
                               placeholder="Códigos UNSPSC">
                    </div>
                    <div class="col-2">
                        <input type="number" class="form-control form-control-sm sub-req-cantidad"
                               value="{{ sub.cantidad_minima_contratos }}" min="1">
                    </div>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
    <div class="form-text">
        Cada sub-requisito debe ser cubierto por un contrato RUP distinto.
    </div>
</div>
{% endif %}
```

Extender `buildExperienceData()` en el JS para recolectar `.sub-req-card` y construir el array `sub_requisitos`.

---

### 5. `web/templates/analysis/results.html`

Agregar tabla de sub-requisitos antes de la tabla de RUPs existente:

```html
{% if exp_result.modo_evaluacion == "MULTI_CONDICION" %}
<div class="mb-4">
    <h6 class="text-muted small text-uppercase mb-2">
        Verificación por Sub-requisito
        ({{ exp_result.sub_requisitos_cumplidos }}/{{ exp_result.sub_requisitos_totales }} cumplidos)
    </h6>
    <table class="table table-bordered table-sm align-middle">
        <thead class="table-dark">
            <tr>
                <th>#</th>
                <th>Sub-requisito</th>
                <th>RUP Asignado</th>
                <th class="text-center">Score</th>
                <th class="text-center">Resultado</th>
            </tr>
        </thead>
        <tbody>
            {% for sub in exp_result.sub_requisitos_resultado %}
            <tr {% if sub.cumple %}class="table-success"{% else %}class="table-danger"{% endif %}>
                <td>{{ sub.indice|add:1 }}</td>
                <td class="small">{{ sub.descripcion }}</td>
                <td>
                    {% if sub.rup_elegido %}
                        <strong>{{ sub.rup_elegido }}</strong>
                        {% if sub.objeto_contrato %}
                        <div class="text-muted" style="font-size:0.7rem">
                            {{ sub.objeto_contrato|truncatechars:80 }}
                        </div>
                        {% endif %}
                    {% else %}
                        <span class="text-muted">Ninguno disponible</span>
                    {% endif %}
                </td>
                <td class="text-center">
                    {% if sub.score_objeto is not None %}
                        {{ sub.score_objeto|floatformat:3 }}
                    {% else %}
                        <span class="text-muted">N/A</span>
                    {% endif %}
                </td>
                <td class="text-center">
                    {% if sub.cumple %}
                        <span class="badge bg-success">CUMPLE</span>
                    {% else %}
                        <span class="badge bg-danger">NO CUMPLE</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endif %}
```

---

### 6. `web/apps/analysis/views.py` — exportaciones

**`export_text`:** agregar bloque por sub-requisito después de la sección de objeto:
```python
if rup.sub_requisitos_resultado:
    lines.append(f'  │  Sub-requisitos:')
    for sr in rup.sub_requisitos_resultado:
        estado = 'CUMPLE' if sr.cumple else 'NO CUMPLE'
        score_str = f'Score={sr.score_objeto:.3f}' if sr.score_objeto is not None else 'Score=N/A'
        lines.append(f'  │    [{estado}] {sr.descripcion} ({score_str})')
```

**`export_excel`:** agregar hoja 3 "Sub-Requisitos" con columnas:
`NUMERO RUP | Sub-Requisito | Cumple | Score | Contrato que Cumple`

---

## Archivos a modificar

| # | Archivo | Tipo de cambio |
|---|---------|---------------|
| 1 | `src/tendermod/evaluation/schemas.py` | Nuevas clases + campos en `ExperienceResponse` y `ExperienceComplianceResult` |
| 2 | `src/tendermod/evaluation/prompts.py` | Preguntas 8 y 9 + JSON ejemplo actualizado |
| 3 | `src/tendermod/evaluation/compare_experience.py` | Refactoring + nueva función + bifurcación |
| 4 | `web/templates/analysis/step2.html` | Sección sub-requisitos + JS `buildExperienceData()` |
| 5 | `web/templates/analysis/results.html` | Tabla por sub-requisito en modo MULTI_CONDICION |
| 6 | `web/apps/analysis/views.py` | `export_text` y `export_excel` |

**Sin cambios:** `tasks.py`, `llm_client.py`, `experience_inference.py`, migraciones de DB.

---

## Compatibilidad hacia atrás

Todos los campos nuevos tienen `default=[]` o `default="GLOBAL"`. El JSON existente en `AnalysisResult.experience_result_json` se parsea sin error. Pliegos con requisito único de experiencia continúan usando el flujo `GLOBAL` sin ningún cambio de comportamiento.

---

## Notas de implementación

- El vectorstore de experiencia debe abrirse **una sola vez** por evaluación multi-condición y pasarse como argumento a `check_multi_condition_experience()` para evitar N aperturas de ChromaDB.
- El algoritmo greedy para asignación de contratos distintos ordena sub-requisitos de menor a mayor número de candidatos (más restrictivos primero). Para casos extremos con muchos sub-requisitos, se puede escalar a Hungarian algorithm en una versión futura.
- El campo `objeto` de `ExperienceResponse` se mantiene como resumen global. En modo `MULTI_CONDICION`, el LLM puede dejarlo vacío o como descripción general sin que afecte la evaluación.
