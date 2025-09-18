# Event Tracker V2

A FastAPI-based event tracking application with PostgreSQL database support.

## Features

- FastAPI web framework
- PostgreSQL database with Prisma ORM
- Docker containerization
- Development and production configurations
- Google OAuth2 login (prepared) with Gmail read + Calendar events scopes

## Quick Start with Docker

### Prerequisites

- Docker
- Docker Compose

### Development Setup

1. Clone the repository:

```bash
git clone <repository-url>
cd event-tracker-v2
```

1. Copy the environment file:

```bash
cp .env.example .env
```

1. Start the application with Docker Compose:

```bash
docker-compose up --build
```

The application will be available at:

- API: <http://localhost:8000>
- Health Check: <http://localhost:8000/health>
- Interactive API docs: <http://localhost:8000/docs>

### Production Deployment

For production, uncomment the `app-prod` service in `docker-compose.yml` and use:

```bash
docker-compose up app-prod db --build
```

## Manual Setup (without Docker)

### Requirements

- Python 3.12+
- PostgreSQL
- uv (Python package manager)

### Installation

1. Install dependencies:

```bash
uv sync
```

1. Set up environment variables:

```bash
cp .env.example .env
# Edit .env with your database configuration
```

1. Generate Prisma client:

```bash
uv run prisma generate
```

1. Run database migrations:

```bash
uv run prisma migrate deploy
```

1. Start the development server:

````bash
uv run uvicorn app.main:app --reload

## Google OAuth2

This project includes endpoints to authenticate users with Google and persist OAuth tokens for future Gmail reading and Calendar event updates.

### Scopes

We request these scopes:

- openid, email, profile
- https://www.googleapis.com/auth/gmail.readonly
- https://www.googleapis.com/auth/calendar.events

You can adjust scopes in `app/services/google_oauth.py`.

### Google Cloud Console Setup

1. Create a project at <https://console.cloud.google.com/>
2. Configure OAuth consent screen:
	- User type: External (for testing) or Internal as appropriate
	- Add the above scopes
	- Add test users (emails) if app is not published
3. Create OAuth 2.0 Client ID (type: Web application):
	- Authorized redirect URIs:
	  - <http://localhost:8000/auth/google/callback>
	- Optional: Authorized JavaScript origins for your frontend
4. Copy the client credentials into `.env`:

```env
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
FRONTEND_URL=http://localhost:5173
````

### Database Migration (GoogleAccount)

We store OAuth tokens in a `GoogleAccount` table linked to `User`.

Run migrations to apply the new schema:

```powershell
# Using Docker
docker-compose --profile tools run --rm migrate python -m prisma migrate deploy

# Or locally (ensure DB is running and env is set)
python -m prisma generate
python -m prisma migrate deploy
```

### Endpoints

- `GET /auth/google/login` → Redirects to Google OAuth consent
- `GET /auth/google/callback` → Handles Google callback, upserts user and tokens

On success, if `FRONTEND_URL` is set, the API redirects there with `?login=success&user_id=<id>`; otherwise, it returns a JSON payload with basic user info.

### Using Tokens for Gmail/Calendar

Use the helper in `app/services/google_api.py` to retrieve a valid (auto-refreshed) access token:

```python
from app.services.google_api import get_user_google_token
token = await get_user_google_token(user_id)
# token['access_token'] usable with Google APIs via httpx or google-api-python-client
```

Future endpoints can leverage this to read Gmail messages and create/update Calendar events.

````

## API Endpoints

- `GET /` - Root endpoint
- `GET /ping` - Simple ping endpoint
- `GET /health` - Health check endpoint
- `GET /docs` - Interactive API documentation (Swagger UI)

## Database

The application uses PostgreSQL with Prisma ORM. The database schema is defined in `prisma/schema.prisma`.

### Database Migrations

The project includes a dedicated migration service for managing database schema changes.

#### Using the Migration Service

**Start the database:**

```bash
docker-compose up db -d
````

**Run migrations:**

```bash
# Apply pending migrations
docker-compose --profile tools run --rm migrate

# Or use the migration scripts:
# Linux/macOS:
./migrate.sh migrate:deploy

# Windows:
migrate.bat migrate:deploy
```

**Create a new migration:**

```bash
# Linux/macOS:
./migrate.sh migrate:dev add_new_table

# Windows:
migrate.bat migrate:dev add_new_table
```

**Check migration status:**

```bash
# Linux/macOS:
./migrate.sh migrate:status

# Windows:
migrate.bat migrate:status
```

**Other migration commands:**

```bash
# Generate Prisma client
./migrate.sh generate        # Linux/macOS
migrate.bat generate         # Windows

# Reset database (WARNING: loses all data)
./migrate.sh migrate:reset   # Linux/macOS
migrate.bat migrate:reset    # Windows

# Start Prisma Studio (database browser)
./migrate.sh studio          # Linux/macOS
migrate.bat studio           # Windows
```

## Docker Services

- **app**: FastAPI application (development mode with hot reload)
- **db**: PostgreSQL 15 database
- **migrate**: Database migration service (run with `--profile tools`)
- **app-prod**: Production-ready FastAPI application (commented out by default)

## Environment Variables

See `.env.example` for required environment variables:

- `DATABASE_URL`: PostgreSQL connection string
- `ENVIRONMENT`: Application environment (development/production)
- `DEBUG`: Enable debug mode
- `SECRET_KEY`: Application secret key
