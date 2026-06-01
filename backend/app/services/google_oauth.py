"""Google OAuth client (Authlib). Returns None until GOOGLE_CLIENT_ID/SECRET are configured,
so the endpoints can 503 gracefully when Google login isn't set up.
"""

from authlib.integrations.starlette_client import OAuth

from app.core.config import get_settings

_oauth: OAuth | None = None
_GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"


def get_oauth() -> OAuth | None:
    global _oauth
    s = get_settings()
    if not s.google_client_id or not s.google_client_secret:
        return None
    if _oauth is None:
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=s.google_client_id,
            client_secret=s.google_client_secret,
            server_metadata_url=_GOOGLE_METADATA,
            client_kwargs={"scope": "openid email profile"},
        )
        _oauth = oauth
    return _oauth
