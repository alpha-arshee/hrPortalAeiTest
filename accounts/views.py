from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.core.paginator import Paginator
import threading
from django.core.management import call_command
from django.conf import settings
import logging
from django.utils import timezone
from datetime import timedelta, date
import json
import calendar
from payroll.models import EmployeePayrollDetails
from attendance.models import LeaveQuota
from .models import BankingInfo, TaxInfo, User, EmployeeProfile, LoginAttempt, commonInfo
from .forms import (
    UserRegistrationForm, UserLoginForm, ProfileUpdateForm,
    HRUserManagementForm, DepartmentSettingsForm
)
from .decorators import hr_admin_required
from django.core.files.storage import default_storage
from decimal import Decimal

logger = logging.getLogger(__name__)


def home(request):
    """Home page view"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    return render(request, 'accounts/home.html')


def register(request):
    """User registration view"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST, request.FILES)
        # Pre-validate uniqueness using pymongo to avoid djongo/sqlparse recursion
        try:
            from pymongo import MongoClient
            client_uri = settings.DATABASES['default']['CLIENT'].get('host')
            db_name = settings.DATABASES['default']['NAME']
            if client_uri and db_name:
                try:
                    client = MongoClient(client_uri)
                    db = client[db_name]
                    users_coll = db.get_collection('accounts_user')

                    username_val = (request.POST.get('username') or '').strip()
                    email_val = (request.POST.get('email') or '').strip()
                    employee_id_val = (request.POST.get('employee_id') or '').strip()

                    if username_val and users_coll.find_one({'username': username_val}):
                        form.add_error('username', 'Username already exists')
                        messages.error(request, 'Username already exists')
                    if email_val and users_coll.find_one({'email': email_val}):
                        form.add_error('email', 'Email already exists')
                        messages.error(request, 'Email already exists')
                    if employee_id_val and users_coll.find_one({'employee_id': employee_id_val}):
                        form.add_error('employee_id', 'Employee ID already exists')
                        messages.error(request, 'Employee ID already exists')
                except Exception:
                    # If pymongo checks fail, log and continue to let Django handle validations
                    logger.exception('pymongo pre-check for registration failed')
        except Exception:
            # pymongo not available or other import issues — skip pre-check
            logger.debug('pymongo not available for pre-check; skipping')

        # If pre-check added form errors, skip Django's validate_unique which triggers djongo SQL parsing
        if form.errors:
            return render(request, 'accounts/register.html', {'form': form})

        if form.is_valid():
            try:
                # Save user with transaction-like approach for djongo
                user = form.save(commit=False)
                user.is_approved = False  # Requires HR approval
                user.role = 'employee'  # Set default role
                
                # Try to save the user
                user.save()
                
                # Create employee profile
                try:
                    # Populate permanent_address on profile if provided in the registration form
                    perm_addr = form.cleaned_data.get('permanent_address') if hasattr(form, 'cleaned_data') else None
                    if perm_addr:
                        EmployeeProfile.objects.create(user=user, permanent_address=perm_addr)
                    else:
                        EmployeeProfile.objects.create(user=user)
                except Exception as profile_error:
                    # If profile creation fails, log but don't fail registration
                    pass
                
                messages.success(request, 'Registration successful! Please wait for HR approval.')
                return redirect('accounts:login')
                
            except Exception as e:
                # Handle database errors gracefully
                error_message = str(e).lower()
                if 'duplicate' in error_message or 'unique' in error_message:
                    if 'email' in error_message:
                        form.add_error('email', 'A user with this email already exists.')
                    elif 'employee_id' in error_message:
                        form.add_error('employee_id', 'A user with this employee ID already exists.')
                    elif 'username' in error_message:
                        form.add_error('username', 'A user with this username already exists.')
                    else:
                        messages.error(request, 'A user with this information already exists.')
                else:
                    messages.error(request, 'Registration failed. User exists')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'accounts/register.html', {'form': form})


# def user_login(request):
#     """User login view with attempt tracking"""
#     if request.user.is_authenticated:
#         return redirect('accounts:dashboard')
    
#     if request.method == 'POST':
#         form = UserLoginForm(request.POST)
#         if form.is_valid():
#             username = form.cleaned_data['username']
#             password = form.cleaned_data['password']
            
#             # Get client IP
#             ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
#             if ip_address:
#                 ip_address = ip_address.split(',')[0]
#             else:
#                 ip_address = request.META.get('REMOTE_ADDR')
            
#             user = authenticate(request, username=username, password=password)
            
#             # Log login attempt
#             LoginAttempt.objects.create(
#                 username=username,
#                 ip_address=ip_address,
#                 success=user is not None,
#                 user_agent=request.META.get('HTTP_USER_AGENT', '')
#             )
            
#             if user is not None:
#                 if user.is_approved:
#                     login(request, user)
#                     messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')

#                     # Optionally run biometric fetch in background after successful login
#                     try:
#                         if getattr(settings, 'RUN_BIOMETRIC_ON_LOGIN', False):
#                             def _run_fetch():
#                                 try:
#                                     call_command('fetch_biometric_data')
#                                 except Exception:
#                                     logger.exception('fetch_biometric_data failed during login-trigger')
#                             threading.Thread(target=_run_fetch, daemon=True).start()
#                     except Exception:
#                         logger.exception('Failed to start biometric fetch thread on login')

#                     return redirect('accounts:dashboard')
#                 else:
#                     messages.error(request, 'Your account is pending approval from HR.')
#             else:
#                 messages.error(request, 'Invalid username or password.')
#     else:
#         form = UserLoginForm()
    
#     return render(request, 'accounts/login.html', {'form': form})


def user_login(request):
    """User login view with attempt tracking"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    
    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            
            # Get client IP
            ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
            if ip_address:
                ip_address = ip_address.split(',')[0]
            else:
                ip_address = request.META.get('REMOTE_ADDR')
            
            user = authenticate(request, username=username, password=password)
            
            # Log login attempt
            LoginAttempt.objects.create(
                username=username,
                ip_address=ip_address,
                success=user is not None,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            if user is not None:
                if user.is_approved:
                    login(request, user)
                    messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
                    return redirect('accounts:dashboard')
                else:
                    messages.error(request, 'Your account is pending approval from HR.')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = UserLoginForm()
    
    return render(request, 'accounts/login.html', {'form': form})


@login_required
def user_logout(request):
    """User logout view"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('accounts:login')


@login_required
def dashboard(request):
    """Role-based dashboard"""
    context = {
        'user': request.user,
    }
    
    if request.user.is_hr_admin():
        # HR Admin Dashboard - Use safer queries
        try:
            # Count employees and HR admins safely (exclude other system/service accounts)
            all_employees = list(User.objects.filter(role__in=['employee', 'hr_admin']))
            # current_employees should reflect only active accounts
            current_employees = len([emp for emp in all_employees if getattr(emp, 'is_active', False)])
            
            # Count pending approvals
            pending_employees = [emp for emp in all_employees if not emp.is_approved]
            pending_approvals = len(pending_employees)
            hr_admins = [emp for emp in all_employees if emp.role == 'hr_admin']
            hr_admin_count = len(hr_admins)
            employee_count = len([emp for emp in all_employees if emp.role == 'employee'])
            # Get recent registrations and total count for the last 7 days
            recent_registrations_full = []
            cutoff_date = timezone.now() - timedelta(days=7)
            for emp in all_employees:
                try:
                    created = emp.created_at
                except Exception:
                    created = None
                if created and created >= cutoff_date:
                    recent_registrations_full.append(emp)

            # total number of new registrations in the last week
            total_new_this_week = len(recent_registrations_full)

            # Sort and slice for the recent registrations table (limit to 5)
            recent_registrations_full.sort(key=lambda x: x.created_at, reverse=True)
            recent_registrations = recent_registrations_full[:5]

            # Upcoming birthdays within the next 10 days (employees + HR)
            upcoming_birthdays = []
            try:
                today = timezone.localdate()
            except Exception:
                today = timezone.now().date()

            for emp in all_employees:
                try:
                    profile = emp.employeeprofile
                    bday = getattr(profile, 'dob', None)
                except Exception:
                    bday = None
                if not bday:
                    continue
                try:
                    # Build next occurrence of birthday based on month/day only (ignore birth year)
                    # Handle Feb 29 on non-leap years by falling back to Feb 28 for that year
                    try:
                        next_bday = date(today.year, bday.month, bday.day)
                    except ValueError:
                        # likely Feb 29 on non-leap year
                        if bday.month == 2 and bday.day == 29:
                            next_bday = date(today.year, 2, 28)
                        else:
                            raise
                except Exception:
                    continue
                if next_bday < today:
                    try:
                        try:
                            next_bday = date(today.year + 1, bday.month, bday.day)
                        except ValueError:
                            # handle Feb 29 -> Feb 28 on non-leap next year
                            if bday.month == 2 and bday.day == 29:
                                next_bday = date(today.year + 1, 2, 28)
                            else:
                                raise
                    except Exception:
                        continue
                days_until = (next_bday - today).days
                if 0 <= days_until <= 30:
                    upcoming_birthdays.append({
                        'name': emp.get_full_name() or emp.username,
                        'department': emp.department or '',
                        'employee_id': emp.employee_id or '',
                        'role': emp.get_role_display(),
                        'date': next_bday,
                        'days_until': days_until,
                    })

            # sort by soonest
            upcoming_birthdays.sort(key=lambda x: x['days_until'])
            upcoming_birthdays = upcoming_birthdays[:10]
            # today's birthdays (days_until == 0)
            todays_birthdays = [b for b in upcoming_birthdays if b.get('days_until') == 0]

            context.update({
                'current_employees': current_employees,
                'hr_admins_len': hr_admin_count,
                'employee_count': employee_count,
                'pending_approvals': pending_approvals,
                'recent_registrations': recent_registrations,
                'total_new_this_week': total_new_this_week,
                'upcoming_birthdays': upcoming_birthdays,
                'todays_birthdays': todays_birthdays,
                # Provide recent attendance logs for HR dashboard (best-effort)
                'recent_attendance_logs': [],
                # pending leave requests (attendance.Leave with status 'pending')
                'pending_leave_requests': [],
                'pending_leave_count': 0,
            })
            try:
                from attendance.models import BiometricLog
                try:
                    # Order by most recent punch_date then by id as fallback
                    recent_attendance_qs = BiometricLog.objects.order_by('-punch_date', '-id')[:10]
                    recent_attendance_logs = list(recent_attendance_qs)
                except Exception:
                    recent_attendance_logs = []
                context['recent_attendance_logs'] = recent_attendance_logs
            except Exception:
                # ignore if attendance app/models not available
                context['recent_attendance_logs'] = []
            # Additional quick KPIs
            try:
                total_employees = len(all_employees)
            except Exception:
                total_employees = 0

            try:
                try:
                    today = timezone.localdate()
                except Exception:
                    today = timezone.now().date()

                # Total attendance today (count biometric logs with punch_date == today)
                attendance_today = 0
                try:
                    from attendance.models import BiometricLog
                    for log in BiometricLog.objects.all():
                        try:
                            pd = getattr(log, 'punch_date', None)
                            if not pd:
                                continue
                            pd_date = pd.date() if hasattr(pd, 'date') else pd
                            if pd_date == today:
                                attendance_today += 1
                        except Exception:
                            continue
                except Exception:
                    attendance_today = 0

                # Employees on leave today
                employees_on_leave_today = 0
                try:
                    from attendance.models import Leave
                    seen = set()
                    for lv in Leave.objects.all():
                        try:
                            sd = getattr(lv, 'start_date', None)
                            ed = getattr(lv, 'end_date', None)
                            if not sd or not ed:
                                continue
                            sd_date = sd.date() if hasattr(sd, 'date') else sd
                            ed_date = ed.date() if hasattr(ed, 'date') else ed
                            if sd_date <= today <= ed_date:
                                uid = getattr(lv.user, 'id', None) if getattr(lv, 'user', None) else getattr(lv, 'user_id', None)
                                if uid and uid not in seen:
                                    seen.add(uid)
                                    employees_on_leave_today += 1
                        except Exception:
                            continue
                except Exception:
                    employees_on_leave_today = 0

                # New joinees this month
                new_joinees_month = 0
                try:
                    for emp in all_employees:
                        try:
                            created = getattr(emp, 'created_at', None)
                            if not created:
                                continue
                            created_date = created.date() if hasattr(created, 'date') else created
                            if created_date.year == today.year and created_date.month == today.month:
                                new_joinees_month += 1
                        except Exception:
                            continue
                except Exception:
                    new_joinees_month = 0
            except Exception:
                attendance_today = 0
                employees_on_leave_today = 0
                new_joinees_month = 0
                total_employees = total_employees if 'total_employees' in locals() else 0
            # Fetch pending leave requests (status == 'pending') for HR review
            try:
                from attendance.models import Leave
                try:
                    pending_qs = Leave.objects.filter(status__iexact='pending').order_by('-start_date')[:10]
                    pending_leave_requests = list(pending_qs)
                    pending_leave_count = pending_qs.count() if hasattr(pending_qs, 'count') else len(pending_leave_requests)
                except Exception:
                    pending_leave_requests = []
                    pending_leave_count = 0
                context['pending_leave_requests'] = pending_leave_requests
                context['pending_leave_count'] = pending_leave_count
            except Exception:
                context['pending_leave_requests'] = []
                context['pending_leave_count'] = 0
            # Inject quick KPI values into context for template
            try:
                context['total_employees'] = total_employees
            except Exception:
                context['total_employees'] = len(all_employees) if 'all_employees' in locals() else 0

            context['attendance_today'] = attendance_today if 'attendance_today' in locals() else 0
            context['employees_on_leave_today'] = employees_on_leave_today if 'employees_on_leave_today' in locals() else 0
            context['new_joinees_month'] = new_joinees_month if 'new_joinees_month' in locals() else 0
            # pending_approvals and upcoming_birthdays already in context
            return render(request, 'accounts/hr_dashboard.html', context)
            
        except Exception as e:
            # Fallback with minimal data
            messages.warning(request, 'Some dashboard data may not be available.')
            context.update({
                'current_employees': 0,
                'pending_approvals': 0,
                'recent_registrations': [],
            })
            return render(request, 'accounts/hr_dashboard.html', context)
    else:
        # Employee Dashboard
        try:
            profile = request.user.employeeprofile
        except EmployeeProfile.DoesNotExist:
            profile = EmployeeProfile.objects.create(user=request.user)
        except Exception:
            # Create a basic profile if there's any issue
            profile = None

        # Normalize CTC for template rendering: convert bson Decimal128 to Decimal
        try:
            if profile is not None:
                try:
                    from bson.decimal128 import Decimal128 as BsonDecimal128
                except Exception:
                    BsonDecimal128 = None
                if BsonDecimal128 and isinstance(getattr(profile, 'ctc', None), BsonDecimal128):
                    try:
                        profile.ctc = profile.ctc.to_decimal()
                    except Exception:
                        # fallback: convert to string then Decimal
                        try:
                            profile.ctc = Decimal(str(profile.ctc))
                        except Exception:
                            profile.ctc = None
        except Exception:
            # Defensive: do not break dashboard rendering
            pass
        
        # Get recent logins safely - use manual filtering for djongo compatibility
        try:
            recent_logins = []
            all_login_attempts = list(LoginAttempt.objects.all())
            
            # Filter manually for the current user's successful logins
            user_successful_logins = []
            for login in all_login_attempts:
                if login.username == request.user.username and login.success:
                    user_successful_logins.append(login)
            
            # Sort by timestamp (most recent first) and limit to 5
            user_successful_logins.sort(key=lambda x: x.timestamp, reverse=True)
            recent_logins = user_successful_logins[:5]
            
        except Exception:
            recent_logins = []
        
        context.update({
            'profile': profile,
            'recent_logins': recent_logins,
        })
        # Also provide tax_info to the employee dashboard for PF display
        try:
            tax_info = request.user.taxinfo
        except TaxInfo.DoesNotExist:
            try:
                tax_info = TaxInfo.objects.create(user=request.user)
            except Exception:
                tax_info = None
        except Exception:
            tax_info = None

        context.update({'tax_info': tax_info})
        return render(request, 'accounts/employee_dashboard.html', context)


@login_required
def profile(request):
    """User profile view and update"""
    try:
        employee_profile = request.user.employeeprofile
    except EmployeeProfile.DoesNotExist:
        employee_profile = EmployeeProfile.objects.create(user=request.user)
    
    if request.method == 'POST':
        # Capture previous profile picture name so we can delete it after a successful update
        previous_picture = None
        try:
            previous_picture = request.user.profile_picture.name if getattr(request.user, 'profile_picture', None) else None
        except Exception:
            previous_picture = None

        form = ProfileUpdateForm(request.POST, request.FILES,
                                 instance=request.user,
                                 employee_profile=employee_profile)
        if form.is_valid():
            form.save()

            # If a new picture was uploaded and it's different from the previous one,
            # remove the previous file from storage to avoid orphaned files.
            try:
                new_picture = request.user.profile_picture.name if getattr(request.user, 'profile_picture', None) else None
                if previous_picture and new_picture and previous_picture != new_picture:
                    # Use default_storage to delete the file (works with local or remote storage backends)
                    try:
                        default_storage.delete(previous_picture)
                    except Exception:
                        # best-effort: ignore deletion errors
                        pass
            except Exception:
                pass

            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile')
    else:
        form = ProfileUpdateForm(instance=request.user, employee_profile=employee_profile)
    
    return render(request, 'accounts/profile.html', {
        'form': form,
        'profile': employee_profile
    })


@login_required
@hr_admin_required
def employee_management(request):
    """HR Admin: Manage employees"""
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', 'all')
    role_filter = request.GET.get('role', 'all')
    
    try:
        # Get all employees safely
        all_employees = list(User.objects.all())
        
        # Apply search filter
        if search_query:
            filtered_employees = []
            search_lower = search_query.lower()
            for emp in all_employees:
                if (search_lower in (emp.username or '').lower() or
                    search_lower in (emp.first_name or '').lower() or
                    search_lower in (emp.last_name or '').lower() or
                    search_lower in (emp.email or '').lower() or
                    search_lower in (emp.employee_id or '').lower()):
                    filtered_employees.append(emp)
            all_employees = filtered_employees
        
        # Apply role filter
        if role_filter == 'employee':
            all_employees = [emp for emp in all_employees if emp.role == 'employee']
        elif role_filter == 'hr_admin':
            all_employees = [emp for emp in all_employees if emp.role == 'hr_admin']
        
        # Apply status filter
        if status_filter == 'approved':
            all_employees = [emp for emp in all_employees if emp.is_approved]
        elif status_filter == 'pending':
            all_employees = [emp for emp in all_employees if not emp.is_approved]
        
        # Sort by creation date (newest first)
        all_employees.sort(key=lambda x: x.created_at, reverse=True)
        
        # Simple pagination - show first 10
        employees_per_page = 10
        page_number = int(request.GET.get('page', 1))
        start_index = (page_number - 1) * employees_per_page
        end_index = start_index + employees_per_page
        
        employees_page = all_employees[start_index:end_index]
        
        # Create a simple page object
        class SimplePage:
            def __init__(self, items, page_num, per_page, total_count):
                self.object_list = items
                self.number = page_num
                self.has_previous = page_num > 1
                self.has_next = end_index < total_count
                self.previous_page_number = page_num - 1 if self.has_previous else None
                self.next_page_number = page_num + 1 if self.has_next else None
                
                class Paginator:
                    def __init__(self, count):
                        self.count = count
                        self.num_pages = (count + per_page - 1) // per_page
                
                self.paginator = Paginator(total_count)
            
            def __iter__(self):
                """Make the page object iterable"""
                return iter(self.object_list)
                
            def has_other_pages(self):
                """Check if there are other pages"""
                return self.paginator.num_pages > 1
        
        page_obj = SimplePage(employees_page, page_number, employees_per_page, len(all_employees))
        
    except Exception as e:
        # Fallback to empty results
        class EmptyPage:
            object_list = []
            number = 1
            has_previous = False
            has_next = False
            previous_page_number = None
            next_page_number = None
            
            class Paginator:
                count = 0
                num_pages = 0
            
            paginator = Paginator()
            
            def __iter__(self):
                """Make the empty page object iterable"""
                return iter(self.object_list)
                
            def has_other_pages(self):
                """Check if there are other pages"""
                return False
        
        page_obj = EmptyPage()
        messages.warning(request, 'Unable to load employee data. Please try again.')
    
    return render(request, 'accounts/employee_management.html', {
        'page_obj': page_obj,
        'employees': page_obj.object_list,  # Also pass the employees directly
        'search_query': search_query,
        'status_filter': status_filter,
        'role_filter': role_filter,
    })


@login_required
@hr_admin_required
def department_settings(request):
    """HR Admin: manage the shared department list used across dropdowns."""
    try:
        common_info = commonInfo.objects.first()
        if common_info is None:
            common_info = commonInfo.objects.create()
    except Exception:
        common_info = commonInfo()

    if request.method == 'POST':
        form = DepartmentSettingsForm(request.POST, instance=common_info)
        if form.is_valid():
            form.save()
            messages.success(request, 'Department list updated successfully!')
            return redirect('accounts:department_settings')
    else:
        form = DepartmentSettingsForm(instance=common_info)

    department_choices = commonInfo.get_department_choices()
    department_list = [choice[0] for choice in department_choices]

    return render(request, 'accounts/commonInfo.html', {
        'form': form,
        'department_list': department_list,
    })


@login_required
@hr_admin_required
@require_http_methods(["POST"])
def approve_employee(request, user_id):
    """HR Admin: Approve employee account"""
    try:
        user = User.objects.get(id=user_id, role='employee')
        user.is_approved = True
        # When approving an account, also ensure it is active so the user can log in
        user.is_active = True
        user.save()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Employee approved successfully!'})
        
        messages.success(request, f'Employee {user.username} approved successfully!')
        return redirect('accounts:employee_management')
    except User.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Employee not found!'})
        messages.error(request, 'Employee not found.')
        return redirect('accounts:employee_management')
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Error approving employee!'})
        messages.error(request, 'Error approving employee.')
        return redirect('accounts:employee_management')


@login_required
@hr_admin_required
@require_http_methods(["POST"])
def reject_employee(request, user_id):
    """HR Admin: Reject/disable employee account"""
    try:
        user = User.objects.get(id=user_id, role='employee')
        user.is_approved = False
        user.is_active = False
        user.save()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Employee account disabled!'})
        
        messages.success(request, f'Employee {user.username} account disabled!')
        return redirect('accounts:employee_management')
    except User.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Employee not found!'})
        messages.error(request, 'Employee not found.')
        return redirect('accounts:employee_management')
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Error disabling employee!'})
        messages.error(request, 'Error disabling employee.')
        return redirect('accounts:employee_management')


@login_required
@hr_admin_required
@require_http_methods(["POST"])
def delete_employee(request, user_id):
    """HR Admin: Delete employee account"""
    try:
        user = User.objects.get(id=user_id, role='employee')
        username = user.username

        # Delete related EmployeeProfile
        try:
            from .models import EmployeeProfile
            EmployeeProfile.objects.filter(user=user).delete()
        except Exception:
            pass

        # Delete TaxInfo and BankingInfo
        try:
            from .models import TaxInfo, BankingInfo
            TaxInfo.objects.filter(user=user).delete()
            BankingInfo.objects.filter(user=user).delete()
        except Exception:
            pass

        # Delete payroll records for this user
        try:
            from payroll.models import EmployeePayrollDetails
            EmployeePayrollDetails.objects.filter(user=user).delete()
        except Exception:
            pass

        # Delete attendance-related records and uploaded files
        try:
            from attendance.models import AttendanceRecord, Leave, Overtime, BiometricLog
            # delete leave supporting documents files where present
            try:
                from django.core.files.storage import default_storage
                leaves = Leave.objects.filter(user=user)
                for lv in leaves:
                    try:
                        if getattr(lv, 'supporting_document', None):
                            path = lv.supporting_document.name
                            if path:
                                try:
                                    default_storage.delete(path)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                leaves.delete()
            except Exception:
                # fallback: just delete leave records
                try:
                    Leave.objects.filter(user=user).delete()
                except Exception:
                    pass

            # Attendance and overtime
            AttendanceRecord.objects.filter(user=user).delete()
            Overtime.objects.filter(user=user).delete()

            # Biometric logs: remove records linking to this user and/or matching employee_id
            try:
                emp_id = getattr(user, 'employee_id', None)
                if emp_id:
                    BiometricLog.objects.filter(employee_id=emp_id).delete()
                # Also delete logs with FK to this user
                BiometricLog.objects.filter(user=user).delete()
            except Exception:
                # generic deletion
                try:
                    BiometricLog.objects.filter(user=user).delete()
                except Exception:
                    pass
        except Exception:
            pass

        # Delete profile picture file if present
        try:
            from django.core.files.storage import default_storage
            pic = getattr(user, 'profile_picture', None)
            if pic and getattr(pic, 'name', None):
                try:
                    default_storage.delete(pic.name)
                except Exception:
                    pass
        except Exception:
            pass

        # Finally delete the user
        user.delete()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Employee deleted successfully!'})
        
        messages.success(request, f'Employee {username} deleted successfully!')
        return redirect('accounts:employee_management')
    except User.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Employee not found!'})
        messages.error(request, 'Employee not found.')
        return redirect('accounts:employee_management')
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Error deleting employee!'})
        messages.error(request, 'Error deleting employee.')
        return redirect('accounts:employee_management')


@login_required
@hr_admin_required
def edit_employee_detail(request, user_id):
    """HR Admin: View employee details"""
    try:
        # Don't restrict by role here so HR can change a user's role from this page
        employee = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, 'Employee not found.')
        return redirect('accounts:employee_management')
    
    # Get tax info safely
    try:
        tax_info = employee.taxinfo
    except TaxInfo.DoesNotExist:
        tax_info = TaxInfo.objects.create(user=employee)
    except Exception:
        tax_info = None

    # Get banking info safely
    try:
        banking_info = employee.bankinginfo
    except BankingInfo.DoesNotExist:
        banking_info = BankingInfo.objects.create(user=employee)
    except Exception:
        banking_info = None

    # Get employee profile safely
    try:
        profile = employee.employeeprofile
    except EmployeeProfile.DoesNotExist:
        profile = EmployeeProfile.objects.create(user=employee)
    except Exception:
        profile = None
    
    # get the latest payroll record safely (single instance)
    try:
        payroll_details = EmployeePayrollDetails.objects.filter(user=employee)
    except Exception:
        payroll_details = None
    
    # Get login history safely
    # try:
    #     all_logins = list(LoginAttempt.objects.filter(username=employee.username))
    #     all_logins.sort(key=lambda x: x.timestamp, reverse=True)
    #     login_history = all_logins[:10]
    # except Exception:
    #     login_history = []
    
    if request.method == 'POST':
        form = HRUserManagementForm(request.POST, request.FILES,
                      instance=employee,
                      employee_profile=profile,
                      tax_info=tax_info,
                      banking_info=banking_info,
                      payroll_details=payroll_details)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'Employee details updated successfully!')
                return redirect('accounts:edit_employee_detail', user_id=user_id)
            except Exception as e:
                messages.error(request, 'Error updating employee details.')
    else:
        # Pass payroll_details to the form on GET so payroll fields are prefilled
        form = HRUserManagementForm(
            instance=employee,
            employee_profile=profile,
            tax_info=tax_info,
            banking_info=banking_info,
            payroll_details=payroll_details,
        )

    return render(request, 'accounts/edit_employee_detail.html', {
        'employee': employee,
        'profile': profile,
        'form': form,
        'tax_info': tax_info,
        'banking_info': banking_info,
        'payroll_details': payroll_details,
    })


@login_required
@hr_admin_required
def employee_detail(request, user_id):
    """HR Admin: View employee data in table form"""
    try:
        employee = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, 'Employee not found.')
        return redirect('accounts:employee_management')
    
    try:
        profile = employee.employeeprofile
    except EmployeeProfile.DoesNotExist:
        profile = EmployeeProfile.objects.create(user=employee)
    except Exception:
        profile = None

    # Get tax info safely (best-effort)
    try:
        tax_info = employee.taxinfo
    except TaxInfo.DoesNotExist:
        try:
            tax_info = TaxInfo.objects.create(user=employee)
        except Exception:
            tax_info = None
    except Exception:
        tax_info = None

    # Get banking info safely (best-effort)
    try:
        banking_info = employee.bankinginfo
    except BankingInfo.DoesNotExist:
        try:
            banking_info = BankingInfo.objects.create(user=employee)
        except Exception:
            banking_info = None
    except Exception:
        banking_info = None


    # Get latest payroll info (best-effort)
    try:
        payroll = EmployeePayrollDetails.objects.filter(user=employee).order_by('-id').first()
    except Exception:
        payroll = None

    # Get current year's leave quota (best-effort)
    try:
        from attendance.models import LeaveQuota
        current_year = date.today().year
        leave_quota = LeaveQuota.objects.filter(user=employee, year=current_year).first()
    except Exception:
        leave_quota = None

    # Get login history safely
    try:
        all_logins = list(LoginAttempt.objects.filter(username=employee.username))
        all_logins.sort(key=lambda x: x.timestamp, reverse=True)
        login_history = all_logins[:10]
    except Exception:
        login_history = []
        
        
    return render(request, 'accounts/employee_detail.html', {
        'employee': employee,
        'profile': profile,
        'tax_info': tax_info,
        'banking_info': banking_info,
        'login_history': login_history,
        'payroll': payroll,
        'leave_quota': leave_quota,
    })




@login_required
def user_details(request, user_id):
    """HR Admin: View employee details"""
    try:
        employee = User.objects.get(id=user_id, role='employee')
    except User.DoesNotExist:
        messages.error(request, 'Employee not found.')
        return redirect('accounts:employee_management')
    
    try:
        profile = employee.employeeprofile
    except EmployeeProfile.DoesNotExist:
        profile = EmployeeProfile.objects.create(user=employee)
    except Exception:
        profile = None

    # Get tax info safely (best-effort)
    try:
        tax_info = employee.taxinfo
    except TaxInfo.DoesNotExist:
        try:
            tax_info = TaxInfo.objects.create(user=employee)
        except Exception:
            tax_info = None
    except Exception:
        tax_info = None

    # Get banking info safely (best-effort)
    try:
        banking_info = employee.bankinginfo
    except BankingInfo.DoesNotExist:
        try:
            banking_info = BankingInfo.objects.create(user=employee)
        except Exception:
            banking_info = None
    except Exception:
        banking_info = None

     # Get latest payroll info (best-effort)
    try:
        payroll = EmployeePayrollDetails.objects.filter(user=employee).order_by('-id').first()
    except Exception:
        payroll = None
    # Get current year's leave quota (best-effort)
    try:
        from attendance.models import LeaveQuota
        current_year = date.today().year
        leave_quota = LeaveQuota.objects.filter(user=employee, year=current_year).first()
    except Exception:
        leave_quota = None

    return render(request, 'accounts/user_detail.html', {
        'employee': employee,
        'profile': profile,
        'tax_info': tax_info,
        'banking_info': banking_info,
        'payroll': payroll,
        'leave_quota': leave_quota,
    })



@login_required
@hr_admin_required
def analytics(request):
    """HR Admin: Analytics and reports"""
    try:
        # Employee statistics - use safer queries
        all_employees = list(User.objects.filter(role='employee'))
        current_employees = len(all_employees)
        all_hr_employees = list(User.objects.filter(role='hr_admin'))
        hr_employee_count = len(all_hr_employees)
        total_employees = current_employees + hr_employee_count
        approved_employees = len([emp for emp in all_employees if emp.is_approved])+len([emp for emp in all_hr_employees if emp.is_approved])
        pending_employees = len([emp for emp in all_employees if not emp.is_approved])+len([emp for emp in all_hr_employees if not emp.is_approved])
        
        
        # Recent activity - last 30 days
        cutoff_date = timezone.now() - timedelta(days=30)
        
        # Recent registrations
        recent_registrations = []
        for emp in all_employees:
            if emp.created_at >= cutoff_date:
                recent_registrations.append(emp)
        recent_registrations.sort(key=lambda x: x.created_at, reverse=True)
        recent_registrations = recent_registrations[:10]
        
        # Recent logins - use manual filtering for djongo compatibility
        try:
            # Get all successful logins first
            all_successful_logins = []
            all_login_attempts = list(LoginAttempt.objects.all())
            
            for login in all_login_attempts:
                if login.success and login.timestamp >= cutoff_date:
                    all_successful_logins.append(login)
            
            # Sort by timestamp (most recent first)
            all_successful_logins.sort(key=lambda x: x.timestamp, reverse=True)
            recent_logins = all_successful_logins[:10]
            
        except Exception:
            recent_logins = []
        
        # Additional KPIs
        try:
            now = timezone.now()
            # Active employees (role='employee' and is_active=True)
            active_employees = len([emp for emp in all_employees if getattr(emp, 'is_active', False)])
            active_employees += len([emp for emp in all_hr_employees if getattr(emp, 'is_active', False)])
            # New joinees this month
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            new_joinees_month = len([emp for emp in all_employees if getattr(emp, 'created_at', None) and emp.created_at >= start_of_month])

            # Attrition rate (approx): number of employees deactivated in last 30 days / total_employees
            deactivated_last_30 = len([emp for emp in all_employees if (not getattr(emp, 'is_active', True)) and getattr(emp, 'updated_at', None) and emp.updated_at >= cutoff_date])
            try:
                attrition_rate = round((deactivated_last_30 / total_employees) * 100, 1) if total_employees else 0.0
            except Exception:
                attrition_rate = 0.0

            # Average employee age from profile.dob
            ages = []
            today = date.today()
            for emp in all_employees+all_hr_employees:
                try:
                    prof = getattr(emp, 'employeeprofile', None)
                    if prof and getattr(prof, 'dob', None):
                        dob = prof.dob
                        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                        ages.append(age)
                except Exception:
                    continue
            if ages:
                avg_employee_age = round(sum(ages) / len(ages), 1)
            else:
                avg_employee_age = 'N/A'
            # Gender ratio counts (Male / Female / Other) - try profile then user field
            male_count = 0
            female_count = 0
            other_count = 0
            try:
                combined = list(all_employees) + list(all_hr_employees)
            except Exception:
                combined = list(all_employees)

            for emp in combined:
                try:
                    g = None
                    prof = getattr(emp, 'employeeprofile', None)
                    if prof and getattr(prof, 'gender', None):
                        g = getattr(prof, 'gender')
                    elif getattr(emp, 'gender', None):
                        g = getattr(emp, 'gender')
                    # Normalize and classify
                    if g is None:
                        continue
                    g_norm = str(g).strip().lower()
                    if g_norm in ('m', 'male', 'man'):
                        male_count += 1
                    elif g_norm in ('f', 'female', 'woman'):
                        female_count += 1
                    else:
                        other_count += 1
                except Exception:
                    continue
            try:
                total_gender = male_count + female_count + other_count
                if total_gender:
                    gender_percentages = {
                        'male': round((male_count / total_gender) * 100, 1),
                        'female': round((female_count / total_gender) * 100, 1),
                        'other': round((other_count / total_gender) * 100, 1),
                    }
                else:
                    gender_percentages = {'male': 0.0, 'female': 0.0, 'other': 0.0}
            except Exception:
                gender_percentages = {'male': 0.0, 'female': 0.0, 'other': 0.0}

            # Employees by grade counts
            grade_counts = {}
            try:
                for emp in combined:
                    try:
                        g = getattr(emp, 'grade', None)
                        if not g:
                            prof = getattr(emp, 'employeeprofile', None)
                            g = getattr(prof, 'grade', None) if prof is not None else None
                        g_label = str(g).strip() if g else 'Unknown'
                        if not g_label:
                            g_label = 'Unknown'
                        grade_counts[g_label] = grade_counts.get(g_label, 0) + 1
                    except Exception:
                        continue
            except Exception:
                grade_counts = {}

            try:
                grade_labels = list(grade_counts.keys())
                grade_values = [grade_counts[k] for k in grade_labels]
                try:
                    grade_items = list(zip(grade_labels, grade_values))
                except Exception:
                    grade_items = []
            except Exception:
                grade_labels = []
                grade_values = []
                grade_items = []

            # Employees by department counts
            dept_counts = {}
            try:
                for emp in combined:
                    try:
                        dep = getattr(emp, 'department', None)
                        if not dep:
                            prof = getattr(emp, 'employeeprofile', None)
                            dep = getattr(prof, 'department', None) if prof is not None else None
                        dep_label = str(dep).strip() if dep else 'Unknown'
                        if not dep_label:
                            dep_label = 'Unknown'
                        dept_counts[dep_label] = dept_counts.get(dep_label, 0) + 1
                    except Exception:
                        continue
            except Exception:
                dept_counts = {}

            try:
                dept_labels = list(dept_counts.keys())
                dept_values = [dept_counts[k] for k in dept_labels]
                try:
                    dept_items = list(zip(dept_labels, dept_values))
                except Exception:
                    dept_items = []
            except Exception:
                dept_labels = []
                dept_values = []
                dept_items = []
        except Exception:
            active_employees = 0
            new_joinees_month = 0
            attrition_rate = 0.0
            avg_employee_age = 'N/A'
            male_count = 0
            female_count = 0
            other_count = 0
            gender_percentages = {'male': 0.0, 'female': 0.0, 'other': 0.0}
            grade_counts = {}
            grade_labels = []
            grade_values = []
            grade_items = []
        
    except Exception as e:
        # Fallback with default values
        current_employees = 0
        approved_employees = 0
        pending_employees = 0
        recent_registrations = []
        recent_logins = []
        messages.warning(request, 'Some analytics data may not be available.')
    
    context = {
        'current_employees': current_employees,
        'approved_employees': approved_employees,
        'pending_employees': pending_employees,
        'recent_registrations': recent_registrations,
        'recent_logins': recent_logins,
        'hr_employee_count': hr_employee_count,
        'total_employees': total_employees,
        'active_employees': active_employees,
        'new_joinees_month': new_joinees_month,
        'attrition_rate': attrition_rate,
        'avg_employee_age': avg_employee_age,
        'male_count': male_count,
        'female_count': female_count,
        'other_count': other_count,
        'gender_percentages': gender_percentages,
        'grade_counts': grade_counts,
        'grade_labels': grade_labels,
        'grade_values': grade_values,
        'grade_items': grade_items,
        'dept_counts': dept_counts,
        'dept_labels': dept_labels,
        'dept_values': dept_values,
        'dept_items': dept_items,
    }
    
    return render(request, 'accounts/analytics.html', context)



@login_required
@hr_admin_required
@require_http_methods(["POST"])
def reactivate_employee(request, user_id):
    """HR Admin: Reactivate previously disabled employee account"""
    try:
        user = User.objects.get(id=user_id, role='employee')
        user.is_active = True
        user.is_approved = True
        user.save()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Employee reactivated successfully!'})

        messages.success(request, f'Employee {user.username} reactivated successfully!')
        return redirect('accounts:employee_management')
    except User.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Employee not found!'})
        messages.error(request, 'Employee not found.')
        return redirect('accounts:employee_management')
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Error reactivating employee!'})
        messages.error(request, 'Error reactivating employee.')
        return redirect('accounts:employee_management')
    
    