"""Per-user locale fallback for clients that do not send Accept-Language."""

from django.utils import translation


class UserLanguageMiddleware:
    """Use a signed-in user's saved language when the request has no preference."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and getattr(user, "is_authenticated", False)
            and not request.headers.get("Accept-Language")
        ):
            language = getattr(user, "language", "en-us") or "en-us"
            translation.activate(language)
            request.LANGUAGE_CODE = language
        return self.get_response(request)
