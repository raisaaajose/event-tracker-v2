#!/bin/bash

# Database Migration Script for Event Tracker V2
# This script provides various database migration commands

set -e

# Configuration
DB_SERVICE="db"
MIGRATE_SERVICE="migrate"
COMPOSE_FILE="docker-compose.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if database is running
check_db() {
    print_status "Checking database status..."
    if docker-compose ps $DB_SERVICE | grep -q "Up"; then
        print_status "Database is running"
        return 0
    else
        print_error "Database is not running. Please start it first with: docker-compose up db -d"
        return 1
    fi
}

# Function to run migrations
migrate_deploy() {
    print_status "Running database migrations..."
    if check_db; then
        docker-compose run --rm $MIGRATE_SERVICE python -m prisma migrate deploy
        print_status "Migrations completed successfully"
    fi
}

# Function to create a new migration
migrate_dev() {
    if [ -z "$1" ]; then
        print_error "Migration name is required"
        echo "Usage: $0 migrate:dev <migration_name>"
        exit 1
    fi
    
    print_status "Creating new migration: $1"
    if check_db; then
        docker-compose run --rm $MIGRATE_SERVICE python -m prisma migrate dev --name "$1"
        print_status "Migration '$1' created successfully"
    fi
}

# Function to reset database
migrate_reset() {
    print_warning "This will reset the database and lose all data!"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Resetting database..."
        if check_db; then
            docker-compose run --rm $MIGRATE_SERVICE python -m prisma migrate reset --force
            print_status "Database reset completed"
        fi
    else
        print_status "Database reset cancelled"
    fi
}

# Function to show migration status
migrate_status() {
    print_status "Checking migration status..."
    if check_db; then
        docker-compose run --rm $MIGRATE_SERVICE python -m prisma migrate status
    fi
}

# Function to generate Prisma client
generate_client() {
    print_status "Generating Prisma client..."
    docker-compose run --rm $MIGRATE_SERVICE python -m prisma generate
    print_status "Prisma client generated successfully"
}

# Function to show database studio (requires additional setup)
db_studio() {
    print_status "Starting Prisma Studio..."
    print_warning "This will start Prisma Studio on port 5555"
    if check_db; then
        docker-compose run --rm -p 5555:5555 $MIGRATE_SERVICE python -m prisma studio
    fi
}

# Main script logic
case "$1" in
    "migrate:deploy")
        migrate_deploy
        ;;
    "migrate:dev")
        migrate_dev "$2"
        ;;
    "migrate:reset")
        migrate_reset
        ;;
    "migrate:status")
        migrate_status
        ;;
    "generate")
        generate_client
        ;;
    "studio")
        db_studio
        ;;
    "help"|"--help"|"-h"|"")
        echo "Event Tracker V2 - Database Migration Tool"
        echo ""
        echo "Usage: $0 <command> [arguments]"
        echo ""
        echo "Commands:"
        echo "  migrate:deploy     Apply pending migrations to the database"
        echo "  migrate:dev <name> Create and apply a new migration"
        echo "  migrate:reset      Reset the database (WARNING: loses all data)"
        echo "  migrate:status     Show current migration status"
        echo "  generate          Generate Prisma client"
        echo "  studio            Start Prisma Studio (database browser)"
        echo "  help              Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0 migrate:deploy"
        echo "  $0 migrate:dev add_user_table"
        echo "  $0 migrate:status"
        echo "  $0 generate"
        ;;
    *)
        print_error "Unknown command: $1"
        echo "Use '$0 help' to see available commands"
        exit 1
        ;;
esac