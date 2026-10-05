from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """{{ photos|get_item:name }}: look up a key in a dictionary."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None
