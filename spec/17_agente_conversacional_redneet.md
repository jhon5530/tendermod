# Spec 17 — Agente conversacional Redneet (reemplaza evaluación rápida)

## Contexto

La evaluación rápida actual tiene dos botones separados (Experiencia / Indicadores), usa Celery async, y redirige a la página de resultados completa diseñada para pliegos. Se reemplaza por un **chat unificado y conversacional** que:
- Responde preguntas libres en lenguaje natural sobre la empresa
- Accede a todas las fuentes de datos Redneet: contratos, equipo, indicadores
- Evalúa requisitos de un pliego pegados directamente en el chat
- Es síncrono (sin Celery/polling)
- Usa `gpt-4.1` para mejor comprensión conversacional

**Impacto en otros flujos:** NINGUNO. Los flujos automático, manual y nueva evaluación usan Celery + ChromaDB del pliego + tareas `extract_*/evaluate_*`. El nuevo agente solo reemplaza la UI de evaluación rápida y lee exclusivamente la BD Redneet (SQLite).

---

## Fuentes de datos del agente

| Fuente | Tabla SQLite | Registros | Tokens estimados |
|--------|-------------|-----------|-----------------|
| Contratos RUP | `experiencia` | 219 contratos | ~8K tokens |
| Equipo de trabajo | `personas` + `certificaciones` | 17 personas, 321 certs | ~17K tokens |
| Indicadores financieros | `indicadores` | 18 indicadores | ~200 tokens |
| **Total contexto** | | | **~25K tokens** |

---

## TODO-LIST

### Fase 1 — Backend (redneet_inference.py)

- [x] **1. Crear `src/tendermod/evaluation/redneet_inference.py`**
  - Función `_load_experience_as_text()`:
    - Lee tabla `experiencia` de SQLite
    - Por cada RUP: formatea NUMERO RUP, CLIENTE, VALOR COP, SMMLV, OBJETO, DESCRIPCION GENERAL, FECHA FINALIZACION, DIAS EJECUCION
    - Incluir solo códigos UNSPSC con valor 1 (no las 173 columnas binarias — solo los activos)
    - Output: string texto ~8K tokens
  - Función `_load_indicators_as_text()`:
    - Lee tabla `indicadores` (INDICADOR, VALOR)
    - Output: string texto ~200 tokens
  - Función `_load_team_as_text()`:
    - **Reutiliza** `_load_all_team_data()` de `team_inference.py` (ya implementado, carga personas + certificaciones)
    - Output: string texto ~17K tokens
  - Función `ask_redneet(question: str, chat_history: list[dict] = []) -> str`:
    - Carga las tres fuentes
    - Construye mensajes: SYSTEM + historial[-10:] + HumanMessage(contexto + pregunta)
    - Llama `ChatOpenAI(model="gpt-4.1", temperature=0.1)`
    - Retorna respuesta en texto

- [x] **2. Añadir `REDNEET_AGENT_SYSTEM` en `src/tendermod/evaluation/prompts.py`**
  - System prompt que instruye al LLM:
    - Rol: experto en empresa Redneet (contratos TI Colombia)
    - Instrucciones: ordenar contratos de más a menos relevante, dar veredictos CUMPLE/NO CUMPLE con justificación
    - Formato: responder en español, usar datos concretos (COP, SMMLV, fechas, clientes)
    - Alcance: solo información de las tres fuentes proporcionadas; no inventar datos
    - Evaluación de requisitos: calcular suma de valores acumulados, indicar qué contratos aportan al cumplimiento

### Fase 2 — Vistas Django

- [x] **3. Añadir vistas en `web/apps/analysis/views.py`**
  - `redneet_qa(request)`:
    - GET: renderiza `analysis/redneet_qa.html` con historial de sesión Django
  - `redneet_qa_query(request)`:
    - POST (JSON `{question: "..."}`)
    - Llama `ask_redneet(question, history)`
    - Actualiza historial (ventana: últimos 10 mensajes = 5 turnos)
    - Retorna `{answer: "..."}`
  - `redneet_qa_clear(request)`:
    - POST: limpia `redneet_chat_history` de sesión Django
  - **Reemplazar** `analysis_quick` → redirigir a `redneet_qa`

- [x] **4. Actualizar `web/apps/analysis/urls.py`**
  ```python
  path('quick/', views.redneet_qa, name='quick'),
  path('quick/query/', views.redneet_qa_query, name='redneet_qa_query'),
  path('quick/clear/', views.redneet_qa_clear, name='redneet_qa_clear'),
  ```

### Fase 3 — Template

- [x] **5. Crear `web/templates/analysis/redneet_qa.html`**
  - Basado en `team_qa.html` con estas diferencias:
    - **Badge de datos**: "219 contratos · 17 personas · 321 certs · 18 indicadores"
    - **Sugerencias rápidas** (6 botones):
      - "¿Qué experiencia tenemos en redes?"
      - "¿Cumplimos con liquidez ≥ 1.5?"
      - "Contratos con valor > $100M"
      - "¿Quién tiene CCNP o CCNA vigente?"
      - "Experiencia en datacenter / servidores"
      - "Evalúa: [pegar requisito]"
    - **Renderizado Markdown** en respuestas (librería `marked.js` via CDN)
    - **Título**: "Consultor Redneet" con ícono de base de datos
    - Historial de chat (mismo patrón que team_qa.html)
    - Botón "Nueva conversación"

---

## Archivos afectados

| Archivo | Operación |
|---------|-----------|
| `src/tendermod/evaluation/redneet_inference.py` | CREAR |
| `src/tendermod/evaluation/prompts.py` | MODIFICAR (añadir `REDNEET_AGENT_SYSTEM`) |
| `web/apps/analysis/views.py` | MODIFICAR (añadir 3 vistas, reemplazar analysis_quick) |
| `web/apps/analysis/urls.py` | MODIFICAR (actualizar rutas /quick/) |
| `web/templates/analysis/redneet_qa.html` | CREAR |
| `web/templates/analysis/quick.html` | DEPRECAR (reemplazado) |

---

## Lo que NO cambia

- `quick_evaluate_experience_task` y `quick_evaluate_indicators_task` (Celery) — se conservan; el flujo automático las puede invocar
- Flujos automático, manual y nueva evaluación — sin cambios
- `team_qa` y `team_qa.html` — sin cambios (el equipo sigue teniendo su propia vista dedicada)
- ChromaDB del pliego — sin cambios
- Toda la lógica de `check_compliance_experience`, `compare_indicators` — sin cambios

---

## Verificación

1. Acceder a `/analysis/quick/` → debe mostrar el nuevo chat
2. Preguntar "¿Qué experiencia tenemos en redes?" → respuesta con contratos relevantes ordenados
3. Preguntar "¿Cumplimos con liquidez >= 1.5?" → respuesta con valor actual vs umbral
4. Pegar requisito de pliego → evaluación con veredicto y contratos que cumplen
5. Preguntar "¿Quién tiene CCNP vigente?" → respuesta con personas y certificaciones
6. Preguntar "¿Cuántos contratos en código 432217?" → conteo correcto
7. Verificar que el historial multi-turno mantiene contexto
8. Verificar "Nueva conversación" limpia el historial
9. Verificar que `/analysis/new/`, `/analysis/{pk}/step1/`, `/analysis/{pk}/auto/` siguen funcionando igual
