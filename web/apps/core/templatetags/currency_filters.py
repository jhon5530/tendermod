from django import template

register = template.Library()


@register.filter
def currency_cop(value):
    """Formatea un valor numérico como peso colombiano: $456.602.069"""
    try:
        n = int(round(float(value)))
        return f'${n:,}'.replace(',', '.')
    except (ValueError, TypeError):
        return value
