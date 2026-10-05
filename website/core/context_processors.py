from .models import SiteSetting


def site_settings(request):
    """`site` = the editable website wording and contact details (Admin > Site settings)."""
    return {"site": SiteSetting.load()}


def language(request):
    """Current language, the language list for the switcher, and the browser-script messages."""
    from .js_strings import js_json

    code = getattr(request, "LANGUAGE_CODE", "en")
    return {"is_swahili": code.startswith("sw"), "js_i18n": js_json(code), "language_code": code[:2]}


PHOTO_CACHE = "site-photos-v1"


def site_photos(request):
    """`photos` = {slot: {src, alt, credit_name, credit_url}} for the photo slots managed in the admin."""
    from django.core.cache import cache

    from .models import SitePhoto

    data = cache.get(PHOTO_CACHE)
    if data is None:
        data = {
            p.slot: {"src": p.src, "alt": p.alt, "credit_name": p.credit_name, "credit_url": p.credit_url}
            for p in SitePhoto.objects.all() if p.src
        }
        cache.set(PHOTO_CACHE, data, 600)
    return {"photos": data}
