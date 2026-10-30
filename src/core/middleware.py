"""Select a persisted account locale before Django's LocaleMiddleware runs."""


class UserLanguageMiddleware:
    """Use an authenticated user's saved language when no header was sent.

    This middleware must run after AuthenticationMiddleware and before
    LocaleMiddleware. It supplies the missing Accept-Language header instead
    of activating a translation itself, so LocaleMiddleware also sets the
    correct response Content-Language and applies normal cleanup semantics.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and getattr(user, "is_authenticated", False)
            and not request.headers.get("Accept-Language")
        ):
            language = getattr(user, "language", None)
            if language:
                request.META["HTTP_ACCEPT_LANGUAGE"] = language
        return self.get_response(request)
