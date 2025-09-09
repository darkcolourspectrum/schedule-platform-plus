# Profile Service - Create missing files
# Execute from services/profile_service/ directory

Write-Host "Creating missing files for Profile Service..." -ForegroundColor Cyan

# Create remaining API files
New-Item -ItemType File -Path "app/api/v1/dashboard.py" -Force
New-Item -ItemType File -Path "app/api/v1/avatars.py" -Force

# Create core files
New-Item -ItemType File -Path "app/core/__init__.py" -Force
New-Item -ItemType File -Path "app/core/exceptions.py" -Force
New-Item -ItemType File -Path "app/core/middleware.py" -Force
New-Item -ItemType File -Path "app/core/auth.py" -Force

# Create database files  
New-Item -ItemType File -Path "app/database/__init__.py" -Force

# Create repositories files
New-Item -ItemType File -Path "app/repositories/__init__.py" -Force
New-Item -ItemType File -Path "app/repositories/base.py" -Force
New-Item -ItemType File -Path "app/repositories/profile_repository.py" -Force
New-Item -ItemType File -Path "app/repositories/comment_repository.py" -Force
New-Item -ItemType File -Path "app/repositories/activity_repository.py" -Force

# Create services files
New-Item -ItemType File -Path "app/services/__init__.py" -Force
New-Item -ItemType File -Path "app/services/auth_client.py" -Force
New-Item -ItemType File -Path "app/services/schedule_client.py" -Force
New-Item -ItemType File -Path "app/services/profile_service.py" -Force
New-Item -ItemType File -Path "app/services/dashboard_service.py" -Force
New-Item -ItemType File -Path "app/services/comment_service.py" -Force
New-Item -ItemType File -Path "app/services/cache_service.py" -Force
New-Item -ItemType File -Path "app/services/avatar_service.py" -Force

# Create schemas files
New-Item -ItemType File -Path "app/schemas/__init__.py" -Force
New-Item -ItemType File -Path "app/schemas/profile.py" -Force
New-Item -ItemType File -Path "app/schemas/comment.py" -Force
New-Item -ItemType File -Path "app/schemas/dashboard.py" -Force
New-Item -ItemType File -Path "app/schemas/common.py" -Force

# Create utils files
New-Item -ItemType File -Path "app/utils/__init__.py" -Force
New-Item -ItemType File -Path "app/utils/image_processing.py" -Force
New-Item -ItemType File -Path "app/utils/cache_keys.py" -Force

# Create init files for remaining directories
New-Item -ItemType File -Path "app/api/__init__.py" -Force
New-Item -ItemType File -Path "app/api/v1/__init__.py" -Force

Write-Host "All files created successfully!" -ForegroundColor Green
Write-Host "Next step: configure database connection" -ForegroundColor Yellow