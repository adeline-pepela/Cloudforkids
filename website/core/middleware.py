from .translation import load_map, translate_html


class UITranslationMiddleware:
    """When the visitor reads Kiswahili, translate the fixed wording of HTML pages (not the admin)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        language = getattr(request, "LANGUAGE_CODE", "en")
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
