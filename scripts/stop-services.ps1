# Schedule Platform Plus - Stop Services (PowerShell)

Write-Host "Stopping Schedule Platform Plus" -ForegroundColor Blue
Write-Host "=" * 50

# Show current container status
Write-Host "Current container status:" -ForegroundColor Yellow
docker-compose ps

Write-Host ""
Write-Host "Stopping all services..." -ForegroundColor Yellow
docker-compose down

Write-Host ""
Write-Host "Cleaning up unused containers..." -ForegroundColor Yellow
docker system prune -f

Write-Host ""
Write-Host "All services stopped successfully!" -ForegroundColor Green

Write-Host ""
Write-Host "Additional commands:" -ForegroundColor Blue
Write-Host "• Full cleanup (including volumes): docker-compose down -v" -ForegroundColor White
Write-Host "• Rebuild on next start: docker-compose build" -ForegroundColor White
Write-Host "• View running containers: docker ps" -ForegroundColor White
Write-Host "• Start again: .\scripts\start-services.ps1" -ForegroundColor White

Write-Host ""
Write-Host "WARNING:" -ForegroundColor Yellow
Write-Host "Command 'docker-compose down -v' will delete ALL database data!" -ForegroundColor Red
Write-Host "Use it only if you want to completely reset the project." -ForegroundColor Red

Read-Host "`nPress Enter to finish"