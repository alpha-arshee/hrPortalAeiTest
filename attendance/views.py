from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
import logging

from accounts.decorators import hr_admin_required
from .forms import LeaveRequestForm, EmployeeAttendanceRequestForm, HRApproveAttendanceRequestForm
from .forms import HRAddAttendanceForm
from django.db.models import Q
from .models import BiometricLog, AttendanceRequest
from .models import Overtime

from accounts.models import User
from datetime import date
from django.utils import timezone
from .models import Leave

from attendance.models import LeaveQuota
from collections import defaultdict
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

PAID_LEAVE_TYPES = {
    'casual',
    'sick',
    'privilege',
    'paid',
}


def _create_leave_biometric_log(leave, requested_date, approved_by):
    """Create a biometric record for an approved paid leave day."""
    punch_time = timezone.localtime(timezone.now()).time().replace(microsecond=0).isoformat(timespec='seconds')
    BiometricLog.objects.create(
        employee_id=leave.user.employee_id or leave.user.username,
        user=leave.user,
        first_name=leave.user.first_name,
        department=leave.user.department or 'N/A',
        punch_date=requested_date,
        punch_time=punch_time,
        status='IN',
        device_id='HR_APPROVED_LEAVE',
        marked_by_hr=True,
        hr_reason=f'Approved leave: {leave.get_leave_type_display()}',
        marked_by=approved_by,
        marked_at=timezone.now(),
    )

# Create your views here.

@login_required
def user_attendance_dashboard(request):
    name = request.user.username
    email = request.user.email
    employee_id = getattr(request.user, 'employee_id', 'N/A')
     # You can extend this to fetch and display more attendance data as needed
    # Show logs that are either linked to the user, or match the user's employee_id.
    employee_id = getattr(request.user, 'employee_id', None)
    # parse optional year/month from query string (GET) so user can pick a month
    today = date.today()
    year_q = request.GET.get('year')
    month_q = request.GET.get('month')
    try:
        year = int(year_q) if year_q else today.year
        month = int(month_q) if month_q else today.month
    except ValueError:
        year = today.year
        month = today.month

    import calendar
    days_in_month = calendar.monthrange(year, month)[1]

    period_start = date(year, month, 1)
    # if current month, end at today; otherwise end at month end
    if year == today.year and month == today.month:
        period_end = today
        total_days = today.day
    else:
        period_end = date(year, month, days_in_month)
        total_days = days_in_month

    # Filter punch logs to the selected period and for this user (linked or by employee_id)
    if employee_id:
        punch_logs = BiometricLog.objects.filter(
            Q(user=request.user) | Q(employee_id=employee_id),
            punch_date__gte=period_start,
            punch_date__lte=period_end,
        ).order_by('-punch_date', '-punch_time')[:200]
    else:
        punch_logs = BiometricLog.objects.filter(
            user=request.user,
            punch_date__gte=period_start,
            punch_date__lte=period_end,
        ).order_by('-punch_date', '-punch_time')[:200]

    # compute unique present days in the period (any status counts)
    present_dates = set()
    try:
        for log in punch_logs:
            pdate = getattr(log, 'punch_date', None)
            try:
                if hasattr(pdate, 'date'):
                    pdate = pdate.date()
            except Exception:
                pass
            if pdate:
                present_dates.add(pdate)
    except Exception:
        present_dates = set()

    present_days = len(present_dates)
    # fetch overtime entries for this user in the selected period
    try:
        overtime_entries = Overtime.objects.filter(user=request.user, date__gte=period_start, date__lte=period_end).order_by('-date')
    except Exception:
        overtime_entries = []
    # compute overtime totals (Python-side Decimal summation to avoid DB date-extract issues)
    from decimal import Decimal
    overtime_total_hours = Decimal('0.00')
    overtime_total_compensation = Decimal('0.00')
    try:
        for ot in overtime_entries:
            try:
                overtime_total_hours += Decimal(str(ot.hours or '0'))
            except Exception:
                pass
            try:
                overtime_total_compensation += Decimal(str(ot.compensation or '0'))
            except Exception:
                pass
    except Exception:
        overtime_total_hours = Decimal('0.00')
        overtime_total_compensation = Decimal('0.00')

    # list of years for picker (two years back to two years forward)
    current_year = today.year
    years = list(range(current_year - 2, current_year + 3))

    months = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
    ]

    context = {
        'name': name,
        'email': email,
        'employee_id': employee_id,
        'punch_logs': punch_logs,
        'present_days': present_days,
        'year': year,
        'month': month,
        'years': years,
        'months': months,
        'total_days': total_days,
        'overtime_entries': overtime_entries,
        'overtime_total_hours': overtime_total_hours,
        'overtime_total_compensation': overtime_total_compensation,
    }
    return render(request, 'attendance/user_attendance_dashboard.html', context)

@login_required
def request_leave(request):
    # compute remaining leaves for the current user for the current year
    try:
        today = date.today()
        current_year = today.year
        try:
            quota = LeaveQuota.objects.get(user=request.user, year=current_year)
            left_paid_leaves = quota.remaining_paid_leaves
            left_unpaid_leaves = max((quota.total_unpaid_leaves or 0) - (quota.used_unpaid_leaves or 0), 0)
        except LeaveQuota.DoesNotExist:
            left_paid_leaves = 0
            left_unpaid_leaves = 0
    except Exception:
        # Fallback to zero if anything goes wrong; log for diagnostics
        logger.exception('Failed to compute leave quota for user %s', getattr(request.user, 'id', None))
        left_paid_leaves = 0
        left_unpaid_leaves = 0
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # validate requested days against user's quota
                cleaned = form.cleaned_data
                s = cleaned.get('start_date')
                e = cleaned.get('end_date')
                lt = cleaned.get('leave_type')
                try:
                    requested_days = (e - s).days + 1 if (s and e) else None
                except Exception:
                    requested_days = None

                if lt in PAID_LEAVE_TYPES and requested_days is not None and requested_days > (left_paid_leaves or 0):
                    messages.error(request, f'Not enough paid leaves left ({left_paid_leaves}). You requested {requested_days} days.')
                elif lt == 'unpaid' and requested_days is not None and requested_days > (left_unpaid_leaves or 0):
                    # optional: restrict unpaid too — currently mirror paid behavior
                    messages.error(request, f'Not enough unpaid leaves left ({left_unpaid_leaves}). You requested {requested_days} days.')
                else:
                    # check for overlapping leaves (approved or pending)
                    # Perform a DB-friendly overlap check: fetch candidate leaves by user/status
                    # and evaluate date overlap in Python. This avoids complex SQL that djongo
                    # sometimes fails to parse for combined date+in-list filters.
                    overlapping = None
                    try:
                        if s and e:
                            candidates = Leave.objects.filter(user=request.user, status__in=['approved', 'pending']).only('start_date', 'end_date', 'status')
                            overlapping_list = []
                            for ov in candidates:
                                try:
                                    if ov.start_date and ov.end_date and (ov.end_date >= s and ov.start_date <= e):
                                        overlapping_list.append(ov)
                                except Exception:
                                    # ignore individual malformed records
                                    continue
                            overlapping = overlapping_list
                        else:
                            overlapping = []
                    except Exception:
                        # Log DB/query exceptions for diagnostics and block submission
                        try:
                            logger.exception('Failed to query candidate leaves for overlap check for user %s', getattr(request.user, 'id', None))
                        except Exception:
                            pass
                        overlapping = None

                    if overlapping is None:
                        messages.error(request, 'Could not verify overlapping leaves due to a system error. Please try again later.')
                    elif overlapping:
                        # build a short summary of overlaps for the user
                        msgs = []
                        try:
                            for ov in overlapping[:5]:
                                sd = getattr(ov, 'start_date', None)
                                ed = getattr(ov, 'end_date', None)
                                msgs.append(f"{sd} to {ed} ({getattr(ov, 'status', '')})")
                        except Exception:
                            msgs = ['existing overlapping leave(s)']
                        messages.error(request, 'Your requested leave overlaps with existing leave: ' + '; '.join(msgs))
                    else:
                        with transaction.atomic():
                            leave = form.save(commit=False)
                            leave.user = request.user
                            leave.save()
                        messages.success(request, "Leave request submitted.")
                        return redirect('attendance:leave_request')
            except Exception as e:
                logger.exception("Failed to save leave request")
                messages.error(request, "An error occurred while saving your request.")
        else:
            # show validation errors so you can diagnose why nothing was saved
            logger.debug("Leave form invalid: %s", form.errors.as_json())
            messages.error(request, "Please correct the errors below.")
    else:
        form = LeaveRequestForm()
    # include current user's leave requests so they can view status/history
    try:
        qs = Leave.objects.filter(user=request.user).order_by('-start_date')[:200]
        my_leaves = []
        for lv in qs:
            try:
                if lv.start_date and lv.end_date:
                    days = (lv.end_date - lv.start_date).days + 1
                else:
                    days = None
            except Exception:
                days = None
            my_leaves.append({'leave': lv, 'days': days})
    except Exception:
        my_leaves = []

    context = {
        'left_paid_leaves': left_paid_leaves,
        'left_unpaid_leaves': left_unpaid_leaves,
        'form': form,
        'my_leaves': my_leaves,
    }
    return render(request, 'attendance/leave_form.html', context)


@login_required
@hr_admin_required
def hr_leave_requests(request):
    """HR view: list leave requests with simple filtering and decision actions."""
    # Default to 'all' so HR sees all requests by default
    status = request.GET.get('status', 'all')
    if status == 'all':
        qs = Leave.objects.all().order_by('-start_date')
    else:
        qs = Leave.objects.filter(status__iexact=status).order_by('-start_date')

    # simple paging hint: limit rows to 200 to avoid huge pages
    qs = qs[:200]

    context = {
        'leave_requests': qs,
        'filter_status': status,
    }
    return render(request, 'attendance/hr_leave_requests.html', context)


@login_required
@hr_admin_required
@require_http_methods(['POST'])
def approve_leave(request, leave_id):
    leave = get_object_or_404(Leave, pk=leave_id)
    # avoid double-applying quota if already approved
    if leave.status == 'approved':
        messages.info(request, f'Leave request #{leave_id} is already approved.')
        ref = request.META.get('HTTP_REFERER')
        return redirect(ref or 'attendance:hr_leave_requests')

    try:
        # Calculate day counts split by year to correctly update per-year quotas
        start = leave.start_date
        end = leave.end_date
        days_by_year = {}
        for yr in range(start.year, end.year + 1):
            year_start = max(start, date(yr, 1, 1))
            year_end = min(end, date(yr, 12, 31))
            if year_end >= year_start:
                days = (year_end - year_start).days + 1
                days_by_year[yr] = days

        with transaction.atomic():
            # update LeaveQuota used counts for each affected year
            for yr, days in days_by_year.items():
                quota, created = LeaveQuota.objects.get_or_create(
                    user=leave.user,
                    year=yr,
                    defaults={
                        'total_paid_leaves': 0,
                        'total_unpaid_leaves': 0,
                        'used_paid_leaves': 0,
                        'used_unpaid_leaves': 0,
                    }
                )
                quota.register_leave_usage(leave.leave_type, days)
                quota.save()

            # For paid leave, create biometric rows so the employee is shown as present.
            if leave.leave_type in PAID_LEAVE_TYPES:
                from datetime import timedelta
                current_day = start
                while current_day <= end:
                    _create_leave_biometric_log(leave, current_day, request.user)
                    current_day = current_day + timedelta(days=1)

            # mark the leave as approved
            leave.status = 'approved'
            try:
                leave.decision_date = timezone.now()
            except Exception:
                pass
            try:
                leave.decision_by = request.user
            except Exception:
                pass
            leave.save()

        messages.success(request, f'Leave request #{leave_id} approved.')
    except Exception as e:
        logger.exception('Failed to approve leave %s', leave_id)
        messages.error(request, f'Failed to approve leave #{leave_id}: {e}')

    ref = request.META.get('HTTP_REFERER')
    return redirect(ref or 'attendance:hr_leave_requests')


@login_required
@hr_admin_required
@require_http_methods(['POST'])
def reject_leave(request, leave_id):
    leave = get_object_or_404(Leave, pk=leave_id)
    try:
        leave.status = 'rejected'
        try:
            leave.decision_date = timezone.now()
        except Exception:
            pass
        try:
            leave.decision_by = request.user
        except Exception:
            pass
        leave.save()
        messages.success(request, f'Leave request #{leave_id} rejected.')
    except Exception as e:
        messages.error(request, f'Failed to reject leave #{leave_id}: {e}')
    ref = request.META.get('HTTP_REFERER')
    return redirect(ref or 'attendance:hr_leave_requests')



@login_required
@hr_admin_required
def hr_biometric_logs_view(request):
    logs = BiometricLog.objects.all().order_by('-punch_date', '-punch_time')[:500]

    # summary stats
    total_employees = User.objects.count()
    today = date.today()
    # number of unique employees who have an IN record today
    # Avoid COUNT(DISTINCT ...) because djongo's SQL parser can fail for that pattern.
    # Instead fetch employee_ids and count unique values in Python.
    employee_ids_qs = BiometricLog.objects.filter(punch_date=today, status='IN').values_list('employee_id', flat=True)
    try:
        employee_ids = list(employee_ids_qs)
        present_today = len(set(employee_ids))
    except Exception:
        # Fallback: if the values_list query fails for any reason, set to 0 and log
        present_today = 0
        logger.exception("Failed to compute present_today count")

    on_leave = total_employees - present_today
    
    all_employees = list(User.objects.all())
    # current_employees should reflect only active accounts
    current_employees = len([emp for emp in all_employees if getattr(emp, 'is_active', False)])
    
    context = {
        'logs': logs,
        # 'total_employees': total_employees,
        'present_today': present_today,
        'on_leave':on_leave,
        'total_employees': current_employees,
    }
    return render(request, 'attendance/hr_biometric_logs.html', context)


@login_required
@hr_admin_required
def hr_add_attendance(request):
    """Allow HR to add a manual attendance (creates a BiometricLog marked as HR-created)."""
    if request.method == 'POST':
        form = HRAddAttendanceForm(request.POST)
        if form.is_valid():
            bl = form.save(commit=False)
            bl.marked_by_hr = True
            bl.marked_by = request.user
            try:
                bl.marked_at = timezone.now()
            except Exception:
                pass
            # set a device marker so raw device column isn't empty
            try:
                bl.device_id = f"HR_MANUAL_{request.user.id}"
            except Exception:
                bl.device_id = 'HR_MANUAL'
            bl.save()
            messages.success(request, 'Manual attendance added.')
            return redirect('attendance:hr_biometric_logs')
        else:
            messages.error(request, 'Please correct the errors in the form.')
    else:
        form = HRAddAttendanceForm()

    context = {'form': form}
    return render(request, 'attendance/hr_add_attendance.html', context)


@login_required
@hr_admin_required
def hr_mark_holiday(request):
    """Manage holidays: show create form (GET), create logs (POST action=create),
    or edit existing holiday metadata (POST action=edit).
    """
    # GET: render management UI
    if request.method == 'GET':
        # collect distinct holiday dates/names from existing BiometricLog rows
        holidays_map = {}
        try:
            for hd, hn in BiometricLog.objects.filter(holiday_date__isnull=False).values_list('holiday_date', 'holiday_name'):
                try:
                    key = hd.isoformat() if hasattr(hd, 'isoformat') else str(hd)
                except Exception:
                    key = str(hd)
                holidays_map.setdefault(key, set()).add(hn or '')
            # flatten into list of dicts for template; include date object and ISO string
            holidays = []
            for k, names in sorted(holidays_map.items(), reverse=True):
                for nm in names:
                    # k is ISO string; try to build a date object for formatting in template
                    try:
                        from datetime import date as _date
                        date_obj = _date.fromisoformat(k)
                        date_str = k
                    except Exception:
                        date_obj = None
                        date_str = str(k)
                    holidays.append({'date': date_obj, 'date_str': date_str, 'name': nm})
        except Exception:
            logger.exception('Failed to collect existing holidays for UI')
            holidays = []

        context = {'holidays': holidays}
        return render(request, 'attendance/hr_mark_holiday.html', context)

    # Only POST beyond this point
    action = request.POST.get('action', 'create')
    if action == 'create':
        holiday_name = request.POST.get('holiday_name')
        holiday_date_raw = request.POST.get('holiday_date')
        if not holiday_name or not holiday_date_raw:
            messages.error(request, 'Please provide holiday name and date.')
            return redirect('attendance:hr_mark_holiday')

        try:
            from datetime import date as _date
            hd = _date.fromisoformat(holiday_date_raw)
        except Exception:
            messages.error(request, 'Invalid holiday date format.')
            return redirect('attendance:hr_mark_holiday')

        created = 0
        skipped = 0
        try:
            # djongo has issues decoding boolean filters in some cases; use __exact
            users_qs = User.objects.all()
            for u in users_qs:
                if not getattr(u, 'is_active', False):
                    continue
                eid = getattr(u, 'employee_id', '') or ''
                exists = BiometricLog.objects.filter(holiday_date=hd, employee_id=eid, holiday_name=holiday_name).exists()
                if exists:
                    skipped += 1
                    continue

                bl = BiometricLog(
                    user=u,
                    employee_id=eid,
                    first_name=u.get_full_name() or u.username,
                    department=getattr(u, 'department', '') or '',
                    punch_time='',
                    punch_date=hd,
                    status='IN',
                    device_id=f'{holiday_name}_{hd.isoformat()}',
                    marked_by_hr=True,
                    marked_by=request.user,
                    marked_at=timezone.now(),
                    holiday_name=holiday_name,
                    holiday_marked_by=request.user,
                    holiday_date=hd,
                )
                try:
                    bl.save()
                    created += 1
                except Exception:
                    logger.exception('Failed to create holiday BiometricLog for user %s', getattr(u, 'id', None))
                    skipped += 1

            messages.success(request, f'Holiday marked: created {created} logs, skipped {skipped}.')
        except Exception:
            logger.exception('Failed to mark holiday')
            messages.error(request, 'Failed to mark holiday due to an internal error.')

        return redirect('attendance:hr_mark_holiday')

    if action == 'delete':
        orig_date_raw = request.POST.get('original_date')
        orig_name = request.POST.get('original_name')
        if not orig_date_raw or not orig_name:
            messages.error(request, 'Original holiday date/name required for delete.')
            return redirect('attendance:hr_mark_holiday')

        try:
            from datetime import date as _date
            orig_date = _date.fromisoformat(orig_date_raw)
        except Exception:
            messages.error(request, 'Invalid date format for delete.')
            return redirect('attendance:hr_mark_holiday')

        try:
            qs = BiometricLog.objects.filter(holiday_date=orig_date, holiday_name=orig_name)
            count = qs.count()
            if count:
                qs.delete()
                messages.success(request, f'Deleted {count} holiday log(s).')
            else:
                messages.info(request, 'No matching holiday logs found to delete.')
        except Exception:
            logger.exception('Failed to delete holiday entries')
            messages.error(request, 'Failed to delete holiday entries.')

        return redirect('attendance:hr_mark_holiday')

    if action == 'edit':
        # expects original_date, original_name, new_name, new_date (optional)
        orig_date_raw = request.POST.get('original_date')
        orig_name = request.POST.get('original_name')
        new_name = request.POST.get('new_name') or orig_name
        new_date_raw = request.POST.get('new_date') or orig_date_raw

        if not orig_date_raw or not orig_name:
            messages.error(request, 'Original holiday date/name required for edit.')
            return redirect('attendance:hr_mark_holiday')

        try:
            from datetime import date as _date
            orig_date = _date.fromisoformat(orig_date_raw)
            new_date = _date.fromisoformat(new_date_raw)
        except Exception:
            messages.error(request, 'Invalid date format for edit.')
            return redirect('attendance:hr_mark_holiday')

        try:
            qs = BiometricLog.objects.filter(holiday_date=orig_date, holiday_name=orig_name)
            updated = qs.update(holiday_name=new_name, holiday_date=new_date, holiday_marked_by=request.user, marked_by=request.user, marked_at=timezone.now())
            messages.success(request, f'Updated {updated} holiday log(s).')
        except Exception:
            logger.exception('Failed to edit holiday entries')
            messages.error(request, 'Failed to update holiday entries.')

        return redirect('attendance:hr_mark_holiday')

    messages.error(request, 'Unknown action.')
    return redirect('attendance:hr_mark_holiday')


@login_required
@hr_admin_required
def employee_attendance_log_view(request):
    """Show per-user present/absent counts for a month.

    Accepts optional query params `year` and `month`. Defaults to current month.
    Excludes users who have approved leave covering the period.
    """
    today = date.today()
    year = request.GET.get('year')
    month = request.GET.get('month')
    try:
        year = int(year) if year else today.year
        month = int(month) if month else today.month
    except ValueError:
        year = today.year
        month = today.month

    import calendar
    days_in_month = calendar.monthrange(year, month)[1]

    # period bounds
    period_start = date(year, month, 1)
    # if current month, end at today; otherwise end at month end
    if year == today.year and month == today.month:
        period_end = today
        total_days = today.day
    else:
        period_end = date(year, month, days_in_month)
        total_days = days_in_month

    # Build present-days map keyed by User.id.
    # Strategy: prefer BiometricLog.user if linked; otherwise try to match by employee_id
    try:
        # include both IN and OUT punches so any punch on a day counts as presence
        qs = BiometricLog.objects.select_related('user').filter(punch_date__gte=period_start, punch_date__lte=period_end).filter(status__in=['0','IN'])
        emp_dates_by_user = {}
        # also count raw biometric rows per user (IN)
        emp_raw_count_by_user = {}
        # cache for matching raw employee_id -> user_id (None if not found)
        eid_to_userid = {}

        # prepare a quick lookup of users by normalized employee_id to avoid repeated queries
        users_with_eid = User.objects.exclude(employee_id__isnull=True).values_list('id', 'employee_id')
        norm_eid_to_userid = {}
        for uid, ueid in users_with_eid:
            try:
                key = str(ueid).strip()
            except Exception:
                key = str(ueid)
            norm_eid_to_userid[key] = uid

        import re

        def normalize_eid_for_fuzzy(eid):
            if eid is None:
                return None
            s = str(eid).strip()
            if not s:
                return None
            # exact/ci
            if s in norm_eid_to_userid:
                return norm_eid_to_userid[s]
            upper = s.upper()
            for k, uid in norm_eid_to_userid.items():
                if k.upper() == upper:
                    return uid
            # fallback: compare numeric parts (e.g., 'EMP008' -> '8')
            nums = re.sub(r'\D', '', s)
            if nums:
                for k, uid in norm_eid_to_userid.items():
                    k_nums = re.sub(r'\D', '', str(k))
                    if k_nums and k_nums.lstrip('0') == nums.lstrip('0'):
                        return uid
            return None

        for log in qs:
            pdate = getattr(log, 'punch_date', None)
            try:
                if hasattr(pdate, 'date'):
                    pdate = pdate.date()
            except Exception:
                pass

            uid = None
            if getattr(log, 'user_id', None):
                uid = log.user_id
            else:
                raw_eid = getattr(log, 'employee_id', None)
                if raw_eid in eid_to_userid:
                    uid = eid_to_userid[raw_eid]
                else:
                    uid = normalize_eid_for_fuzzy(raw_eid)
                    eid_to_userid[raw_eid] = uid

            if uid:
                emp_dates_by_user.setdefault(uid, set()).add(pdate)
                emp_raw_count_by_user[uid] = emp_raw_count_by_user.get(uid, 0) + 1
    except Exception:
        emp_dates_by_user = {}

    # users on approved leave during the period
    # on_leave_qs = Leave.objects.filter(status='approved', start_date__lte=period_end, end_date__gte=period_start)
    # on_leave_user_ids = set(on_leave_qs.values_list('user_id', flat=True))

    absent_employees = []
    for user in User.objects.all().order_by('username'):
        eid = getattr(user, 'employee_id', None)
        # Show raw biometric row count as "present days" per user's request
        present_days = emp_raw_count_by_user.get(user.id, 0) if 'emp_raw_count_by_user' in locals() else 0
        # leave_days = 0
        # if user.id in on_leave_user_ids:
        #     # calculate leave days overlap for the period
        #     # approximate by summing leave overlap entries
        #     try:
        #         user_leaves = on_leave_qs.filter(user_id=user.id)
        #         for lv in user_leaves:
        #             # overlapping days count
        #             overlap_start = max(lv.start_date, period_start)
        #             overlap_end = min(lv.end_date, period_end)
        #             if overlap_end >= overlap_start:
        #                 leave_days += (overlap_end - overlap_start).days + 1
        #     except Exception:
        #         leave_days = 0

        absent_days = total_days - present_days
        if absent_days < 0:
            absent_days = 0

        absent_employees.append({
            'name': user.get_full_name() or user.username,
            'user_id': user.id,
            'employee_id': eid,
            'department': None,
            'present_days': present_days,
            'absent_days': absent_days,
            'total_days': total_days,
        })

    # offer a small year range for the picker (two years back to two years forward)
    # ensure year range exists for template even if earlier logic changed
    current_year = date.today().year
    years = list(range(current_year - 2, current_year + 3))

    context = {
        'absent_employees': absent_employees,
        'year': year,
        'month': month,
        'today': today,
        'years': years,
    }
    return render(request, 'attendance/employee_attendance_log.html', context)


@login_required
@hr_admin_required
def employee_attendance_detail_view(request, user_id):
    """Show attendance logs, leaves and overtime for a single employee for a selected month."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect('attendance:employee_attendance_log')

    today = date.today()
    year_q = request.GET.get('year')
    month_q = request.GET.get('month')
    try:
        year = int(year_q) if year_q else today.year
        month = int(month_q) if month_q else today.month
    except ValueError:
        year = today.year
        month = today.month

    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    period_start = date(year, month, 1)
    if year == today.year and month == today.month:
        period_end = today
    else:
        period_end = date(year, month, days_in_month)

    # If form submitted by HR, support adding manual attendance or creating Overtime
    if request.method == 'POST':
        # Support editing existing HR-created logs when `edit_log_id` is provided
        edit_log_id = request.POST.get('edit_log_id')
        if edit_log_id:
            try:
                bl = BiometricLog.objects.filter(pk=int(edit_log_id)).first()
            except Exception:
                bl = None

            if not bl:
                messages.error(request, 'Attendance record not found.')
            else:
                # ensure it's editable: must be HR-created
                if not getattr(bl, 'marked_by_hr', False):
                    messages.error(request, 'Only attendance entries created by HR are editable.')
                else:
                    # ensure the log belongs to this employee (by linked user or employee_id)
                    log_user_id = getattr(bl, 'user_id', None)
                    user_eid = getattr(user, 'employee_id', None)
                    if (log_user_id and log_user_id != user.id) or (not log_user_id and bl.employee_id != user_eid):
                        # give a helpful hint to open the correct employee detail
                        if log_user_id:
                            correct_url = f"/attendance/hr/employee/{log_user_id}/?edit_log_id={bl.id}"
                            messages.error(request, f'Attendance belongs to another employee. Open it at {correct_url}')
                        else:
                            messages.error(request, 'Attendance belongs to another employee.')
                    else:
                        # allow updating employee_id, punch_date, punch_time, status, hr_reason
                        new_eid = request.POST.get('employee_id') or getattr(user, 'employee_id', '')
                        pd = request.POST.get('punch_date')
                        pt = request.POST.get('punch_time')
                        status = request.POST.get('status', bl.status)
                        hr_reason = request.POST.get('hr_reason', bl.hr_reason)
                        try:
                            try:
                                punch_dt = date.fromisoformat(pd) if pd else bl.punch_date
                            except Exception:
                                punch_dt = bl.punch_date
                            bl.employee_id = new_eid
                            bl.punch_date = punch_dt
                            if pt:
                                bl.punch_time = pt
                            bl.status = status
                            bl.hr_reason = hr_reason
                            bl.marked_by = request.user
                            bl.marked_at = timezone.now()
                            bl.save()
                            messages.success(request, 'Attendance updated.')
                        except Exception:
                            logger.exception('Failed to update HR attendance')
                            messages.error(request, 'Failed to update attendance.')
            redirect_url = request.path + f'?year={year}&month={month}'
            return redirect(redirect_url)

        # If HR submitted an attendance entry (punch_date present) handle that next
        if request.POST.get('punch_date'):
            pd = request.POST.get('punch_date')
            pt = request.POST.get('punch_time')
            status = request.POST.get('status', 'IN')
            hr_reason = request.POST.get('hr_reason', '')
            try:
                try:
                    punch_dt = date.fromisoformat(pd)
                except Exception:
                    punch_dt = None
                if not punch_dt:
                    messages.error(request, 'Invalid date for attendance.')
                else:
                    punch_time = (pt or '').strip()
                    bl = BiometricLog.objects.create(
                        user=user,
                        employee_id=getattr(user, 'employee_id', None) or '',
                        punch_date=punch_dt,
                        punch_time=punch_time,
                        status=status,
                        marked_by_hr=True,
                        hr_reason=hr_reason,
                        marked_by=request.user,
                        marked_at=timezone.now(),
                        device_id=f'HR_MANUAL_{request.user.id}',
                    )
                    messages.success(request, 'Manual attendance added.')
            except Exception:
                logger.exception('Failed to add manual attendance')
                messages.error(request, 'Failed to add manual attendance.')
            redirect_url = request.path + f'?year={year}&month={month}'
            return redirect(redirect_url)

        # Otherwise fall back to existing overtime handling
        # support inline edit: if `ot_id` is present, update existing record
        ot_id = request.POST.get('ot_id')
        ot_date = request.POST.get('overtime_date')
        ot_hours = request.POST.get('overtime_hours')
        ot_reason = request.POST.get('overtime_reason', '')
        ot_compensation = request.POST.get('compensation','')
        try:
            from decimal import Decimal, InvalidOperation
            if not ot_date or not ot_hours:
                messages.error(request, 'Please provide date and hours for overtime.')
            else:
                # parse ISO date (expects YYYY-MM-DD)
                try:
                    od = date.fromisoformat(ot_date)
                except Exception:
                    messages.error(request, 'Invalid date format for overtime.')
                    od = None

                # normalize hours (allow comma or dot)
                raw_hours = str(ot_hours).strip().replace(',', '.')
                try:
                    hours = Decimal(raw_hours)
                except (InvalidOperation, ValueError):
                    messages.error(request, 'Invalid hours value for overtime.')
                    hours = None

                if od is not None and hours is not None:
                    # basic validation
                    if hours < 0:
                        messages.error(request, 'Overtime hours must be non-negative.')
                    else:
                        # clamp/validate reasonable range (e.g., <= 24)
                        if hours > Decimal('24'):
                            messages.error(request, 'Overtime hours looks too large.')
                        else:
                            # create record
                            try:
                                # include optional compensation if provided
                                comp_val = None
                                if ot_compensation:
                                    try:
                                        comp_val = Decimal(str(ot_compensation).strip().replace(',', '.'))
                                    except (InvalidOperation, ValueError):
                                        comp_val = None

                                if ot_id:
                                    # update existing record
                                    try:
                                        ot_obj = Overtime.objects.get(pk=int(ot_id), user=user)
                                        ot_obj.date = od
                                        ot_obj.hours = hours
                                        ot_obj.reason = ot_reason
                                        if comp_val is not None:
                                            ot_obj.compensation = comp_val
                                        ot_obj.save()
                                        messages.success(request, 'Overtime updated.')
                                    except Overtime.DoesNotExist:
                                        messages.error(request, 'Overtime record not found for update.')
                                    except Exception as e:
                                        logger.exception('Failed to update overtime')
                                        messages.error(request, f'Failed to update overtime: {str(e)}')
                                else:
                                    if comp_val is not None:
                                        Overtime.objects.create(user=user, date=od, hours=hours, reason=ot_reason, compensation=comp_val)
                                    else:
                                        Overtime.objects.create(user=user, date=od, hours=hours, reason=ot_reason)
                                    messages.success(request, 'Overtime added.')
                            except Exception as db_e:
                                logger.exception('Failed to create overtime')
                                messages.error(request, f'Failed to add overtime: {str(db_e)}')
        except Exception:
            logger.exception('Unexpected error while creating overtime')
            messages.error(request, 'Failed to add overtime due to an unexpected error.')
        # redirect back to the same page preserving year/month
        redirect_url = request.path + f'?year={year}&month={month}'
        return redirect(redirect_url)

    # Logs: prefer linked user, but include entries matching employee_id too
    eid = getattr(user, 'employee_id', None)
    if eid:
        logs = BiometricLog.objects.filter(
            Q(user=user) | Q(employee_id=eid),
            punch_date__gte=period_start,
            punch_date__lte=period_end,
        ).order_by('-punch_date', '-punch_time')
    else:
        logs = BiometricLog.objects.filter(
            user=user,
            punch_date__gte=period_start,
            punch_date__lte=period_end,
        ).order_by('-punch_date', '-punch_time')

    # If requested via GET to edit a specific HR-created log, prepare prefill data
    edit_prefill = None
    try:
        edit_id = request.GET.get('edit_log_id')
        if edit_id:
            try:
                elog = BiometricLog.objects.filter(pk=int(edit_id), marked_by_hr=True).first()
            except Exception:
                elog = None
            if elog:
                edit_prefill = {
                    'id': elog.id,
                    'employee_id': elog.employee_id,
                    'punch_date': getattr(elog.punch_date, 'isoformat', lambda: elog.punch_date)(),
                    'punch_time': elog.punch_time,
                    'status': elog.status,
                    'hr_reason': elog.hr_reason,
                }
    except Exception:
        edit_prefill = None

    # Leaves and overtime in period
    leaves = Leave.objects.filter(user=user, start_date__lte=period_end, end_date__gte=period_start).order_by('-start_date')
    try:
        overtime = Overtime.objects.filter(user=user, date__gte=period_start, date__lte=period_end).order_by('-date')
    except Exception:
        overtime = []

    # compute present_days (unique dates with any punch)
    present_dates = set()
    for log in logs:
        pdate = getattr(log, 'punch_date', None)
        try:
            if hasattr(pdate, 'date'):
                pdate = pdate.date()
        except Exception:
            pass
        if pdate:
            present_dates.add(pdate)
    present_days = len(present_dates)

    # compute overtime totals for this period in Python (robust against DB functions)
    from decimal import Decimal
    overtime_total_hours = Decimal('0.00')
    overtime_total_compensation = Decimal('0.00')
    try:
        for ot in overtime:
            try:
                overtime_total_hours += Decimal(str(ot.hours or '0'))
            except Exception:
                pass
            try:
                overtime_total_compensation += Decimal(str(ot.compensation or '0'))
            except Exception:
                pass
    except Exception:
        overtime_total_hours = Decimal('0.00')
        overtime_total_compensation = Decimal('0.00')

    # unpaid approved leave days still reduce attendance; paid leave is represented
    # as a present biometric check-in and should not be subtracted here.
    leave_days = 0
    try:
        user_leaves = Leave.objects.filter(user=user, status='approved', start_date__lte=period_end, end_date__gte=period_start)
        for lv in user_leaves:
            if lv.leave_type in PAID_LEAVE_TYPES:
                continue
            overlap_start = max(lv.start_date, period_start)
            overlap_end = min(lv.end_date, period_end)
            if overlap_end >= overlap_start:
                leave_days += (overlap_end - overlap_start).days + 1
    except Exception:
        leave_days = 0

    total_days = (period_end - period_start).days + 1
    absent_days = total_days - present_days - leave_days
    if absent_days < 0:
        absent_days = 0

    current_year = date.today().year
    years = list(range(current_year - 2, current_year + 3))
    months = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
    ]

    
    context = {
        'employee': user,
        'logs': logs,
        'leaves': leaves,
        'overtime': overtime,
        'year': year,
        'month': month,
        'present_days': present_days,
        'leave_days': leave_days,
        'absent_days': absent_days,
        'overtime_total_hours': overtime_total_hours,
        'overtime_total_compensation': overtime_total_compensation,
        'total_days': total_days,
        'years': years,
        'months': months,
        'edit_prefill': edit_prefill,
       
    }
    return render(request, 'attendance/employee_attendance_detail.html', context)


@login_required
@hr_admin_required
def edit_overtime_view(request, ot_id):
    """HR-only view to edit an existing Overtime record."""
    ot = get_object_or_404(Overtime, pk=ot_id)
    employee = ot.user
    # preserve picker params if present
    year = request.GET.get('year') or request.POST.get('year')
    month = request.GET.get('month') or request.POST.get('month')

    if request.method == 'POST':
        # parse submitted fields
        ot_date = request.POST.get('overtime_date')
        ot_hours = request.POST.get('overtime_hours')
        ot_reason = request.POST.get('overtime_reason', '')
        ot_comp = request.POST.get('compensation', '')
        try:
            from decimal import Decimal, InvalidOperation
            if not ot_date or not ot_hours:
                messages.error(request, 'Please provide date and hours for overtime.')
            else:
                try:
                    od = date.fromisoformat(ot_date)
                except Exception:
                    messages.error(request, 'Invalid date format.')
                    od = None

                try:
                    hours = Decimal(str(ot_hours).strip().replace(',', '.'))
                except (InvalidOperation, ValueError):
                    messages.error(request, 'Invalid hours value.')
                    hours = None

                comp_val = None
                if ot_comp:
                    try:
                        comp_val = Decimal(str(ot_comp).strip().replace(',', '.'))
                    except Exception:
                        comp_val = None

                if od is not None and hours is not None:
                    if hours < 0 or hours > Decimal('24'):
                        messages.error(request, 'Hours value out of range.')
                    else:
                        # update record
                        try:
                            ot.date = od
                            ot.hours = hours
                            ot.reason = ot_reason
                            if comp_val is not None:
                                ot.compensation = comp_val
                            # save will recalc totals
                            ot.save()
                            messages.success(request, 'Overtime updated.')
                        except Exception:
                            logger.exception('Failed to update overtime')
                            messages.error(request, 'Failed to update overtime.')
        except Exception:
            logger.exception('Unexpected error while updating overtime')
            messages.error(request, 'Unexpected error while updating overtime.')

        # redirect back to employee detail
        redirect_url = f"/attendance/hr/employee/{employee.id}/?"
        if year:
            redirect_url += f'year={year}&'
        if month:
            redirect_url += f'month={month}&'
        return redirect(redirect_url)

    # GET -> render edit form
    context = {
        'ot': ot,
        'employee': employee,
        'year': year,
        'month': month,
    }
    return render(request, 'attendance/edit_overtime.html', context)


# ============================================================================
# ATTENDANCE REQUEST VIEWS (Employee Request + HR Approval Workflow)
# ============================================================================

@login_required
def request_attendance(request):
    """Employee submits an attendance request"""
    today = timezone.localdate()
    
    if request.method == 'POST':
        form = EmployeeAttendanceRequestForm(request.POST)
        if form.is_valid():
            try:
                # Check if request already exists for this date
                existing = AttendanceRequest.objects.filter(
                    user=request.user,
                    request_date=form.cleaned_data['request_date']
                ).first()
                
                if existing:
                    messages.warning(request, f"You already have a {existing.status} request for {form.cleaned_data['request_date']}.")
                    return redirect('attendance:request_attendance')
                
                # Create the request
                attendance_request = form.save(commit=False)
                attendance_request.user = request.user
                attendance_request.save()
                
                messages.success(request, "Attendance request submitted successfully! HR will review it shortly.")
                return redirect('attendance:my_attendance_requests')
            except Exception as e:
                logger.exception('Error creating attendance request')
                messages.error(request, f"Error: {str(e)}")
    else:
        form = EmployeeAttendanceRequestForm()
    
    context = {
        'form': form,
        'today': today,
    }
    return render(request, 'attendance/request_attendance.html', context)


@login_required
def my_attendance_requests(request):
    """Employee views their own attendance requests"""
    requests_list = AttendanceRequest.objects.filter(user=request.user).order_by('-submitted_at')
    approved_count = requests_list.filter(status='approved').count()
    pending_count = requests_list.filter(status='pending').count()
    rejected_count = requests_list.filter(status='rejected').count()

    context = {
        'requests': requests_list,
        'approved_count': approved_count,
        'pending_count': pending_count,
        'rejected_count': rejected_count,
    }
   
    return render(request, 'attendance/my_attendance_requests.html', context)


@hr_admin_required
def pending_attendance_requests(request):
    """HR views all pending attendance requests"""
    pending = AttendanceRequest.objects.filter(status='pending').select_related('user').order_by('-submitted_at')
    
    context = {
        'requests': pending,
    }
    return render(request, 'attendance/pending_attendance_requests.html', context)


@hr_admin_required
def review_attendance_request(request, request_id):
    """HR approves or rejects an attendance request"""
    attendance_request = get_object_or_404(AttendanceRequest, id=request_id)
    
    # Only allow review if still pending
    if attendance_request.status != 'pending':
        messages.warning(request, f"This request has already been {attendance_request.status}.")
        return redirect('attendance:pending_attendance_requests')
    
    if request.method == 'POST':
        form = HRApproveAttendanceRequestForm(request.POST)
        if form.is_valid():
            try:
                action = form.cleaned_data['action']
                
                if action == 'approved':
                    # Create BiometricLog entry to mark attendance
                    BiometricLog.objects.create(
                        employee_id=attendance_request.user.employee_id or attendance_request.user.username,
                        user=attendance_request.user,
                        first_name=attendance_request.user.first_name,
                        department=attendance_request.user.department or 'N/A',
                        punch_date=attendance_request.request_date,
                        punch_time=attendance_request.punch_time.isoformat() if attendance_request.punch_time else '',
                        status='IN',
                        device_id='HR_APPROVED',
                        marked_by_hr=True,
                        hr_reason=attendance_request.reason,
                        marked_by=request.user,
                        marked_at=timezone.now(),
                    )
                    
                    # Update request status
                    attendance_request.status = 'approved'
                    attendance_request.reviewed_by = request.user
                    attendance_request.reviewed_at = timezone.now()
                    attendance_request.save()
                    
                    messages.success(request, f"✓ Attendance request approved for {attendance_request.user.username}.")
                
                elif action == 'rejected':
                    # Update request status with rejection reason
                    attendance_request.status = 'rejected'
                    attendance_request.rejection_reason = form.cleaned_data['rejection_reason']
                    attendance_request.reviewed_by = request.user
                    attendance_request.reviewed_at = timezone.now()
                    attendance_request.save()
                    
                    messages.success(request, f"✗ Attendance request rejected for {attendance_request.user.username}.")
                
                return redirect('attendance:pending_attendance_requests')
            
            except Exception as e:
                logger.exception('Error reviewing attendance request')
                messages.error(request, f"Error: {str(e)}")
    else:
        form = HRApproveAttendanceRequestForm()
    
    context = {
        'attendance_request': attendance_request,
        'form': form,
    }
    return render(request, 'attendance/review_attendance_request.html', context)

