# Schedule Platform Plus - Start Services (PowerShell)

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
    Write-Host "Warning: .env file not found!" -ForegroundColor Yellow
    Write-Host "Creating .env from template..." -ForegroundColor Blue
    
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env file from .env.example" -ForegroundColor Green
        Write-Host "Please edit .env file and set your secret keys!" -ForegroundColor Yellow
        Write-Host ""
    } else {
        Write-Host "Error: .env.example file not found!" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

Write-Host "Starting databases..." -ForegroundColor Yellow
docker-compose up -d postgres redis

Write-Host "Waiting for databases to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

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
Write-Host "Applying database migrations..." -ForegroundColor Yellow

# Apply migrations for each service
Write-Host "Auth Service migrations..." -ForegroundColor Blue
docker-compose run --rm auth-service alembic upgrade head

Write-Host "Profile Service migrations..." -ForegroundColor Blue
docker-compose run --rm profile-service alembic upgrade head

Write-Host "Schedule Service migrations..." -ForegroundColor Blue
docker-compose run --rm schedule-service alembic upgrade head

Write-Host ""
Write-Host "Starting all services..." -ForegroundColor Yellow
docker-compose up -d

Write-Host ""
Write-Host "All services started successfully!" -ForegroundColor Green
Write-Host "=" * 50
Write-Host "Available services:" -ForegroundColor Blue
Write-Host "• Auth Service:     http://localhost:8000/docs" -ForegroundColor White
Write-Host "• Profile Service:  http://localhost:8002/docs" -ForegroundColor White
Write-Host "• Schedule Service: http://localhost:8001/docs" -ForegroundColor White
Write-Host ""
Write-Host "Management tools:" -ForegroundColor Blue
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

Read-Host "`nPress Enter to finish"