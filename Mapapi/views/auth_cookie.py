"""Vues d'authentification déposant le JWT dans des cookies httpOnly.

login → pose access_token + refresh_token (httpOnly) + un cookie csrftoken (lisible
par le SPA pour renvoyer X-CSRFToken). refresh → relit le refresh depuis le cookie.
logout → efface les cookies. Les tokens restent aussi dans le corps JSON pour le
mobile (Bearer) et la transition.
"""
from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


def _set_auth_cookies(request, response, access=None, refresh=None):
    """Pose les cookies JWT httpOnly. Secure + SameSite=None en HTTPS (cross-site
    prod : front et back sur des domaines différents) ; Lax + non-secure en HTTP local."""
    secure = request.is_secure()
    samesite = 'None' if secure else 'Lax'
    common = dict(httponly=True, secure=secure, samesite=samesite, path='/')
    if access:
        response.set_cookie(
            settings.AUTH_COOKIE_ACCESS, access,
            max_age=settings.AUTH_COOKIE_ACCESS_MAX_AGE, **common,
        )
    if refresh:
        response.set_cookie(
            settings.AUTH_COOKIE_REFRESH, refresh,
            max_age=settings.AUTH_COOKIE_REFRESH_MAX_AGE, **common,
        )


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CookieTokenObtainPairView(TokenObtainPairView):
    """POST /login/ — pose les cookies httpOnly + renvoie aussi les tokens (mobile)."""

    # Le login établit l'authentification (via identifiants) ; il ne doit PAS faire
    # tourner l'auth par cookie (sinon un cookie résiduel déclencherait une
    # vérif CSRF et bloquerait la reconnexion).
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            _set_auth_cookies(
                request, response,
                access=response.data.get('access'),
                refresh=response.data.get('refresh'),
            )
            get_token(request)  # garantit l'émission du cookie csrftoken
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """POST /token/refresh/ — relit le refresh depuis le corps OU le cookie."""

    # Le refresh s'authentifie via le refresh token lui-même, pas via l'access
    # cookie → pas d'auth par cookie ici (donc pas de blocage CSRF).
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        refresh = request.data.get('refresh') or request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        serializer = self.get_serializer(data={'refresh': refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0])
        response = Response(serializer.validated_data, status=status.HTTP_200_OK)
        _set_auth_cookies(
            request, response,
            access=serializer.validated_data.get('access'),
            refresh=serializer.validated_data.get('refresh'),
        )
        return response


class CookieLogoutView(APIView):
    """POST /logout/ — efface les cookies d'authentification.

    Sans authentification ni CSRF : la déconnexion (effacer les cookies) doit
    toujours réussir, même avec un token expiré/absent."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        response = Response({'detail': 'Déconnecté.'}, status=status.HTTP_200_OK)
        response.delete_cookie(settings.AUTH_COOKIE_ACCESS, path='/')
        response.delete_cookie(settings.AUTH_COOKIE_REFRESH, path='/')
        return response
