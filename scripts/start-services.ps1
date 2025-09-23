# Schedule Platform Plus - Start Services (PowerShell) - ИСПРАВЛЕННАЯ ВЕРСИЯ

Write-Host "Starting Schedule Platform Plus" -ForegroundColor Blue
Write-Host "=" * 50

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Host "Docker Desktop is running" -ForegroundColor Green
} catch {
    Write-Host "Docker is not running or unavailable!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if .env file exists
if (-not (Test-Path ".env")) {
    Write-Host "Error: .env file not found!" -ForegroundColor Red
    Write-Host "Creating .env from template..." -ForegroundColor Blue
    
    if (Test-Path ".env.example") {
        Write-Host "ВНИМАНИЕ: Нужно создать .env файл с правильными значениями!" -ForegroundColor Yellow
        Write-Host "Используйте исправленный .env файл из артефактов Claude." -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
        exit 1
    } else {
        Write-Host "Error: .env.example file not found!" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

Write-Host "Found .env file" -ForegroundColor Green

# Stop any existing containers first
Write-Host "Stopping any existing containers..." -ForegroundColor Yellow
docker-compose down

Write-Host "Starting databases..." -ForegroundColor Yellow
docker-compose up -d postgres redis

Write-Host "Waiting for databases to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 20

# Check PostgreSQL readiness
$maxAttempts = 30
$attempt = 0
$postgresReady = $false

do {
    $attempt++
    Write-Host "Checking PostgreSQL (attempt $attempt/$maxAttempts)..." -ForegroundColor Yellow
    
    try {
        $null = docker-compose exec -T postgres pg_isready -U postgres 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "PostgreSQL is ready!" -ForegroundColor Green
            $postgresReady = $true
            break
        }
    } catch {
        # Continue checking
    }
    
    Start-Sleep -Seconds 2
} while ($attempt -lt $maxAttempts)

if (-not $postgresReady) {
    Write-Host "PostgreSQL failed to start within timeout!" -ForegroundColor Red
    Write-Host "Check logs with: docker-compose logs postgres" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check Redis readiness
$attempt = 0
$redisReady = $false

do {
    $attempt++
    Write-Host "Checking Redis (attempt $attempt/10)..." -ForegroundColor Yellow
    
    try {
        $result = docker-compose exec -T redis redis-cli ping 2>$null
        if ($result -match "PONG") {
            Write-Host "Redis is ready!" -ForegroundColor Green
            $redisReady = $true
            break
        }
    } catch {
        # Continue checking
    }
    
    Start-Sleep -Seconds 2
} while ($attempt -lt 10)

if (-not $redisReady) {
    Write-Host "Warning: Redis may not be ready, but continuing..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Building and starting microservices..." -ForegroundColor Yellow

# Build and start auth service first
Write-Host "Building Auth Service..." -ForegroundColor Blue
docker-compose build auth-service
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to build Auth Service!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Starting Auth Service..." -ForegroundColor Blue
docker-compose up -d auth-service

# Wait for auth service
Write-Host "Waiting for Auth Service to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# Build and start profile service
Write-Host "Building Profile Service..." -ForegroundColor Blue
docker-compose build profile-service
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to build Profile Service!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Starting Profile Service..." -ForegroundColor Blue
docker-compose up -d profile-service

# Wait for profile service
Write-Host "Waiting for Profile Service to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# Build and start schedule service
Write-Host "Building Schedule Service..." -ForegroundColor Blue
docker-compose build schedule-service
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to build Schedule Service!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Starting Schedule Service..." -ForegroundColor Blue
docker-compose up -d schedule-service

Write-Host ""
Write-Host "Applying database migrations..." -ForegroundColor Yellow

# Apply migrations for each service (ТОЛЬКО если контейнеры запущены)
Write-Host "Auth Service migrations..." -ForegroundColor Blue
$authRunning = docker-compose ps -q auth-service
if ($authRunning) {
    docker-compose exec auth-service alembic upgrade head
} else {
    Write-Host "Warning: Auth Service не запущен, пропускаем миграции" -ForegroundColor Yellow
}

Write-Host "Profile Service migrations..." -ForegroundColor Blue
$profileRunning = docker-compose ps -q profile-service
if ($profileRunning) {
    docker-compose exec profile-service alembic upgrade head
} else {
    Write-Host "Warning: Profile Service не запущен, пропускаем миграции" -ForegroundColor Yellow
}

Write-Host "Schedule Service migrations..." -ForegroundColor Blue
$scheduleRunning = docker-compose ps -q schedule-service
if ($scheduleRunning) {
    docker-compose exec schedule-service alembic upgrade head
} else {
    Write-Host "Warning: Schedule Service не запущен, пропускаем миграции" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "All services started successfully!" -ForegroundColor Green
Write-Host "=" * 50
Write-Host "Available services:" -ForegroundColor Blue
Write-Host "• Auth Service:     http://localhost:8000/docs" -ForegroundColor White
Write-Host "• Profile Service:  http://localhost:8002/docs" -ForegroundColor White
Write-Host "• Schedule Service: http://localhost:8001/docs" -ForegroundColor White
Write-Host ""
Write-Host "Management tools (добавьте --profile tools к docker-compose):" -ForegroundColor Blue
Write-Host "• PgAdmin:          http://localhost:5050" -ForegroundColor White
Write-Host "• Redis Commander:  http://localhost:8081" -ForegroundColor White
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Yellow
Write-Host "• View logs:        docker-compose logs -f" -ForegroundColor White
Write-Host "• Check status:     docker-compose ps" -ForegroundColor White
Write-Host "• Stop services:    docker-compose down" -ForegroundColor White
Write-Host "• Or use:           .\scripts\stop-services.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Ready for development!" -ForegroundColor Green

# Show container status
Write-Host ""
Write-Host "Container status:" -ForegroundColor Blue
docker-compose ps

# Check if services are responding
Write-Host ""
Write-Host "Testing service endpoints..." -ForegroundColor Blue
try {
    $authResponse = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -UseBasicParsing
    Write-Host "✅ Auth Service: $($authResponse.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "❌ Auth Service: Not responding" -ForegroundColor Red
}

try {
    $profileResponse = Invoke-WebRequest -Uri "http://localhost:8002/health" -TimeoutSec 5 -UseBasicParsing
    Write-Host "✅ Profile Service: $($profileResponse.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "❌ Profile Service: Not responding" -ForegroundColor Red
}

try {
    $scheduleResponse = Invoke-WebRequest -Uri "http://localhost:8001/health" -TimeoutSec 5 -UseBasicParsing
    Write-Host "✅ Schedule Service: $($scheduleResponse.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "❌ Schedule Service: Not responding" -ForegroundColor Red
}

Read-Host "`nPress Enter to finish"