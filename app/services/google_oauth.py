from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.datastructures import Secret

config = Config(".env")

GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID", cast=str, default=None)
GOOGLE_CLIENT_SECRET = config("GOOGLE_CLIENT_SECRET", cast=Secret, default=None)
GOOGLE_REDIRECT_URI = config(
    "GOOGLE_REDIRECT_URI",
    cast=str,
    default="http://localhost:8000/auth/google/callback",
)


GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

oauth = OAuth()

oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=str(GOOGLE_CLIENT_SECRET) if GOOGLE_CLIENT_SECRET else None,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": " ".join(GOOGLE_SCOPES)},
    redirect_uri=GOOGLE_REDIRECT_URI,
)
