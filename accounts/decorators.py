from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from functools import wraps


def hr_admin_required(view_func):
    """Decorator to ensure user is HR admin"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Redirect to login page
            from django.contrib.auth.decorators import login_required
            return login_required(view_func)(request, *args, **kwargs)
        
        if not request.user.is_hr_admin():
            raise PermissionDenied("You must be an HR admin to access this page.")
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def employee_required(view_func):
    """Decorator to ensure user is an employee"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.decorators import login_required
            return login_required(view_func)(request, *args, **kwargs)
        
        if not request.user.is_employee():
            raise PermissionDenied("You must be an employee to access this page.")
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def approved_user_required(view_func):
    """Decorator to ensure user is approved"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.decorators import login_required
            return login_required(view_func)(request, *args, **kwargs)
        
        if not request.user.is_approved:
            raise PermissionDenied("Your account is pending approval.")
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view