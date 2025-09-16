# Event Tracker V2

A FastAPI-based event tracking application with PostgreSQL database support.

## Features

- FastAPI web framework
- PostgreSQL database with Prisma ORM
- Docker containerization
- Development and production configurations

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

2. Copy the environment file:

```bash
cp .env.example .env
```

3. Start the application with Docker Compose:

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

2. Set up environment variables:

```bash
cp .env.example .env
# Edit .env with your database configuration
```

3. Generate Prisma client:

```bash
uv run prisma generate
```

4. Run database migrations:

```bash
uv run prisma migrate deploy
```

5. Start the development server:

```bash
uv run uvicorn app.main:app --reload
```

## API Endpoints

- `GET /` - Root endpoint
- `GET /ping` - Simple ping endpoint
- `GET /health` - Health check endpoint
- `GET /docs` - Interactive API documentation (Swagger UI)

## Database

The application uses PostgreSQL with Prisma ORM. The database schema is defined in `prisma/schema.prisma`.

## Docker Services

- **app**: FastAPI application (development mode with hot reload)
- **db**: PostgreSQL 15 database
- **app-prod**: Production-ready FastAPI application (commented out by default)

## Environment Variables

See `.env.example` for required environment variables:

- `DATABASE_URL`: PostgreSQL connection string
- `ENVIRONMENT`: Application environment (development/production)
- `DEBUG`: Enable debug mode
- `SECRET_KEY`: Application secret key
