# Plan: Formato de Valores Monetarios en Pesos Colombianos

## Fecha
2026-03-22

## Contexto

Los valores monetarios (valor requerido, total acreditado, valor por contrato RUP) se muestran
como números crudos sin separadores de miles, e.g. `456602069`. El usuario requiere el formato
colombiano: `$456.602.069` (punto como separador de miles, prefijo `$`, sin decimales).

Situación actual por canal de salida:
- **Web UI** (`results.html`): usa `|floatformat:0` → produce `456602069` (sin separadores)
- **Exportación TXT** (`views.py`): usa f-string `{:,.0f}` → produce `$456,602,069` (coma anglosajona)
- **Exportación Excel** (`views.py`): escribe números crudos sin ningún formato

---

## Impacto Arquitectural

- **Frontend/Templates**: Requiere un filtro de template personalizado en Django.
- **Backend (views.py)**: Ajustar formato en `export_text()` y `export_excel()`.
- **Base de datos**: Sin impacto — los valores se siguen almacenando como números.
- **API**: Sin impacto — el JSON devuelve números crudos (correcto para cálculo).

---

## Propuesta de Solución

### Filtro de template personalizado `currency_cop`

Crear el filtro en `web/apps/core/templatetags/currency_filters.py` (app base del proyecto,
disponible globalmente). El filtro transforma cualquier valor numérico al formato colombiano:

```python
@register.filter
def currency_cop(value):
    """Formatea un valor numérico como peso colombiano: $456.602.069"""
    try:
        n = int(round(float(value)))
        return f'${n:,}'.replace(',', '.')
    except (ValueError, TypeError):
        return value
```

---

## Plan de Implementación

### 1. Crear templatetag

**Nuevos archivos:**
- `web/apps/core/templatetags/__init__.py` (vacío)
- `web/apps/core/templatetags/currency_filters.py` (filtro `currency_cop`)

### 2. Aplicar en `web/templates/analysis/results.html`

Agregar `{% load currency_filters %}` al inicio del template.

Reemplazar los tres usos de `|floatformat:0` monetarios:

| Campo | Antes | Después |
|-------|-------|---------|
| `exp_result.valor_requerido_cop` (~línea 131) | `\|floatformat:0` con `$` literal | `\|currency_cop` |
| `exp_result.total_valor_cop` (~línea 141) | `\|floatformat:0` con `$` literal | `\|currency_cop` |
| `rup.valor_cop` (~línea 186) | `${{ rup.valor_cop\|floatformat:0 }}` | `{{ rup.valor_cop\|currency_cop }}` |

> El filtro ya incluye el símbolo `$`, eliminar los literales `$` que preceden el tag en el HTML.

### 3. Actualizar `export_text()` en `web/apps/analysis/views.py` (~líneas 454, 456, 465)

Cambiar separador de miles de coma (US) a punto (colombiano):

```python
# Antes
f'${exp.valor_requerido_cop:,.0f} COP'

# Después
f"${int(round(exp.valor_requerido_cop)):,} COP".replace(',', '.')
```

Aplicar el mismo patrón a `total_valor_cop` y `valor_cop`.

### 4. Actualizar `export_excel()` en `web/apps/analysis/views.py` (~líneas 349, 356)

Definir helper local y escribir valores formateados como string:

```python
def fmt_cop(v):
    try:
        return f"${int(round(float(v))):,}".replace(',', '.')
    except Exception:
        return v
```

Aplicar `fmt_cop()` a `exp_result.valor_requerido_cop` y `rup.valor_cop` en los `ws_exp.append(...)`.

---

## Archivos a modificar

| Archivo | Tipo de cambio |
|---------|----------------|
| `web/apps/core/templatetags/__init__.py` | Crear (nuevo, vacío) |
| `web/apps/core/templatetags/currency_filters.py` | Crear (nuevo, filtro `currency_cop`) |
| `web/templates/analysis/results.html` | Modificar — cargar filtro y aplicar en 3 lugares |
| `web/apps/analysis/views.py` | Modificar — `export_text()` y `export_excel()` |

---

## Verificación

1. Abrir `/analysis/<pk>/results/` → sección Experiencia debe mostrar `$456.602.069` en:
   - "Valor requerido"
   - "Total acreditado"
   - Columna "Valor" de la tabla RUP por contrato
2. Descargar exportación TXT → valores deben aparecer como `$456.602.069 COP`
3. Descargar exportación Excel → columnas de valor deben mostrar `$456.602.069` (string)
4. Verificar que `score_objeto` (no monetario, usa `|floatformat:3`) **no** se ve afectado
5. Verificar que campos `None` o vacíos no generen excepción (el filtro retorna el valor sin cambios)
