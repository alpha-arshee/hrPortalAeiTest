# Development setup script
# Run this in PowerShell to set up the development environment

Write-Host "Setting up Django Two-Level Authentication System..." -ForegroundColor Green

# Create virtual environment
Write-Host "Creating virtual environment..." -ForegroundColor Yellow
python -m venv .venv

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& ".venv\Scripts\Activate.ps1"

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install requirements
Write-Host "Installing requirements..." -ForegroundColor Yellow
pip install -r requirements.txt

# Copy environment file
Write-Host "Setting up environment file..." -ForegroundColor Yellow
if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env file from template. Please update with your settings." -ForegroundColor Yellow
}

# Run migrations
Write-Host "Running database migrations..." -ForegroundColor Yellow
python manage.py makemigrations
python manage.py migrate

# Create superuser
Write-Host "Creating superuser..." -ForegroundColor Yellow
Write-Host "Note: This will create an HR Admin user." -ForegroundColor Cyan
python manage.py createsuperuser

Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "Run 'python manage.py runserver' to start the development server." -ForegroundColor Cyan