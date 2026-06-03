from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.http import JsonResponse, HttpResponse
import datetime
from .forms import AdvanceSalaryRequestForm, ApproveAdvanceSalaryForm
from .models import EmployeePayrollDetails, AdvanceSalaryRequest, GeneratePayroll
from attendance.models import LeaveQuota
from accounts.models import User, EmployeeProfile, TaxInfo, BankingInfo
from accounts.decorators import hr_admin_required
from django.contrib.auth import get_user_model
from django.db.models import Q
import calendar as _calendar
from .utils import use_payroll_dashboard

# Create your views here.
@login_required
def advance_salary_request_view(request):
    # show form and user's requests
    if request.method == 'POST':
        form = AdvanceSalaryRequestForm(request.POST)
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                obj.user = request.user
                obj.save()
                messages.success(request, 'Advance salary request submitted successfully.')
                return redirect('payroll:advance_salary_request')
            except Exception as e:
                messages.error(request, f'Failed to submit request: {e}')
    else:
        form = AdvanceSalaryRequestForm()

    requests_qs = AdvanceSalaryRequest.objects.filter(user=request.user).order_by('-request_date')
    return render(request, 'payroll/advance_salary_requestform.html', {
        'advancesalaryrequestform': form,
        'advancesalaryrequestlist': requests_qs,
    })


@login_required
@hr_admin_required
def hr_requests_list(request):
    # default to 'all' so HR sees all requests by default
    status = request.GET.get('status', 'all')
    # Support sorting by related user fields via ?sort=name or ?sort=-name or ?sort=id or ?sort=-id
    sort = request.GET.get('sort')

    if status == 'all':
        qs = AdvanceSalaryRequest.objects.all()
    else:
        qs = AdvanceSalaryRequest.objects.filter(status=status)

    # Search query (filter by user name, username or employee_id)
    q = request.GET.get('q', '')
    if q:
        q = q.strip()
        if q:
            try:
                qs = qs.filter(
                    Q(user__first_name__icontains=q) |
                    Q(user__last_name__icontains=q) |
                    Q(user__username__icontains=q) |
                    Q(user__employee_id__icontains=q)
                )
            except Exception:
                # If backend doesn't support related-field queries in some cases,
                # fall back to a no-op (keep original qs).
                pass

    # Default ordering
    order_by_arg = '-request_date'

    # Map friendly sort keys to ORM ordering expressions
    if sort:
        # normalize and allow descending with leading '-'
        desc = sort.startswith('-')
        key = sort[1:] if desc else sort
        if key == 'name':
            # order by first_name then last_name then username
            order_by_arg = ('-user__first_name', '-user__last_name', '-user__username') if desc else ('user__first_name', 'user__last_name', 'user__username')
        elif key == 'id':
            order_by_arg = ('-user__employee_id',) if desc else ('user__employee_id',)
        else:
            # unknown sort key - fall back to request_date
            order_by_arg = '-request_date'

    # Apply ordering (handle tuple or single)
    try:
        if isinstance(order_by_arg, (list, tuple)):
            qs = qs.order_by(*order_by_arg)
        else:
            qs = qs.order_by(order_by_arg)
    except Exception:
        # In case related-field ordering isn't supported by backend, fall back
        qs = qs.order_by('-request_date')
    return render(request, 'payroll/hr_requests_list.html', {
        'requests': qs,
        'status': status,
        'sort': sort,
        'q': q,
    })




@login_required
@hr_admin_required
@require_http_methods(['POST'])
def approve_request(request, request_id):
    req = get_object_or_404(AdvanceSalaryRequest, id=request_id)
    try:
        # Ensure amount is a proper Decimal (clean common unicode characters)
        amt = req.amount
        if not isinstance(amt, Decimal):
            try:
                # normalize to string and remove unicode quotes and commas
                s = str(amt)
                s = s.replace('\u201c', '"').replace('\u201d', '"')
                s = s.replace('"', '').replace(',', '')
                s = s.strip()
                req.amount = Decimal(s)
            except (InvalidOperation, TypeError) as conv_err:
                messages.error(request, f'Invalid stored amount for request #{req.id}: {conv_err}')
                return redirect('payroll:hr_requests_list')

        req.status = 'approved'
        req.decision_date = timezone.now()
        # record who approved
        try:
            req.approver = request.user
        except Exception:
            # if approver cannot be set, continue and save without approver
            pass
        req.save()
        req.refresh_from_db()
        messages.success(request, f'Request #{req.id} updated to {req.get_status_display()}.')
    except Exception as e:
        messages.error(request, f'Failed to approve request: {e}')
    return redirect('payroll:hr_requests_list')



@login_required
@hr_admin_required
@require_http_methods(['POST'])
def reject_request(request, request_id):
    req = get_object_or_404(AdvanceSalaryRequest, id=request_id)
    try:
        # Ensure amount is a proper Decimal before saving
        amt = req.amount
        if not isinstance(amt, Decimal):
            try:
                s = str(amt)
                s = s.replace('\u201c', '"').replace('\u201d', '"')
                s = s.replace('"', '').replace(',', '')
                s = s.strip()
                req.amount = Decimal(s)
            except (InvalidOperation, TypeError) as conv_err:
                messages.error(request, f'Invalid stored amount for request #{req.id}: {conv_err}')
                return redirect('payroll:hr_requests_list')

        req.status = 'rejected'
        req.decision_date = timezone.now()
        # record who rejected
        try:
            req.approver = request.user
        except Exception:
            pass
        req.save()
        req.refresh_from_db()
        messages.success(request, f'Request #{req.id} rejected.')
    except Exception as e:
        messages.error(request, f'Failed to reject request: {e}')
    return redirect('payroll:hr_requests_list')



@login_required
def advance_request_status(request, request_id):
    req = get_object_or_404(AdvanceSalaryRequest, id=request_id)
    return render(request, 'payroll/advance_salary_status.html', {'request_obj': req})





@login_required
def user_payroll_dashboard(request):
    # Pass empty-string for month/year by default so the helper does not
    # apply month/year filtering and returns all generated payrolls for the user.
    params = {
        'month': request.GET.get('month', ''),
        'year': request.GET.get('year', ''),
        'status': request.GET.get('status'),
        'q': request.GET.get('q'),
        'sort': request.GET.get('sort'),
    }
    ctx = use_payroll_dashboard(request.user, for_hr=False, params=params)

    # derive the single user's latest payroll (if any)
    try:
        payrolls_qs = ctx.get('payrolls')
        if payrolls_qs is not None:
            try:
                latest = payrolls_qs.first()
            except Exception:
                # If it's not a queryset but a list-like, pick first element
                try:
                    latest = payrolls_qs[0] if len(payrolls_qs) > 0 else None
                except Exception:
                    latest = None
        else:
            latest = None
    except Exception:
        latest = None

    ctx.update({'user_payroll_dashboard': latest})
    return render(request, 'payroll/user_payroll_dashboard.html', ctx)



@login_required
@hr_admin_required
def hr_payroll_dashboard(request):
    params = {
        'month': request.GET.get('month'),
        'year': request.GET.get('year'),
        'status': request.GET.get('status'),
        'q': request.GET.get('q'),
        'sort': request.GET.get('sort'),
    }
    ctx = use_payroll_dashboard(request.user, for_hr=True, params=params)

    payroll_details = ctx.get('payrolls')
    # Build a context for the template; include other generated keys as well
    context = {
        'payroll_details': payroll_details,
    }
    # merge other keys from ctx except the `payrolls` key we've already mapped
    for k, v in ctx.items():
        if k == 'payrolls':
            continue
        context[k] = v

    return render(request, 'payroll/hr_payroll_dashboard.html', context)



@login_required
@hr_admin_required
def list_employee_payrolls(request):
    payrolls_qs = EmployeePayrollDetails.objects.all().order_by('-id')

    def _format_amount(value):
        """Format Decimal/number like '7.04' or '8000' (strip unnecessary .00)."""
        if value is None:
            return ''
        try:
            d = Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            try:
                return str(value)
            except Exception:
                return ''

        s = format(d, 'f')
        if '.' in s:
            s = s.rstrip('0').rstrip('.')
        return s

    # Attach a display string to each payroll instance for template rendering
    for p in payrolls_qs:
        amt = None
        try:
            amt = getattr(p, 'basic_salary', None)
        except Exception:
            amt = None

        if amt is None:
            try:
                profile = getattr(p.user, 'employeeprofile', None)
                if profile is not None:
                    amt = getattr(profile, 'ctc', None)
            except Exception:
                amt = None

        if amt is None:
            p.amount_display = '-'
        else:
            formatted = _format_amount(amt)
            p.amount_display = f'₹{formatted}' if formatted != '' else '-'

    # --- GeneratePayroll filtering ---
    from .models import GeneratePayroll

    gen_qs = GeneratePayroll.objects.all().order_by('-year', '-month')
    # read filters from query params
    month = request.GET.get('month')
    year = request.GET.get('year')
    status = request.GET.get('status')

    # default to current month/year only when the parameter is completely
    # missing (None). If the parameter is present but empty string (""),
    # treat that as the user's "All" selection and do not apply the filter.
    today = datetime.date.today()
    if month is None:
        month = str(today.month)
    if year is None:
        year = str(today.year)

    try:
        gen_qs = gen_qs.filter(month=int(month))
    except Exception:
        pass

    try:
        gen_qs = gen_qs.filter(year=int(year))
    except Exception:
        pass

    if status:
        gen_qs = gen_qs.filter(status__iexact=status)

    # helper lists for template selects
    months_list = [str(i) for i in range(1, 13)]
    now_year = datetime.date.today().year
    years_list = [str(y) for y in range(now_year - 10, now_year + 1)]
    statuses = list(GeneratePayroll.objects.order_by().values_list('status', flat=True).distinct())

    context = {
        'payrolls': payrolls_qs,
        'generate_payrolls': gen_qs,
        'filter_month': month or '',
        'filter_year': year or '',
        'filter_status': status or '',
        'months_list': months_list,
        'years_list': years_list,
        'statuses_list': statuses,
    }
    return render(request, 'payroll/employee_payroll_list.html', context)




@login_required
@hr_admin_required
def generate_payroll(request, payroll_id):
    """Show a form prefilled from EmployeePayrollDetails (payroll_id) and on POST create a GeneratePayroll record."""
    try:
        details = EmployeePayrollDetails.objects.get(id=payroll_id)
    except EmployeePayrollDetails.DoesNotExist:
        messages.error(request, 'Payroll details not found.')
        return redirect('payroll:employee_payroll_list')
 
    # Ensure these variables exist for all code paths (prevents UnboundLocalError
    # when an exception occurs before they are assigned later).
    present_days_ui = 0
    absent_days_ui = 0
    paid_leave_days = 0
    present = 0               # number of biometric-present days (debug/display)
    present_days = 0          # used by POST branch for persisted value
    absent_days = 0           # used by POST branch for persisted value

    # Helper to convert potential BSON Decimal128, Decimal, float or string
    # into a Python Decimal for arithmetic and safe storage.
    def _to_decimal(val, default=Decimal('0')):
        if val is None:
            return default
        try:
            from bson.decimal128 import Decimal128 as BsonDecimal128
        except Exception:
            BsonDecimal128 = None

        try:
            if BsonDecimal128 and isinstance(val, BsonDecimal128):
                return val.to_decimal()
            if isinstance(val, Decimal):
                return val
            return Decimal(str(val))
        except Exception:
            try:
                return Decimal(str(val))
            except Exception:
                return default

    if request.method == 'GET':
        # Prefill context with details
        initial = {
            'user': details.user,
            'basic_salary': details.basic_salary,
            'hra': details.hra,
            # For fields that should default to zero when absent, ensure 0 is used
            'special_allowances': details.special_allowances if details.special_allowances is not None else Decimal('0'),
            'conveyance_allowances': details.conveyance_allowances if details.conveyance_allowances is not None else Decimal('0'),
            'fooding_allowance': details.fooding_allowance if getattr(details, 'fooding_allowance', None) is not None else Decimal('0'),
            'medical_allowance': details.medical_allowance if getattr(details, 'medical_allowance', None) is not None else Decimal('0'),
            'education_allowance': details.education_allowance if getattr(details, 'education_allowance', None) is not None else Decimal('0'),
            'transport_allowance': details.transport_allowance if getattr(details, 'transport_allowance', None) is not None else Decimal('0'),
            'epf_contribution': details.epf_contribution if details.epf_contribution is not None else Decimal('0'),
            'esi_contribution': details.esi_contribution if details.esi_contribution is not None else Decimal('0'),
            'professional_tax': details.professional_tax if details.professional_tax is not None else Decimal('0'),
            'tds': details.tds if details.tds is not None else Decimal('0'),
            # Default month/year to query params or today
            'month': request.GET.get('month', str(datetime.date.today().month)),
            'year': request.GET.get('year', str(datetime.date.today().year)),
            # Default status to Paid for generated payroll; user can change via selector
            'status': request.GET.get('status', 'Paid'),
        }

        # Provide select lists for month/year/status in the template
        months_list = [str(i) for i in range(1, 13)]
        now_year = datetime.date.today().year
        try:
            years_qs = GeneratePayroll.objects.order_by().values_list('year', flat=True).distinct()
            years_nums = [int(y) for y in years_qs if y is not None]
            if years_nums:
                min_year = min(min(years_nums), now_year - 10)
                max_year = max(max(years_nums), now_year + 10)
            else:
                min_year = now_year - 10
                max_year = now_year + 10
        except Exception:
            min_year = now_year - 10
            max_year = now_year + 10

        years_list = [str(y) for y in range(min_year, max_year + 1)]
        statuses_list = list(GeneratePayroll.objects.order_by().values_list('status', flat=True).distinct())
        if not statuses_list:
            statuses_list = ['Paid', 'Not Paid']

        # reuse helper defined above
        total_earnings = None
        total_deductions = None
        net_pay = None

        # determine selected month/year (from initial) and ensure safe defaults
        try:
            sel_month = int(initial.get('month'))
            sel_year = int(initial.get('year'))
        except Exception:
            sel_month = datetime.date.today().month
            sel_year = datetime.date.today().year

        # compute present/paid-leave days for the selected month/year
        try:
            from attendance.models import BiometricLog, Leave as AttendanceLeave
            from django.db.models import Q
            import calendar as _calendar
            from datetime import date as _date, timedelta as _td

            # days in selected month
            days_in_month_sel = _calendar.monthrange(sel_year, sel_month)[1]
            period_start = _date(sel_year, sel_month, 1)
            today_dt = datetime.date.today()
            if sel_year == today_dt.year and sel_month == today_dt.month:
                period_end = today_dt
            else:
                period_end = _date(sel_year, sel_month, days_in_month_sel)

            total_days_ui = (period_end - period_start).days + 1

            emp_id = getattr(details.user, 'employee_id', None)
            # fetch IN punch dates in the period
            try:
                logs_qs = BiometricLog.objects.filter(
                    Q(user=details.user) | Q(employee_id=emp_id),
                    punch_date__gte=period_start,
                    punch_date__lte=period_end,
                    status='0'
                ).values_list('punch_date', flat=True)
                punch_dates = list(logs_qs)
                present_dates = set()
                for pd in punch_dates:
                    try:
                        if pd is None:
                            continue
                        if hasattr(pd, 'date'):
                            pd = pd.date()
                        if pd:
                            present_dates.add(pd)
                    except Exception:
                        continue
            except Exception:
                present_dates = set()

            # collect approved paid leave dates overlapping the period
            paid_leave_dates = set()
            try:
                paid_qs = AttendanceLeave.objects.filter(
                    user=details.user,
                    status='approved',
                    leave_type='paid',
                    start_date__lte=period_end,
                    end_date__gte=period_start,
                )
                for lv in paid_qs:
                    try:
                        overlap_start = max(lv.start_date, period_start)
                        overlap_end = min(lv.end_date, period_end)
                        if overlap_end >= overlap_start:
                            for i in range((overlap_end - overlap_start).days + 1):
                                paid_leave_dates.add(overlap_start + _td(days=i))
                    except Exception:
                        continue
            except Exception:
                paid_leave_dates = set()

            # present = unique biometric punch days U paid leave dates
            present_union = present_dates.union(paid_leave_dates)
            present_days_ui = len(present_union)
            present = len(present_dates)
            paid_leave_days = len(paid_leave_dates)

            if present_days_ui > total_days_ui:
                present_days_ui = total_days_ui
            absent_days_ui = total_days_ui - present_days_ui
            if absent_days_ui < 0:
                absent_days_ui = 0

            # compute prorated basic and other components (safe Decimal math)
            try:
                days_in_month_sel_int = int(days_in_month_sel)
            except Exception:
                days_in_month_sel_int = 0

            try:
                full_basic = _to_decimal(details.basic_salary)
                if days_in_month_sel_int > 0:
                    prorated_basic = (full_basic / Decimal(days_in_month_sel_int)) * Decimal(present_days_ui)
                    prorated_basic = prorated_basic.quantize(Decimal('0.01'))
                else:
                    prorated_basic = full_basic
            except Exception:
                prorated_basic = _to_decimal(details.basic_salary)

            try:
                if days_in_month_sel_int > 0:
                    prorate_ratio = (Decimal(present_days_ui) / Decimal(days_in_month_sel_int))
                else:
                    prorate_ratio = Decimal('1')
            except Exception:
                prorate_ratio = Decimal('1')

            def _prorate_field(attr_name, fallback):
                try:
                    full = _to_decimal(getattr(details, attr_name, fallback))
                    return (full * prorate_ratio).quantize(Decimal('0.01'))
                except Exception:
                    try:
                        return _to_decimal(getattr(details, attr_name, fallback))
                    except Exception:
                        return _to_decimal(fallback)

            prorated_hra = _prorate_field('hra', initial.get('hra'))
            prorated_special_allowances = _prorate_field('special_allowances', initial.get('special_allowances'))
            prorated_conveyance_allowances = _prorate_field('conveyance_allowances', initial.get('conveyance_allowances'))
            prorated_fooding_allowance = _prorate_field('fooding_allowance', initial.get('fooding_allowance'))
            prorated_medical_allowance = _prorate_field('medical_allowance', initial.get('medical_allowance'))
            prorated_education_allowance = _prorate_field('education_allowance', initial.get('education_allowance'))
            prorated_transport_allowance = _prorate_field('transport_allowance', initial.get('transport_allowance'))
            prorated_epf_contribution = _prorate_field('epf_contribution', initial.get('epf_contribution'))
            prorated_esi_contribution = _prorate_field('esi_contribution', initial.get('esi_contribution'))
            prorated_professional_tax = _prorate_field('professional_tax', initial.get('professional_tax'))
            prorated_tds = _prorate_field('tds', initial.get('tds'))

            # compute totals for display using full monthly amounts (do not change Payroll Details)
            try:
                full_basic_for_display = _to_decimal(details.basic_salary)
            except Exception:
                full_basic_for_display = _to_decimal(initial.get('basic_salary'))

            total_earnings = (
                full_basic_for_display +
                _to_decimal(initial.get('hra')) +
                _to_decimal(initial.get('special_allowances')) +
                _to_decimal(initial.get('conveyance_allowances')) +
                _to_decimal(initial.get('fooding_allowance')) +
                _to_decimal(initial.get('medical_allowance')) +
                _to_decimal(initial.get('education_allowance')) +
                _to_decimal(initial.get('transport_allowance'))
            )
            total_deductions = (
                _to_decimal(initial.get('epf_contribution')) +
                _to_decimal(initial.get('esi_contribution')) +
                _to_decimal(initial.get('professional_tax')) +
                _to_decimal(initial.get('tds'))
            )
            net_pay = total_earnings - total_deductions

        except Exception:
            # fallback safe defaults
            present_days_ui = 0
            absent_days_ui = 0
            paid_leave_days = 0
            prorated_basic = _to_decimal(details.basic_salary)
            prorated_hra = _to_decimal(initial.get('hra'))
            prorated_special_allowances = _to_decimal(initial.get('special_allowances'))
            prorated_conveyance_allowances = _to_decimal(initial.get('conveyance_allowances'))
            prorated_epf_contribution = _to_decimal(initial.get('epf_contribution'))
            prorated_esi_contribution = _to_decimal(initial.get('esi_contribution'))
            prorated_professional_tax = _to_decimal(initial.get('professional_tax'))
            prorated_tds = _to_decimal(initial.get('tds'))
            total_earnings = _to_decimal(initial.get('basic_salary')) + _to_decimal(initial.get('hra'))
            total_deductions = _to_decimal(initial.get('epf_contribution')) + _to_decimal(initial.get('tds'))
            net_pay = total_earnings - total_deductions

        return render(request, 'payroll/generate_payroll.html', {
            'initial': initial,
            'details': details,
            'months_list': months_list,
            'years_list': years_list,
            'statuses_list': statuses_list,
            'total_earnings': total_earnings,
            'total_deductions': total_deductions,
            'net_pay': net_pay,
            'present_days': present_days_ui,
            'absent_days': absent_days_ui,
            'paid_leave_days': paid_leave_days,
            'prorated_basic': prorated_basic,
            'prorated_hra': prorated_hra,
            'prorated_special_allowances': prorated_special_allowances,
            'prorated_conveyance_allowances': prorated_conveyance_allowances,
            'prorated_fooding_allowance': prorated_fooding_allowance,
            'prorated_medical_allowance': prorated_medical_allowance,
            'prorated_education_allowance': prorated_education_allowance,
            'prorated_transport_allowance': prorated_transport_allowance,
            'prorated_epf_contribution': prorated_epf_contribution,
            'prorated_esi_contribution': prorated_esi_contribution,
            'prorated_professional_tax': prorated_professional_tax,
            'prorated_tds': prorated_tds,
            'present': present,
        })

    
    # Handle POST: create GeneratePayroll from submitted (or prefilled) values
    if request.method == 'POST':
        month = request.POST.get('month')
        year = request.POST.get('year')
        try:
            month_i = int(month)
            year_i = int(year)
        except Exception:
            messages.error(request, 'Invalid month or year.')
            return redirect('payroll:generate_payroll', payroll_id=payroll_id)

        # Prevent duplicate for this user/month/year
        # Use `user_id` in the query to avoid djongo/sqlparse recursion issues
        from django.db import DatabaseError
        try:
            user_pk = getattr(details.user, 'id', None)
            exists = GeneratePayroll.objects.filter(user_id=user_pk, month=month_i, year=year_i).exists()
        except DatabaseError:
            # Fallback: query by month/year and check user id in Python to avoid SQL parsing
            try:
                user_pk = getattr(details.user, 'id', None)
                candidates = GeneratePayroll.objects.filter(month=month_i, year=year_i)
                exists = any((getattr(c, 'user_id', None) == user_pk) or (getattr(getattr(c, 'user', None), 'id', None) == user_pk) for c in candidates)
            except Exception:
                exists = False

        if exists:
            messages.error(request, 'Payroll already generated for this employee for this month.')
            return redirect('payroll:employee_payroll_list')

        # Read amounts from POST but fallback to details
        def _v(field):
            val = request.POST.get(field)
            return val if val not in (None, '') else getattr(details, field, None)

        # compute present/absent for the payroll month (POST-time) so we store accurate values
        try:
            from attendance.models import BiometricLog, Leave as AttendanceLeave
            from django.db.models import Q
            import calendar as _calendar
            from datetime import date as _date, timedelta as _td

            days_in_month_post = _calendar.monthrange(year_i, month_i)[1]
            period_start = _date(year_i, month_i, 1)
            today_dt = datetime.date.today()
            if year_i == today_dt.year and month_i == today_dt.month:
                period_end = today_dt
            else:
                period_end = _date(year_i, month_i, days_in_month_post)

            # unique IN punch dates
            emp_id = getattr(details.user, 'employee_id', None)
            try:
                logs_qs = BiometricLog.objects.filter(
                    Q(user=details.user) | Q(employee_id=emp_id),
                    punch_date__gte=period_start,
                    punch_date__lte=period_end,
                    status='0'
                ).values_list('punch_date', flat=True)
                punch_dates = list(logs_qs)
                present_dates = set()
                for pd in punch_dates:
                    try:
                        if pd is None:
                            continue
                        if hasattr(pd, 'date'):
                            pd = pd.date()
                        if pd:
                            present_dates.add(pd)
                    except Exception:
                        pass
            except Exception:
                present_dates = set()

            # approved leave days overlapping the period: collect paid/unpaid date-sets
            paid_leave_dates = set()
            unpaid_leave_dates = set()
            try:
                paid_qs = AttendanceLeave.objects.filter(
                    user=details.user,
                    status='approved',
                    leave_type='paid',
                    start_date__lte=period_end,
                    end_date__gte=period_start,
                )
                for lv in paid_qs:
                    try:
                        overlap_start = max(lv.start_date, period_start)
                        overlap_end = min(lv.end_date, period_end)
                        if overlap_end >= overlap_start:
                            for i in range((overlap_end - overlap_start).days + 1):
                                paid_leave_dates.add(overlap_start + _td(days=i))
                    except Exception:
                        continue
            except Exception:
                paid_leave_dates = set()

            try:
                unpaid_qs = AttendanceLeave.objects.filter(
                    user=details.user,
                    status='approved',
                    leave_type='unpaid',
                    start_date__lte=period_end,
                    end_date__gte=period_start,
                )
                for lv in unpaid_qs:
                    try:
                        overlap_start = max(lv.start_date, period_start)
                        overlap_end = min(lv.end_date, period_end)
                        if overlap_end >= overlap_start:
                            for i in range((overlap_end - overlap_start).days + 1):
                                unpaid_leave_dates.add(overlap_start + _td(days=i))
                    except Exception:
                        continue
            except Exception:
                unpaid_leave_dates = set()

            total_days_post = (period_end - period_start).days + 1
            # present includes biometric distinct punch days plus paid leave days (deduplicated)
            present_days = len(present_dates.union(paid_leave_dates))
            # absent subtract unpaid leaves only (paid leaves are counted as present)
            absent_days = total_days_post - present_days - len(unpaid_leave_dates)
            if absent_days < 0:
                absent_days = 0
        except Exception:
            present_days = 0
            absent_days = 0

        # compute prorated basic salary for POST if no basic_salary submitted
        try:
            days_in_month_post = int(days_in_month_post) if 'days_in_month_post' in locals() else int(_calendar.monthrange(year_i, month_i)[1])
        except Exception:
            days_in_month_post = 0

        try:
            full_basic_post = _to_decimal(details.basic_salary)
            if days_in_month_post > 0:
                prorated_basic_post = (full_basic_post / Decimal(days_in_month_post)) * Decimal(present_days)
                prorated_basic_post = prorated_basic_post.quantize(Decimal('0.01'))
            else:
                prorated_basic_post = full_basic_post
        except Exception:
            prorated_basic_post = _to_decimal(details.basic_salary)

        try:
            # Allow the form to supply a status (default to 'Paid')
            status_post = request.POST.get('status', 'Paid') or 'Paid'
            # if user didn't post a basic_salary, use prorated_basic_post
            posted_basic = request.POST.get('basic_salary')
            if posted_basic is None or posted_basic == '':
                basic_to_save = prorated_basic_post
            else:
                basic_to_save = posted_basic

            new = GeneratePayroll.objects.create(
                user=details.user,
                generated_by=request.user,
                month=month_i,
                year=year_i,
                basic_salary=_to_decimal(basic_to_save),
                hra=_to_decimal(_v('hra')),
                special_allowances=_to_decimal(_v('special_allowances')),
                conveyance_allowances=_to_decimal(_v('conveyance_allowances')),
                fooding_allowance=_to_decimal(_v('fooding_allowance')),
                medical_allowance=_to_decimal(_v('medical_allowance')),
                education_allowance=_to_decimal(_v('education_allowance')),
                transport_allowance=_to_decimal(_v('transport_allowance')),
                epf_contribution=_to_decimal(_v('epf_contribution')),
                esi_contribution=_to_decimal(_v('esi_contribution')),
                professional_tax=_to_decimal(_v('professional_tax')),
                tds=_to_decimal(_v('tds')),
                bonuses=_to_decimal(_v('bonuses')),
                advance_adjustment=_to_decimal(_v('advance_adjustment')),
                present_days=present_days,
                absent_days=absent_days,
                overtime_hours=_to_decimal(_v('overtime_hours') or '0'),
                overtime_compensation=_to_decimal(_v('overtime_compensation') or '0'),
                status=status_post,
            )
            messages.success(request, f'Payroll generated for {month_i}/{year_i} for {details.user.username}.')
        except Exception as e:
            messages.error(request, f'Failed to create payroll: {e}')
 
        return redirect('payroll:employee_payroll_list')


@login_required
@hr_admin_required
def overtime_for_month(request):
    """Return JSON with overtime totals for a given user for the provided month/year.

    Query params: user_id, month, year
    Response: {hours: "12.50", compensation: "1250.00"}
    """
    from attendance.models import Overtime
    from decimal import Decimal
    try:
        user_id = int(request.GET.get('user_id'))
    except Exception:
        return JsonResponse({'error': 'missing or invalid user_id'}, status=400)

    try:
        month = int(request.GET.get('month'))
        year = int(request.GET.get('year'))
    except Exception:
        return JsonResponse({'error': 'missing or invalid month/year'}, status=400)

    try:
        from datetime import date as _date
        start = _date(year, month, 1)
        if month == 12:
            end = _date(year + 1, 1, 1)
        else:
            end = _date(year, month + 1, 1)

        qs = Overtime.objects.filter(user_id=user_id, date__gte=start, date__lt=end)
        sum_hours = Decimal('0.00')
        sum_comp = Decimal('0.00')
        for h, c in qs.values_list('hours', 'compensation'):
            try:
                sum_hours += Decimal(str(h or '0'))
            except Exception:
                pass
            try:
                sum_comp += Decimal(str(c or '0'))
            except Exception:
                pass

        # Format as string to preserve decimal precision in JSON
        return JsonResponse({'hours': str(sum_hours), 'compensation': str(sum_comp)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def present_absent_for_month(request):
    """Return JSON with present/absent/leave/total days for a user for a given month/year.

    Query params: user_id, month, year
    Response: {present_days: 10, absent_days: 2, leave_days: 1, total_days: 13}
    """
    try:
        user_id = int(request.GET.get('user_id'))
    except Exception:
        return JsonResponse({'error': 'missing or invalid user_id'}, status=400)

    try:
        month = int(request.GET.get('month'))
        year = int(request.GET.get('year'))
    except Exception:
        return JsonResponse({'error': 'missing or invalid month/year'}, status=400)

    try:
        from attendance.models import BiometricLog, Leave as AttendanceLeave
        from datetime import date as _date, timedelta as _td
        import calendar as _calendar
        from django.db.models import Q

        start = _date(year, month, 1)
        days_in_month = _calendar.monthrange(year, month)[1]
        # if current month, end at today; otherwise end at month end
        today_dt = datetime.date.today()
        if year == today_dt.year and month == today_dt.month:
            end = today_dt
        else:
            end = _date(year, month, days_in_month)

        total_days = (end - start).days + 1

        # unique IN punch dates for the user (or employee_id)
        try:
            punch_qs = BiometricLog.objects.filter(
                Q(user_id=user_id) | Q(employee_id=getattr(get_user_model().objects.filter(id=user_id).first(), 'employee_id', None)),
                punch_date__gte=start,
                punch_date__lte=end,
                status__in=['0', 'IN']
            ).values_list('punch_date', flat=True)
            punch_dates = list(punch_qs)
            present_dates = set()
            for pd in punch_dates:
                try:
                    if pd is None:
                        continue
                    if hasattr(pd, 'date'):
                        pd = pd.date()
                    if pd:
                        present_dates.add(pd)
                except Exception:
                    continue
        except Exception:
            present_dates = set()

        # Collect paid and unpaid leave dates as explicit per-day sets to avoid double-counting
        paid_leave_dates = set()
        unpaid_leave_dates = set()
        try:
            paid_qs = AttendanceLeave.objects.filter(
                user_id=user_id,
                status='approved',
                leave_type='paid',
                start_date__lte=end,
                end_date__gte=start,
            )
            for lv in paid_qs:
                try:
                    overlap_start = max(lv.start_date, start)
                    overlap_end = min(lv.end_date, end)
                    if overlap_end >= overlap_start:
                        for i in range((overlap_end - overlap_start).days + 1):
                            paid_leave_dates.add(overlap_start + _td(days=i))
                except Exception:
                    continue
        except Exception:
            paid_leave_dates = set()

        try:
            unpaid_qs = AttendanceLeave.objects.filter(
                user_id=user_id,
                status='approved',
                leave_type='unpaid',
                start_date__lte=end,
                end_date__gte=start,
            )
            for lv in unpaid_qs:
                try:
                    overlap_start = max(lv.start_date, start)
                    overlap_end = min(lv.end_date, end)
                    if overlap_end >= overlap_start:
                        for i in range((overlap_end - overlap_start).days + 1):
                            unpaid_leave_dates.add(overlap_start + _td(days=i))
                except Exception:
                    continue
        except Exception:
            unpaid_leave_dates = set()

        # present includes unique punch days U paid leave dates (deduplicated)
        present_days = len(present_dates.union(paid_leave_dates))

        # absent subtract unpaid leave days only (paid leaves counted as present)
        absent_days = total_days - present_days - len(unpaid_leave_dates)
        if absent_days < 0:
            absent_days = 0

        # total leave days (paid + unpaid)
        try:
            leave_days = len(paid_leave_dates) + len(unpaid_leave_dates)
        except Exception:
            leave_days = 0

        return JsonResponse({'present_days': present_days, 'absent_days': absent_days, 'leave_days': leave_days, 'total_days': total_days})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def salary_slip_view(request):
    return render(request, 'payroll/salary_slip.html')


@login_required
def salary_slip_download(request, gen_id):
    """Return a salary slip for a generated payroll as a download.

    Attempts to create a PDF using ReportLab if available. If ReportLab
    isn't installed, returns an HTML attachment so the browser will
    download the rendered slip.
    """
    try:
        gen = GeneratePayroll.objects.get(id=gen_id)
    except GeneratePayroll.DoesNotExist:
        messages.error(request, 'Generated payroll not found.')
        return redirect('payroll:employee_payroll_list')

    # Permission: HR admins or the payroll generator or the user themselves
    user = request.user
    if not (user.is_hr_admin() or user == gen.generated_by or user == gen.user):
        messages.error(request, 'You do not have permission to download this salary slip.')
        return redirect('payroll:employee_payroll_list')

    # Build a template-friendly context from the generated payroll and related objects
    def _fmt(v):
        try:
            return str(v)
        except Exception:
            return ''

    user_obj = gen.user
    # try to get tax/banking/profile info safely
    try:
        tax = getattr(user_obj, 'taxinfo', None)
    except Exception:
        tax = None
    try:
        bank = getattr(user_obj, 'bankinginfo', None)
    except Exception:
        bank = None
    try:
        profile = getattr(user_obj, 'employeeprofile', None)
    except Exception:
        profile = None

    month = gen.month
    year = gen.year
    # Show month as English name (e.g., 12 -> December) for the template
    try:
        month_display = _calendar.month_name[int(month)] if month is not None else ''
    except Exception:
        try:
            month_display = str(int(month))
        except Exception:
            month_display = str(month or '')
    # Normalize numeric fields (handle bson.decimal128.Decimal128) before arithmetic
    def _to_decimal_local(v):
        try:
            from bson.decimal128 import Decimal128 as BsonDecimal128
        except Exception:
            BsonDecimal128 = None
        try:
            if v is None:
                return Decimal('0')
            if BsonDecimal128 and isinstance(v, BsonDecimal128):
                return v.to_decimal()
            if isinstance(v, Decimal):
                return v
            return Decimal(str(v))
        except Exception:
            try:
                return Decimal(str(v))
            except Exception:
                return Decimal('0')

    basic_d = _to_decimal_local(getattr(gen, 'basic_salary', None))
    hra_d = _to_decimal_local(getattr(gen, 'hra', None))
    special_d = _to_decimal_local(getattr(gen, 'special_allowances', None))
    convey_d = _to_decimal_local(getattr(gen, 'conveyance_allowances', None))
    food_d = _to_decimal_local(getattr(gen, 'fooding_allowance', None))
    medical_d = _to_decimal_local(getattr(gen, 'medical_allowance', None))
    education_d = _to_decimal_local(getattr(gen, 'education_allowance', None))
    transport_d = _to_decimal_local(getattr(gen, 'transport_allowance', None))
    bonus_d = _to_decimal_local(getattr(gen, 'bonuses', None))

    epf_d = _to_decimal_local(getattr(gen, 'epf_contribution', None))
    esi_d = _to_decimal_local(getattr(gen, 'esi_contribution', None))
    prof_tax_d = _to_decimal_local(getattr(gen, 'professional_tax', None))
    tds_d = _to_decimal_local(getattr(gen, 'tds', None))
    advance_adj_d = _to_decimal_local(getattr(gen, 'advance_adjustment', None))

    total_earning = basic_d + hra_d + special_d + convey_d + food_d + medical_d + education_d + transport_d + bonus_d
    total_deduction = epf_d + esi_d + prof_tax_d + tds_d + advance_adj_d
    # Round net salary to nearest rupee (rounded off)
    try:
        net_salary = (total_earning - total_deduction).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    except Exception:
        net_salary = total_earning - total_deduction
    # Convert net salary to words using num2words if available
    amount_in_words = ''
    try:
        from num2words import num2words
        amount_in_words = num2words(int(net_salary), to='cardinal', lang='en_IN').title() + ' Only'
    except Exception:
        amount_in_words = ''
    
    tmpl_ctx = {
        'month': month_display,
        'year': year,
        'project_name': _fmt(getattr(user_obj, 'project_name', '')),
        'emp_code': _fmt(getattr(user_obj, 'employee_id', '')),
        'emp_name': user_obj.get_full_name() or user_obj.username,
        'designation': _fmt(getattr(user_obj, 'designation', '') or (getattr(profile, 'designation', '') if profile else '')),
        'department': _fmt(getattr(user_obj, 'department', '') or (getattr(profile, 'department', '') if profile else '')),
        'grade': _fmt(getattr(user_obj, 'grade', '') or (getattr(profile, 'grade', '') if profile else '')),
        'address': _fmt(getattr(user_obj, 'address', '') or (getattr(profile, 'address', '') if profile else '')),
        'joining_date': _fmt(getattr(user_obj, 'date_of_joining', '') or (getattr(profile, 'dob', '') if profile else '')),
        'email': _fmt(getattr(user_obj, 'email', '')),
        'bank_name': _fmt(getattr(bank, 'bank_name', '') if bank else ''),
        'branch': _fmt(getattr(bank, 'branch', '') if bank else ''),
        'account_no': _fmt(getattr(bank, 'account_number', '') if bank else ''),
        'ifsc': _fmt(getattr(bank, 'ifsc_code', '') if bank else ''),
        'pan': _fmt(getattr(tax, 'pan_number', '') if tax else ''),
        'aadhaar': _fmt(getattr(user_obj, 'addhar_id', '')),
        'uan': _fmt(getattr(tax, 'uan_number', '') if tax else ''),
        'pf_no': _fmt(getattr(tax, 'pf_number', '') if tax else ''),
        'esi_no': _fmt(getattr(tax, 'esi_number', '') if tax else ''),
        'days_in_month': '{month_days}'.format(month_days=_calendar.monthrange(year, month)[1]),
        'present_days': getattr(gen, 'present_days', 0),
        'basic': _fmt(getattr(gen, 'basic_salary', '')),
        'hra': _fmt(getattr(gen, 'hra', '')),
        'conveyance': _fmt(getattr(gen, 'conveyance_allowances', '')),
        'fooding': _fmt(getattr(gen, 'fooding_allowance', '')),
        'medical': _fmt(getattr(gen, 'medical_allowance', '')),
        'education': _fmt(getattr(gen, 'education_allowance', '')),
        'transport': _fmt(getattr(gen, 'transport_allowance', '')),
        'special_allowance': _fmt(getattr(gen, 'special_allowances', '')),
        'bonus': _fmt(getattr(gen, 'bonuses', '')),
        'total_earning': _fmt(total_earning),
        'epf': _fmt(getattr(gen, 'epf_contribution', '')),
        'esi': _fmt(getattr(gen, 'esi_contribution', '')),
        'prof_tax': _fmt(getattr(gen, 'professional_tax', '')),
        'tds': _fmt(getattr(gen, 'tds', '')),
        'advance': _fmt(getattr(gen, 'advance_adjustment', '')),
        'total_deduction': _fmt(total_deduction),
        'net_salary': _fmt(net_salary),
        'amount_in_words': amount_in_words,
    }

    # Prefer PDF via ReportLab if available
    try:
    #     from reportlab.lib.pagesizes import A4
    #     from reportlab.pdfgen import canvas
    #     from io import BytesIO

    #     buf = BytesIO()
    #     c = canvas.Canvas(buf, pagesize=A4)
    #     width, height = A4

    #     left = 40
    #     top = height - 40

    #     c.setFont('Helvetica-Bold', 14)
    #     c.drawString(left, top, 'Arshee Engineering & Innovations Pvt. Ltd.')
    #     c.setFont('Helvetica', 10)
    #     c.drawString(left, top - 20, f"Salary Slip for: {tmpl_ctx['emp_name']} ({tmpl_ctx['emp_code']})")
    #     c.drawString(left, top - 35, f"Month/Year: {tmpl_ctx['month']}/{tmpl_ctx['year']}")
    #     c.drawString(left, top - 50, f"Generated By: {gen.generated_by.get_full_name() or gen.generated_by.username}")
    #     c.drawString(left, top - 65, f"Generated On: {gen.generated_on.strftime('%d-%b-%Y %H:%M')}")

    #     # Draw earnings/deductions table header
    #     c.setFont('Helvetica-Bold', 11)
    #     y = top - 95
    #     c.drawString(left, y, 'Earnings')
    #     c.drawString(left + 250, y, 'Deductions')
    #     c.setFont('Helvetica', 10)
    #     y -= 15

    #     def draw_row(label, amount, x):
    #         nonlocal y
    #         c.drawString(x, y, label)
    #         c.drawRightString(x + 130, y, f"{amount}")

    #     # Earnings
    #     draw_row('Basic Salary', tmpl_ctx['basic'], left)
    #     y -= 14
    #     draw_row('HRA', tmpl_ctx['hra'], left)
    #     y -= 14
    #     draw_row('Special Allowances', tmpl_ctx['special_allowance'], left)
    #     y -= 14
    #     draw_row('Conveyance', tmpl_ctx['conveyance'], left)

    #     # Deductions (draw on right column)
    #     y = top - 95 - 14
    #     draw_row('EPF', tmpl_ctx['epf'], left + 250)
    #     y -= 14
    #     draw_row('ESI', tmpl_ctx['esi'], left + 250)
    #     y -= 14
    #     draw_row('Professional Tax', tmpl_ctx['prof_tax'], left + 250)
    #     y -= 14
    #     draw_row('TDS', tmpl_ctx['tds'], left + 250)

    #     # Net Pay
    #     y -= 24
    #     c.setFont('Helvetica-Bold', 12)
    #     try:
    #         net_val = float(net_salary)
    #     except Exception:
    #         net_val = net_salary
    #     c.drawString(left, y, 'Net Pay:')
    #     c.drawRightString(left + 130, y, f"{net_val}")

    #     c.showPage()
    #     c.save()
    #     pdf = buf.getvalue()
    #     buf.close()

    #     filename = f"salary_slip_{tmpl_ctx['emp_code'] or user_obj.username}_{tmpl_ctx['month']}_{tmpl_ctx['year']}.pdf"
    #     response = HttpResponse(content_type='application/pdf')
    #     response['Content-Disposition'] = f'attachment; filename="{filename}"'
    #     response.write(pdf)
    #     return response

    # except Exception:
    #     # Fallback: render HTML and return as attachment
        rendered = render(request, 'payroll/salary_slip.html', tmpl_ctx)
        # Get rendered HTML as string
        try:
            if hasattr(rendered, 'content'):
                html_str = rendered.content.decode(getattr(rendered, 'charset', 'utf-8'))
            else:
                html_str = str(rendered)
        except Exception:
            html_str = str(rendered)

        # Try to embed the logo as a base64 data URI so the downloaded HTML
        # shows the logo even when opened locally (file://...)
        try:
            from django.contrib.staticfiles import finders
            import base64, mimetypes, os

            logo_rel_paths = ['logo.jpeg', 'logo.jpg', 'logo.png']
            logo_path = None
            for p in logo_rel_paths:
                found = finders.find(p)
                if found:
                    logo_path = found
                    break

            if logo_path and os.path.exists(logo_path):
                with open(logo_path, 'rb') as f:
                    data = f.read()
                mime_type, _ = mimetypes.guess_type(logo_path)
                if not mime_type:
                    mime_type = 'image/jpeg'
                data_uri = 'data:%s;base64,%s' % (mime_type, base64.b64encode(data).decode('ascii'))

                # Replace common static URL occurrences with the data URI
                html_str = html_str.replace('/static/logo.jpeg', data_uri)
                html_str = html_str.replace('/static/logo.jpg', data_uri)
                html_str = html_str.replace('/static/logo.png', data_uri)
                html_str = html_str.replace('src="{% static '"'"'logo.jpeg'"'"' %}"', f'src="{data_uri}"')
                html_str = html_str.replace("src='{% static 'logo.jpeg' %}'", f"src='{data_uri}'")
        except Exception:
            # If anything fails, fall back to the original rendered HTML
            pass

        filename = f"salary_slip_{tmpl_ctx['emp_code'] or user_obj.username}_{tmpl_ctx['month']}_{tmpl_ctx['year']}.html"
        resp = HttpResponse(html_str.encode('utf-8'), content_type='text/html; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from io import BytesIO

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4

        left = 40
        top = height - 40

        c.setFont('Helvetica-Bold', 14)
        c.drawString(left, top, context['company_name'])
        c.setFont('Helvetica', 10)
        c.drawString(left, top - 20, f"Salary Slip for: {gen.user.get_full_name() or gen.user.username} ({gen.user.employee_id or '-'})")
        c.drawString(left, top - 35, f"Month/Year: {gen.month}/{gen.year}")
        c.drawString(left, top - 50, f"Generated By: {gen.generated_by.get_full_name() or gen.generated_by.username}")
        c.drawString(left, top - 65, f"Generated On: {gen.generated_on.strftime('%d-%b-%Y %H:%M')}")

        # Draw earnings/deductions table header
        c.setFont('Helvetica-Bold', 11)
        y = top - 95
        c.drawString(left, y, 'Earnings')
        c.drawString(left + 250, y, 'Deductions')
        c.setFont('Helvetica', 10)
        y -= 15


        def _to_decimal_local(v):
            from decimal import Decimal as _D
            if v is None:
                return _D('0')
            try:
                # Handle BSON Decimal128
                from bson.decimal128 import Decimal128 as BsonDecimal128
            except Exception:
                BsonDecimal128 = None
            try:
                if BsonDecimal128 and isinstance(v, BsonDecimal128):
                    return v.to_decimal()
                if isinstance(v, _D):
                    return v
                return _D(str(v))
            except Exception:
                try:
                    return _D(str(v))
                except Exception:
                    return _D('0')

        def draw_row(label, amount, x):
            nonlocal y
            c.drawString(x, y, label)
            c.drawRightString(x + 130, y, f"{amount}")

        # Earnings
        basic = _to_decimal_local(getattr(gen, 'basic_salary', None))
        hra = _to_decimal_local(getattr(gen, 'hra', None))
        special = _to_decimal_local(getattr(gen, 'special_allowances', None))
        convey = _to_decimal_local(getattr(gen, 'conveyance_allowances', None))

        draw_row('Basic Salary', basic, left)
        y -= 14
        draw_row('HRA', hra, left)
        y -= 14
        draw_row('Special Allowances', special, left)
        y -= 14
        draw_row('Conveyance', convey, left)

        # Deductions (draw on right column)
        y = top - 95 - 14
        epf = _to_decimal_local(getattr(gen, 'epf_contribution', None))
        esi = _to_decimal_local(getattr(gen, 'esi_contribution', None))
        prof_tax = _to_decimal_local(getattr(gen, 'professional_tax', None))
        tds = _to_decimal_local(getattr(gen, 'tds', None))

        draw_row('EPF', epf, left + 250)
        y -= 14
        draw_row('ESI', esi, left + 250)
        y -= 14
        draw_row('Professional Tax', prof_tax, left + 250)
        y -= 14
        draw_row('TDS', tds, left + 250)

        # Net Pay
        y -= 24
        c.setFont('Helvetica-Bold', 12)
        net = basic + hra + special + convey - (epf + esi + prof_tax + tds)
        c.drawString(left, y, 'Net Pay:')
        try:
            net_str = str(net)
        except Exception:
            net_str = f"{net}"
        c.drawRightString(left + 130, y, net_str)

        c.showPage()
        c.save()
        pdf = buf.getvalue()
        buf.close()

        filename = f"salary_slip_{gen.user.employee_id or gen.user.username}_{gen.month}_{gen.year}.pdf"
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write(pdf)
        return response

    except Exception:
        # Fallback: render HTML and return as attachment
        rendered = render(request, 'payroll/salary_slip.html', {'g': gen})
        html_content = rendered.content if hasattr(rendered, 'content') else rendered
        filename = f"salary_slip_{gen.user.employee_id or gen.user.username}_{gen.month}_{gen.year}.html"
        resp = HttpResponse(html_content, content_type='text/html')
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp