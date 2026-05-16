"""
format_text.py — Template filters para presentar texto almacenado en MAYÚSCULAS
con formato legible en las vistas de cliente.

Uso en plantillas:
    {% load format_text %}
    {{ producto.nombre|titulo_legible }}        → "Matcha latte"
    {{ categoria.nombre|titulo_legible }}       → "Bebidas calientes"
    {{ producto.descripcion|parrafo_legible }}  → Oraciones con primera letra mayúscula
"""

from django import template

register = template.Library()


@register.filter(name="titulo_legible")
def titulo_legible(value):
    """
    Convierte un texto en MAYÚSCULAS a formato de título legible:
    primera letra de cada palabra en mayúscula, el resto en minúsculas.
    Ejemplo: "MATCHA LATTE CON LECHE" → "Matcha Latte Con Leche"
    """
    if not value:
        return value
    return str(value).title()


@register.filter(name="primera_mayuscula")
def primera_mayuscula(value):
    """
    Solo la primera letra del texto en mayúscula, el resto en minúsculas.
    Útil para nombres de productos en oraciones.
    Ejemplo: "MATCHA LATTE" → "Matcha latte"
    """
    if not value:
        return value
    s = str(value).lower()
    return s[0].upper() + s[1:] if s else s


@register.filter(name="parrafo_legible")
def parrafo_legible(value):
    """
    Convierte MAYÚSCULAS a minúsculas conservando la primera letra del párrafo
    en mayúscula. Ideal para descripciones largas.
    Ejemplo: "BEBIDA CALIENTE CON ESPUMA" → "Bebida caliente con espuma"
    """
    if not value:
        return value
    s = str(value).lower()
    return s[0].upper() + s[1:] if s else s
