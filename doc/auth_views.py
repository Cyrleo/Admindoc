import json
import secrets
import urllib.error
import urllib.request

from django.conf import settings
from django.contrib.auth import login
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from google_auth_oauthlib.flow import Flow
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User


GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_OAUTH_STATE_CACHE_PREFIX = "google-oauth-state"
GOOGLE_OAUTH_STATE_TTL_SECONDS = 15 * 60


def _state_cache_key(state):
    return f"{GOOGLE_OAUTH_STATE_CACHE_PREFIX}:{state}"


def _store_oauth_state(state, payload):
    cache.set(_state_cache_key(state), payload, timeout=GOOGLE_OAUTH_STATE_TTL_SECONDS)


def _pop_oauth_state(state):
    key = _state_cache_key(state)
    payload = cache.get(key)
    if payload is not None:
        cache.delete(key)
    return payload


def _build_google_flow(request, state=None):
    redirect_uri = getattr(
        settings,
        "SOCIAL_AUTH_GOOGLE_OAUTH2_REDIRECT_URI",
        request.build_absolute_uri(reverse("google-auth-callback")),
    )
    client_id = getattr(settings, "SOCIAL_AUTH_GOOGLE_OAUTH2_KEY", "")
    client_secret = getattr(settings, "SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET", "")

    if not client_id or not client_secret:
        raise ValueError("Google OAuth credentials are not configured.")

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=getattr(
            settings,
            "SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE",
            [
                "openid",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
            ],
        ),
        state=state,
    )
    flow.redirect_uri = redirect_uri
    return flow


def _fetch_google_userinfo(access_token):
    request = urllib.request.Request(
        GOOGLE_USERINFO_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


class GoogleAuthStartView(View):
    def get(self, request):
        try:
            flow = _build_google_flow(request)
        except ValueError as exc:
            return render(
                request,
                "accounts/google_auth_callback.html",
                {
                    "status": "error",
                    "error": str(exc),
                    "provider": "Google",
                },
                status=500,
            )

        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent select_account",
        )
        request.session["google_oauth_state"] = state
        request.session["google_oauth_next"] = request.GET.get("next", "")
        request.session["google_oauth_nonce"] = secrets.token_urlsafe(16)
        _store_oauth_state(
            state,
            {
                "next_url": request.GET.get("next", ""),
                "created_at": timezone.now().isoformat(),
            },
        )
        return HttpResponseRedirect(authorization_url)


class GoogleAuthCallbackView(View):
    template_name = "accounts/google_auth_callback.html"

    def get(self, request):
        error = request.GET.get("error")
        code = request.GET.get("code")
        state = request.GET.get("state")
        expected_state = request.session.get("google_oauth_state")
        cached_state_payload = _pop_oauth_state(state) if state else None
        next_url = (
            request.session.get("google_oauth_next")
            or (cached_state_payload or {}).get("next_url", "")
            or request.GET.get("next", "")
        )

        if error:
            return render(
                request,
                self.template_name,
                {
                    "status": "error",
                    "error": error,
                    "provider": "Google",
                    "next_url": next_url,
                },
                status=400,
            )

        if not code or not state:
            return render(
                request,
                self.template_name,
                {
                    "status": "error",
                    "error": "Missing code or state parameter.",
                    "provider": "Google",
                    "next_url": next_url,
                },
                status=400,
            )

        session_state_valid = bool(expected_state and state == expected_state)
        cache_state_valid = cached_state_payload is not None
        if not session_state_valid and not cache_state_valid:
            return render(
                request,
                self.template_name,
                {
                    "status": "error",
                    "error": (
                        "Invalid or expired OAuth state. "
                        "Vérifie que tu lances et termines le flow sur le même host "
                        "(localhost ou 127.0.0.1, mais pas les deux)."
                    ),
                    "provider": "Google",
                    "next_url": next_url,
                },
                status=400,
            )

        try:
            flow = _build_google_flow(request, state=state)
            flow.fetch_token(code=code)
            credentials = flow.credentials
            google_profile = _fetch_google_userinfo(credentials.token)
        except urllib.error.HTTPError as exc:
            return render(
                request,
                self.template_name,
                {
                    "status": "error",
                    "error": f"Google userinfo request failed: {exc.reason}",
                    "provider": "Google",
                    "next_url": next_url,
                },
                status=400,
            )
        except Exception as exc:
            return render(
                request,
                self.template_name,
                {
                    "status": "error",
                    "error": str(exc),
                    "provider": "Google",
                    "next_url": next_url,
                },
                status=500,
            )

        email = google_profile.get("email", "").strip().lower()
        if not email:
            return render(
                request,
                self.template_name,
                {
                    "status": "error",
                    "error": "Google account did not return an email address.",
                    "provider": "Google",
                    "next_url": next_url,
                },
                status=400,
            )

        first_name = google_profile.get("given_name", "").strip()
        last_name = google_profile.get("family_name", "").strip()

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
                "is_verified": bool(google_profile.get("email_verified", True)),
            },
        )

        changed_fields = []
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed_fields.append("first_name")
        if last_name and user.last_name != last_name:
            user.last_name = last_name
            changed_fields.append("last_name")
        if not user.is_active:
            user.is_active = True
            changed_fields.append("is_active")
        if google_profile.get("email_verified", False) and not user.is_verified:
            user.is_verified = True
            changed_fields.append("is_verified")
        if created:
            user.set_unusable_password()
            changed_fields.append("password")
        if changed_fields:
            user.save(update_fields=sorted(set(changed_fields)))

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        refresh = RefreshToken.for_user(user)

        request.session.pop("google_oauth_state", None)
        request.session.pop("google_oauth_next", None)
        request.session.pop("google_oauth_nonce", None)

        token_pair = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

        return render(
            request,
            self.template_name,
            {
                "status": "success",
                "provider": "Google",
                "created": created,
                "next_url": next_url,
                "user": user,
                "google_profile": google_profile,
                "google_profile_json": json.dumps(google_profile, indent=2, ensure_ascii=False, sort_keys=True),
                "token_pair": token_pair,
            },
        )