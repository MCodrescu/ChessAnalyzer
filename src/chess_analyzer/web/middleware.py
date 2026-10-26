"""Shared private access for small, HTTPS-only deployments."""

import base64
import binascii

from django.conf import settings
from django.http import HttpResponse
from django.utils.crypto import constant_time_compare


class PrivateAccessMiddleware:
    """Require HTTP Basic credentials except for the lightweight health endpoint.

    Production settings require both credentials. Local development stays open
    when neither is set. Static assets are public via the preceding WhiteNoise
    middleware; application responses are never cacheable when access is enabled.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info == "/healthz/" or not (
            settings.BASIC_AUTH_USERNAME or settings.BASIC_AUTH_PASSWORD
        ):
            return self.get_response(request)
        if self._authorized(request):
            response = self.get_response(request)
        else:
            response = HttpResponse("Authentication required.", status=401)
            response["WWW-Authenticate"] = (
                'Basic realm="ChessAnalyzer", charset="UTF-8"'
            )
        response["Cache-Control"] = "private, no-store"
        return response

    @staticmethod
    def _authorized(request):
        parts = request.headers.get("Authorization", "").split()
        if len(parts) != 2 or parts[0].lower() != "basic":
            return False
        try:
            decoded = base64.b64decode(parts[1], validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return False
        username_matches = constant_time_compare(username, settings.BASIC_AUTH_USERNAME)
        password_matches = constant_time_compare(password, settings.BASIC_AUTH_PASSWORD)
        return username_matches & password_matches
