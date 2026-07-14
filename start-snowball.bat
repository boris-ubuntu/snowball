@echo off
echo Waiting for Docker Desktop to start...
setlocal enabledelayedexpansion

:: Wait for Docker to be ready (up to 60 seconds)
set count=0
:wait_loop
docker info >nul 2>&1
if !errorlevel! equ 0 (
    echo Docker is ready!
    goto start_containers
)
set /a count+=1
if !count! geq 60 (
    echo Timeout waiting for Docker. Please start Docker Desktop manually.
    exit /b 1
)
timeout /t 2 /nobreak >nul
goto wait_loop

:start_containers
echo Starting snowball containers...
cd /d "%~dp0"
docker-compose up -d
if !errorlevel! equ 0 (
    echo Snowball started successfully!
    echo Open http://localhost:8000 in your browser.
) else (
    echo Failed to start snowball containers.
    exit /b 1
)