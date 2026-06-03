#install 
	#python-3.10
	#mongoDB

# Development setup script
# Run this in PowerShell to set up the development environment

Write-Host "Setting up Django Two-Level Authentication System..." -ForegroundColor Green


# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& ".venv\Scripts\Activate.ps1"

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install requirements
Write-Host "Installing requirements..." -ForegroundColor Yellow
pip install -r requirements.txt


# Run migrations
Write-Host "Running database migrations..." -ForegroundColor Yellow
python manage.py makemigrations
python manage.py migrate

# Create superuser
Write-Host "Creating superuser..." -ForegroundColor Yellow
Write-Host "Note: This will create an HR Admin user." -ForegroundColor Cyan
python manage.py createsuperuser