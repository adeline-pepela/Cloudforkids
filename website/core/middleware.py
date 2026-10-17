from .translation import load_map, translate_html


class UITranslationMiddleware:
    """When the visitor reads Kiswahili, translate the fixed wording of HTML pages (not the admin)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        language = getattr(request, "LANGUAGE_CODE", "en")
        _remember_language(request, language)
        if (
            language.startswith("sw")
            and response.status_code == 200
            and "text/html" in response.get("Content-Type", "")
            and not request.path.startswith("/admin")
            and not response.streaming
        ):
            html = response.content.decode(response.charset or "utf-8")
            response.content = translate_html(html, load_map()).encode(response.charset or "utf-8")
            if response.has_header("Content-Length"):
                response["Content-Length"] = str(len(response.content))
        return response


def _remember_language(request, language):
    """Emails follow the language a signed-in person picked with the EN/SW switch (the cookie it sets)."""
    from django.conf import settings
    from django.contrib.auth import get_user_model

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or settings.LANGUAGE_COOKIE_NAME not in request.COOKIES:
        return
    code = "sw" if language.startswith("sw") else "en"
    if getattr(user, "language", code) != code:
        get_user_model().objects.filter(pk=user.pk).update(language=code)
        user.language = code
