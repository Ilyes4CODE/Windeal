# App: auth_app | File: social.py
"""
Google / Apple sign-in token verification.

Verifies the provider's signed ID/identity token against the provider's public
JWKS (JSON Web Key Set) using PyJWT — no extra dependency beyond PyJWT, which is
already installed. Audience (client-id) checking is enforced when the relevant
*_CLIENT_IDS setting is configured.
"""
import jwt
from jwt import PyJWKClient
from django.conf import settings

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS   = ("accounts.google.com", "https://accounts.google.com")

APPLE_CERTS_URL  = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER     = "https://appleid.apple.com"


class SocialVerifyError(Exception):
    """Raised when a provider token cannot be verified."""


# Cache one JWKS client per certs URL (each caches keys internally).
_jwk_clients = {}


def _jwk_client(url):
    client = _jwk_clients.get(url)
    if client is None:
        client = PyJWKClient(url)
        _jwk_clients[url] = client
    return client


def _decode(token, certs_url, issuers, audiences):
    try:
        signing_key = _jwk_client(certs_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=audiences or None,
            options={"verify_aud": bool(audiences)},
        )
    except Exception as exc:  # jwt errors, network errors, malformed token…
        raise SocialVerifyError(f"token verification failed: {exc}")

    iss = claims.get("iss")
    if isinstance(issuers, (tuple, list)):
        if iss not in issuers:
            raise SocialVerifyError("invalid issuer")
    elif iss != issuers:
        raise SocialVerifyError("invalid issuer")

    sub = claims.get("sub")
    if not sub:
        raise SocialVerifyError("token has no subject")
    return claims, sub


def verify_google(id_token_str):
    """Return {'sub','email','name'} for a valid Google ID token, else raise."""
    claims, sub = _decode(id_token_str, GOOGLE_CERTS_URL, GOOGLE_ISSUERS,
                          getattr(settings, "GOOGLE_CLIENT_IDS", []))
    return {"sub": sub, "email": claims.get("email"), "name": claims.get("name")}


def verify_apple(identity_token_str):
    """Return {'sub','email','name'} for a valid Apple identity token, else raise."""
    claims, sub = _decode(identity_token_str, APPLE_CERTS_URL, APPLE_ISSUER,
                          getattr(settings, "APPLE_CLIENT_IDS", []))
    return {"sub": sub, "email": claims.get("email"), "name": None}
