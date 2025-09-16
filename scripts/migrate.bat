@echo off
REM Database Migration Script for Event Tracker V2 (Windows)
REM This script provides various database migration commands

setlocal enabledelayedexpansion

REM Configuration
set DB_SERVICE=db
set MIGRATE_SERVICE=migrate
set COMPOSE_FILE=docker-compose.yml

REM Helper function to print status
:print_status
echo [INFO] %~1
goto :eof

:print_warning
echo [WARN] %~1
goto :eof

:print_error
echo [ERROR] %~1
goto :eof

REM Function to check if database is running
:check_db
call :print_status "Checking database status..."
docker-compose ps %DB_SERVICE% | findstr "Up" >nul
if !errorlevel! equ 0 (
    call :print_status "Database is running"
    exit /b 0
) else (
    call :print_error "Database is not running. Please start it first with: docker-compose up db -d"
    exit /b 1
)

REM Function to run migrations
:migrate_deploy
call :print_status "Running database migrations..."
call :check_db
if !errorlevel! equ 0 (
    docker-compose run --rm %MIGRATE_SERVICE% python -m prisma migrate deploy
    call :print_status "Migrations completed successfully"
)
goto :eof

REM Function to create a new migration
:migrate_dev
if "%~2"=="" (
    call :print_error "Migration name is required"
    echo Usage: %0 migrate:dev ^<migration_name^>
    exit /b 1
)

call :print_status "Creating new migration: %~2"
call :check_db
if !errorlevel! equ 0 (
    docker-compose run --rm %MIGRATE_SERVICE% python -m prisma migrate dev --name "%~2"
    call :print_status "Migration '%~2' created successfully"
)
goto :eof

REM Function to reset database
:migrate_reset
call :print_warning "This will reset the database and lose all data!"
set /p "confirm=Are you sure? (y/N): "
if /i "!confirm!"=="y" (
    call :print_status "Resetting database..."
    call :check_db
    if !errorlevel! equ 0 (
        docker-compose run --rm %MIGRATE_SERVICE% python -m prisma migrate reset --force
        call :print_status "Database reset completed"
    )
) else (
    call :print_status "Database reset cancelled"
)
goto :eof

REM Function to show migration status
:migrate_status
call :print_status "Checking migration status..."
call :check_db
if !errorlevel! equ 0 (
    docker-compose run --rm %MIGRATE_SERVICE% python -m prisma migrate status
)
goto :eof

REM Function to generate Prisma client
:generate_client
call :print_status "Generating Prisma client..."
docker-compose run --rm %MIGRATE_SERVICE% python -m prisma generate
call :print_status "Prisma client generated successfully"
goto :eof

REM Function to show database studio
:db_studio
call :print_status "Starting Prisma Studio..."
call :print_warning "This will start Prisma Studio on port 5555"
call :check_db
if !errorlevel! equ 0 (
    docker-compose run --rm -p 5555:5555 %MIGRATE_SERVICE% python -m prisma studio
)
goto :eof

REM Function to show help
:show_help
echo Event Tracker V2 - Database Migration Tool
echo.
echo Usage: %0 ^<command^> [arguments]
echo.
echo Commands:
echo   migrate:deploy     Apply pending migrations to the database
echo   migrate:dev ^<name^> Create and apply a new migration
echo   migrate:reset      Reset the database (WARNING: loses all data)
echo   migrate:status     Show current migration status
echo   generate          Generate Prisma client
echo   studio            Start Prisma Studio (database browser)
echo   help              Show this help message
echo.
echo Examples:
echo   %0 migrate:deploy
echo   %0 migrate:dev add_user_table
echo   %0 migrate:status
echo   %0 generate
goto :eof

REM Main script logic
if "%1"=="migrate:deploy" (
    call :migrate_deploy
) else if "%1"=="migrate:dev" (
    call :migrate_dev %1 %2
) else if "%1"=="migrate:reset" (
    call :migrate_reset
) else if "%1"=="migrate:status" (
    call :migrate_status
) else if "%1"=="generate" (
    call :generate_client
) else if "%1"=="studio" (
    call :db_studio
) else if "%1"=="help" (
    call :show_help
) else if "%1"=="--help" (
    call :show_help
) else if "%1"=="-h" (
    call :show_help
) else if "%1"=="" (
    call :show_help
) else (
    call :print_error "Unknown command: %1"
    echo Use '%0 help' to see available commands
    exit /b 1
)