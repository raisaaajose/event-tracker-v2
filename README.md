# Event Tracker V2

FastAPI + Prisma backend with Google OAuth, Gmail ingestion → LLM extraction → Google Calendar creation, and interests/profile APIs.

Quick start

- Copy envs and edit values:

  - Windows (PowerShell): `Copy-Item .env.template .env`
  - Unix: `cp .env.template .env`

- Run with Docker:

  - `docker compose up --build`

- Or run locally:
  - `uv sync`
  - `uv run prisma generate && uv run prisma migrate deploy`
  - `uv run uvicorn app.main:app --reload`

Essential envs (.env)

- `DATABASE_URL`: Postgres URL
- `SECRET_KEY`: random string
- `FRONTEND_URL`: origin of your frontend (e.g., <http://localhost:5173>)
- Google OAuth: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- Sessions (optional tuning): `SESSION_COOKIE`, `SESSION_DOMAIN`, `SESSION_SAMESITE`, `SESSION_SECURE`, `SESSION_MAX_AGE_DAYS`
- `EMAIL_SYNC_INTERVAL_SECONDS`: default 3600

Auth flow

- Start login: `GET /auth/google/login` (also supports POST)
- Callback: `GET /auth/google/callback` → upserts user + tokens, sets session
- All other routes require a session; user_id is taken from session (no user_id in payloads)

Docs

- Swagger UI: `/docs` (public)
- ReDoc: `/redoc` (public)
- OpenAPI: `/openapi.json`

Endpoints (high-level)

- Interests: `/interests` (list), `/interests/me` (get/set), `/interests/me/custom` (create/delete)
- Events: `/events` (list with `limit`, `offset`)
- Users: `/users/me/profile`
- Health: `/health`, `/ping`, root `/`

Notes

- Gmail ingestion is queued; messages flow into an LLM (stubbed) that proposes events → we create them in Google Calendar and persist to DB.
- For cross-origin sessions in production, set `SESSION_SAMESITE=none` and `SESSION_SECURE=true`; consider `SESSION_DOMAIN`.

Google Cloud setup (brief)

- Create OAuth client (Web) with redirect: `http://localhost:8000/auth/google/callback`
- Set client id/secret in `.env`; adjust scopes in `app/services/google_oauth.py` if needed

That’s it — see `/docs` for full API details.
