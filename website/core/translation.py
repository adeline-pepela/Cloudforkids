"""Shows the site in Kiswahili: swaps known English wording for the Kiswahili in the UITranslation table."""

import re

from django.core.cache import cache

CACHE_KEY = "ui-translations-sw-v1"
SKIP = r"<script\b.*?</script>|<style\b.*?</style>|<textarea\b.*?</textarea>|<pre\b.*?</pre>|<code\b.*?</code>"
TEXT_NODE = re.compile(r"(" + SKIP + r")|>([^<>]+)<", re.S | re.I)
ATTRIBUTE = re.compile(r'(\s(?:placeholder|title|aria-label|alt)=")([^"<>]+)(")')
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def load_map():
    mapping = cache.get(CACHE_KEY)
    if mapping is None:
        from .models import UITranslation

        mapping = {re.sub(r"\s+", " ", e).strip(): s for e, s in UITranslation.objects.values_list("english", "swahili")}
        cache.set(CACHE_KEY, mapping, 600)
    return mapping


def clear_cache():
    cache.delete(CACHE_KEY)


def _lookup(text, mapping):
    key = re.sub(r"\s+", " ", text).strip()
    if not key or not re.search(r"[A-Za-z]", key):
        return None
    if key in mapping:
        return mapping[key]
    numbers = NUMBER.findall(key)
    if numbers:
        found = mapping.get(NUMBER.sub("{n}", key))
        if found:
            it = iter(numbers)
            return re.sub(r"\{n\}", lambda m: next(it, "0"), found)
    return None


def translate_html(html, mapping):
    def node(match):
        if match.group(1):
            return match.group(1)
        text = match.group(2)
        swahili = _lookup(text, mapping)
        if swahili is None:
            return match.group(0)
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        return f">{lead}{swahili}{trail}<"

    def attribute(match):
        swahili = _lookup(match.group(2), mapping)
        return f"{match.group(1)}{swahili.replace(chr(34), chr(39))}{match.group(3)}" if swahili else match.group(0)

    return ATTRIBUTE.sub(attribute, TEXT_NODE.sub(node, html))
