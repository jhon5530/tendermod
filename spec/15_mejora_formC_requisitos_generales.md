# Spec 15 — Mejora FormC Requisitos Generales Habilitantes

## Objetivo

Mejorar la interfaz de revisión del FormC (Step 2) para que el usuario pueda
interactuar eficientemente con cada requisito: marcar su estado, escribir una nota
y filtrar la lista por Tipo y Categoría.

---

## Cambios funcionales

### Estados disponibles

| Valor | UI | Descripcion |
|-------|----|-------------|
| `EN_REVISION` | "En Revision" | Estado inicial de todo requisito nuevo |
| `CUMPLE` | "Cumple" | El proponente cumple el requisito |
| `NO_CUMPLE` | "No Cumple" | El proponente no cumple el requisito |
| `N/A` | "N/A" | No aplica para esta licitacion |
| `PENDIENTE` | (legacy) | Sesiones anteriores; UI lo muestra como "En Revision" |

### Nota por requisito

- Campo `textarea` inline (siempre visible, 2 filas) debajo del dropdown de estado.
- Se guarda junto con el estado al hacer click en "Guardar estados".
- Aparece como columna **"Nota"** en la hoja "Checklist General" del Excel exportado
  (posición 11, entre "Estado" y "Origen").

### Filtros (client-side, lógica AND)

- **Tipo**: dropdown con todos los valores posibles del campo `tipo`.
- **Categoría**: dropdown con todos los valores posibles del campo `categoria`.
- Con ambos activos se muestran solo los requisitos que cumplen Tipo **y** Categoría.
- Botón "Limpiar" resetea ambos filtros.
- Contador "X de Y requisitos" se actualiza en tiempo real.
- Las cabeceras de categoría se ocultan automáticamente si todos sus requisitos
  están filtrados.

### Visibilidad de Categoría y Tipo

- Cada fila muestra un badge gris con la Categoría del requisito.
- Se agregan badges para tipos faltantes: `HABILITANTE-EXPERIENCIA`,
  `HABILITANTE-INDICADORES`, `OBLIGACION`.

---

## Almacenamiento

| Campo | Ubicacion |
|-------|-----------|
| `estado` | `AnalysisSession.general_requirements_json` — campo `estado` en cada objeto del array `requisitos` |
| `nota` | Mismo JSON — campo `nota` añadido a `GeneralRequirement` (Pydantic schema) |
| Persistencia | AJAX POST → `/analysis/<pk>/checklist/save/` → sobrescribe el blob JSON completo |
| Exportacion | Hoja "Checklist General" del `.xlsx`, columna 11 "Nota" |

No se requiere migración de Django — el JSON blob vive en un `TextField` existente.
Sesiones antiguas con `estado="PENDIENTE"` son retrocompatibles (tratadas como `EN_REVISION`).

---

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `src/tendermod/evaluation/schemas.py` | `GeneralRequirement.estado` añade `EN_REVISION`, default cambia a `EN_REVISION`; campo `nota: str = ""` añadido |
| `web/apps/analysis/views.py` | `analysis_checklist_save` acepta y persiste `nota`; `export_excel` añade columna "Nota" en pos 11 |
| `web/templates/analysis/step2.html` | Barra de filtros, dropdown actualizado, textarea de nota inline, badges mejorados, JS de filtrado y guardado |

---

## Verificacion

1. Step 2 → FormC: verificar barra de filtros visible encima del listado.
2. Filtrar por Tipo = HABILITANTE → solo esos requisitos visibles; contador correcto.
3. Combinar Tipo + Categoría → filtrado AND; cabeceras sin hijos se ocultan.
4. Botón "Limpiar" → todos los requisitos visibles.
5. Cambiar estados + escribir notas → "Guardar" → recargar → datos persisten.
6. Exportar Excel → columna "Nota" en posición 11 con el texto guardado.
7. Sesion antigua con `estado=PENDIENTE` → dropdown muestra "En Revision".

---

## Estado de implementacion

- [x] `schemas.py` — `EN_REVISION` + campo `nota`
- [x] `views.py` — `analysis_checklist_save` acepta `nota`
- [x] `views.py` — `export_excel` columna Nota
- [x] `step2.html` — filtros, dropdown, textarea nota, badges, JS
