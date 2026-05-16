# Spec 14 — Evaluacion Automatica

## Objetivo

Agregar un botón "Evaluacion automatica" en `/analysis/new/` que ejecute todos los
pasos de extraccion y evaluacion de forma secuencial y autonoma, sin que el usuario
deba presionar ningun boton adicional. Muestra una barra de progreso (0–100 %) con el
listado de pasos en tiempo real y redirige automaticamente a la pagina de resultados
al terminar.

---

## Decisiones de arquitectura

| Decision | Eleccion | Razon |
|----------|----------|-------|
| Edicion Step 2 | Saltar — usar datos crudos | Flujo 100% automatico; imprecisiones se corrigen en modo manual |
| Pantalla progreso | Pagina dedicada `/analysis/<pk>/auto/` | Espacio para mostrar detalle de 7 pasos |
| Requisitos generales | Extraer sin auto-marcar | Checklist queda pendiente de revision manual en resultados |
| Boton | Segundo `<button submit>` junto a "Cargar PDF" | Coexiste con el flujo manual sin romperlo |
| Orquestacion | JS secuencial + polling existente | Reutiliza `/api/task-status/<id>/`, sin nueva infraestructura Celery |

---

## Pasos de la evaluacion automatica

| # | Accion | Peso (%) | Endpoint backend |
|---|--------|---------|-----------------|
| 1 | Ingesta PDF en base vectorial | 15 | Poll `ingest_task_id` (ya lanzado al subir PDF) |
| 2 | Extraer requisitos de experiencia | 15 | POST `/analysis/<pk>/step1/extract/` `action=experience` |
| 3 | Extraer indicadores financieros | 15 | POST `/analysis/<pk>/step1/extract/` `action=indicators` |
| 4 | Extraer informacion general | 10 | POST `/analysis/<pk>/step1/extract/` `action=general_info` |
| 5 | Extraer requisitos habilitantes | 15 | POST `/analysis/<pk>/step1/extract/` `action=general_requirements` |
| 6 | Evaluar cumplimiento experiencia | 15 | POST `/analysis/<pk>/auto/evaluate-experience/` |
| 7 | Evaluar indicadores financieros | 15 | POST `/analysis/<pk>/auto/evaluate-indicators/` |

---

## Archivos creados / modificados

### Backend

| Archivo | Accion |
|---------|--------|
| `web/apps/analysis/views.py` | MODIFICADO — `analysis_new` detecta `action=auto`; agrega `analysis_auto`, `auto_evaluate_experience`, `auto_evaluate_indicators` |
| `web/apps/analysis/urls.py` | MODIFICADO — agrega `<pk>/auto/`, `<pk>/auto/evaluate-experience/`, `<pk>/auto/evaluate-indicators/` |

### Web

| Archivo | Accion |
|---------|--------|
| `web/templates/analysis/new.html` | MODIFICADO — segundo boton "Evaluacion automatica" |
| `web/templates/analysis/auto.html` | NUEVO — pantalla de progreso con barra y lista de pasos |

---

## Flujo completo

```
Usuario sube PDF en /analysis/new/ → click "Evaluacion automatica"
    → analysis_new crea sesion, lanza ingest_pdf_task, redirige a /analysis/<pk>/auto/?ingest_task=<id>

/analysis/<pk>/auto/ carga auto.html
    → JS inicia runAutoEvaluation()
        1. Pollra ingest_task_id hasta SUCCESS (15%)
        2. POST extract/ action=experience → poll → done (30%)
        3. POST extract/ action=indicators → poll → done (45%)
        4. POST extract/ action=general_info → poll → done (55%)
        5. POST extract/ action=general_requirements → poll → done (70%)
        6. POST auto/evaluate-experience/ → lee session.experience_requirements_json → poll → done (85%)
        7. POST auto/evaluate-indicators/ → lee session.indicators_requirements_json → poll → done (100%)
    → window.location = /analysis/<pk>/results/
```

---

## Verificacion

1. Subir PDF → click "Evaluacion automatica" → confirmar redireccion a `/analysis/<pk>/auto/`.
2. La barra debe avanzar de 0 a 100 % completando los 7 pasos listados con iconos.
3. Si un paso falla, debe mostrar icono rojo y boton "Ir al modo manual".
4. Al llegar al 100 %, debe redirigir automaticamente a `/analysis/<pk>/results/`.
5. Resultados deben mostrar Experiencia, Indicadores y Requisitos Generales (checklist vacio).
6. Verificar que el boton "Cargar PDF" original sigue funcionando sin cambios.

---

## Estado de implementacion

- [x] `views.py` — `analysis_auto`, `auto_evaluate_experience`, `auto_evaluate_indicators` creados
- [x] `views.py` — `analysis_new` modificado para detectar `action=auto`
- [x] `urls.py` — 3 URLs nuevas agregadas
- [x] `new.html` — segundo boton submit agregado
- [x] `auto.html` — creado con barra de progreso y logica JS
