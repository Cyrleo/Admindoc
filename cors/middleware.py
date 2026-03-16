from .request_context import clear_current_user, set_current_user


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            set_current_user(user)
        else:
            clear_current_user()

        try:
            response = self.get_response(request)
        finally:
            clear_current_user()

        return response
