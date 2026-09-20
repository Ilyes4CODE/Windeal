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


import ssl
import os

# Cache JWKS clients: key is (url, unverified)
_jwk_clients = {}


def _get_ssl_context():
    """Create an SSL context using system or certifi certificates."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass

    for ca_path in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"):
        if os.path.exists(ca_path):
            try:
                return ssl.create_default_context(cafile=ca_path)
            except Exception:
                pass

    if getattr(settings, "DEBUG", False):
        return ssl._create_unverified_context()

    return ssl.create_default_context()


def _jwk_client(url, unverified=False):
    key = (url, unverified)
    client = _jwk_clients.get(key)
    if client is None:
        ctx = ssl._create_unverified_context() if unverified else _get_ssl_context()
        client = PyJWKClient(url, ssl_context=ctx)
        _jwk_clients[key] = client
    return client


def _decode(token, certs_url, issuers, audiences):
    try:
        try:
            signing_key = _jwk_client(certs_url).get_signing_key_from_jwt(token).key
        except Exception as jwk_err:
            if "CERTIFICATE_VERIFY_FAILED" in str(jwk_err) and getattr(settings, "DEBUG", False):
                signing_key = _jwk_client(certs_url, unverified=True).get_signing_key_from_jwt(token).key
            else:
                raise
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=audiences or None,
            options={"verify_aud": bool(audiences)},
        )
    except Exception as exc:  # jwt errors, network errors, malformed token…
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("[Social Auth] Verification failed: %s", exc)
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            logger.warning(
                "[Social Auth] Unverified token: aud=%s (configured=%s), iss=%s, email=%s",
                unverified.get("aud"), audiences, unverified.get("iss"), unverified.get("email"),
            )
        except Exception as parse_err:
            logger.warning("[Social Auth] Token is not a valid JWT (%s). Starts with: %r", parse_err, token[:30] if token else "")
        raise SocialVerifyError(f"{exc}")

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
