#!/usr/bin/env python
import os
import sys
import django

# Set up Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aei_hr.settings')
django.setup()

from accounts.models import LoginAttempt, User
from django.utils import timezone
from datetime import timedelta

def check_login_data():
    print("=== Checking Login Attempt Data ===")
    
    # Check total login attempts
    total_attempts = LoginAttempt.objects.count()
    print(f"Total login attempts: {total_attempts}")
    
    if total_attempts > 0:
        # Show all login attempts
        attempts = list(LoginAttempt.objects.all())
        print("\nAll login attempts:")
        for attempt in attempts:
            print(f"  {attempt.username} - {attempt.timestamp} - Success: {attempt.success}")
        
        # Check recent successful logins (last 30 days) - using manual filtering
        cutoff_date = timezone.now() - timedelta(days=30)
        
        # Get all login attempts and filter manually (djongo compatible)
        all_attempts = list(LoginAttempt.objects.all())
        recent_successful_logins = []
        
        for attempt in all_attempts:
            if attempt.success and attempt.timestamp >= cutoff_date:
                recent_successful_logins.append(attempt)
        
        recent_successful_logins.sort(key=lambda x: x.timestamp, reverse=True)
        
        print(f"\nRecent successful logins (last 30 days): {len(recent_successful_logins)}")
        
        for login in recent_successful_logins[:5]:
            print(f"  {login.username} - {login.timestamp}")
    else:
        print("No login attempts found in database!")
        print("This means the login tracking is not working properly.")
    
    # Check users
    users = User.objects.all()
    print(f"\nTotal users: {users.count()}")
    for user in users:
        print(f"  {user.username} - Last login: {user.last_login}")

if __name__ == "__main__":
    check_login_data()