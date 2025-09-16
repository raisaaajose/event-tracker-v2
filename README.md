# event-tracker-v2

## Dockerized Setup

- Services: `api` (FastAPI) and `db` (Postgres 16).
- Prisma manages the schema found in `prisma/schema.prisma`.

### Prerequisites

- Docker Desktop installed and running.
- Copy `.env.template` to `.env` and update the database password:

  ```pwsh
  Copy-Item .env.template .env
  # Edit .env file and replace "your_password_here" with a secure password
  ```

### Quick start (Windows PowerShell)

```pwsh
# Start the application
docker compose up --build

# For development with hot reload (mounts source code):
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Initialize database only (useful for first-time setup):
docker compose --profile init up --build
```

- API: <http://localhost:8000>
- Health: <http://localhost:8000/ping>

The API container will:

- wait for the DB to be reachable,
- run `prisma generate`,
- push the schema (`prisma db push`),
- and then start `uvicorn`.

### Common commands

```pwsh
# Start in background
docker compose up -d --build

# View logs
docker compose logs -f api

# Recreate only API after code change
docker compose up -d --build api

# Stop and remove containers
docker compose down

# Wipe DB volume as well
docker compose down -v
```

### Faster dev cycles

- Use reload and skip Prisma steps:

```pwsh
# Using dev override file (recommended for local dev)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Or set flags ad-hoc
$env:UVICORN_RELOAD=1; $env:PRISMA_GENERATE=0; $env:PRISMA_DB_PUSH=0; docker compose up --build
```

- When you change the Prisma schema and need a client/db update:

```pwsh
$env:PRISMA_GENERATE=1; docker compose run --rm api python -m prisma generate
$env:PRISMA_DB_PUSH=1; docker compose run --rm api python -m prisma db push --accept-data-loss
```

### One-off Prisma init (separate job)

Run Prisma generate + db push via a dedicated init service:

```pwsh
docker compose --profile init up --build init
```

### Build speed tips

- Enable Docker BuildKit (usually on by default in Docker Desktop). The Dockerfile uses cache mounts for apt and uv to speed rebuilds.
- Dependency cache hits occur when `pyproject.toml` and `uv.lock` are unchanged.

### Environment

By default, `DATABASE_URL` is set for Compose as:

```text
postgresql://postgres:postgres@db:5432/event_tracker
```

You can override it in `docker-compose.yml` or by using an `.env` file.
