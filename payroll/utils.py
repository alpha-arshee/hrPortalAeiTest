"""
Payroll utilities.

Provides `use_payroll_dashboard(user, for_hr=False, params=None)` which returns
a context dictionary suitable for rendering payroll dashboards in templates
or returning via JSON.

The function is defensive: it catches DB/backends that may not support
certain queries (e.g., djongo quirks) and returns sensible defaults.
"""
from datetime import date
import calendar
from decimal import Decimal
from typing import Any, Dict, Optional

from .models import EmployeePayrollDetails, GeneratePayroll


def use_payroll_dashboard(user, for_hr: bool = False, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Builds and returns context used by payroll dashboard views.

    Args:
        user: Django `User` instance requesting the dashboard.
        for_hr: If True, include all employees' payroll details; otherwise
            restrict `payrolls` to the current `user`.
        params: Optional dict with optional keys: `month`, `year`, `status`, `q`, `sort`.
            - If `month` or `year` is None, they default to current month/year.
            - If `month` or `year` is the empty string (""), the filter is not applied.

    Returns:
        A dict containing keys: `payrolls`, `generate_payrolls`, `filter_month`,
        `filter_year`, `filter_status`, `months_list`, `years_list`, `statuses_list`.
    """
    if params is None:
        params = {}
    # Payroll details list (per-employee records)
    try:
        if for_hr:
            payrolls_qs = EmployeePayrollDetails.objects.all().order_by('-id')
        else:
            payrolls_qs = EmployeePayrollDetails.objects.filter(user=user).order_by('-id')
    except Exception:
        payrolls_qs = EmployeePayrollDetails.objects.none()

    # Generated payroll queryset and simple filters
    try:
        if for_hr:
            gen_qs = GeneratePayroll.objects.all().order_by('-year', '-month')
        else:
            # restrict generated payrolls to this user for non-HR dashboards
            gen_qs = GeneratePayroll.objects.filter(user=user).order_by('-year', '-month')
    except Exception:
        gen_qs = GeneratePayroll.objects.none()

    # Read filter params (None -> default to current month/year; '' -> no filter)
    today = date.today()
    month = params.get('month')
    year = params.get('year')
    status = params.get('status')
    q = params.get('q')
    sort = params.get('sort')

    if month is None:
        month = str(today.month)
    if year is None:
        year = str(today.year)

    # Apply month/year filters when not empty string
    try:
        if month != "":
            gen_qs = gen_qs.filter(month=int(month))
    except Exception:
        pass

    try:
        if year != "":
            gen_qs = gen_qs.filter(year=int(year))
    except Exception:
        pass

    if status:
        try:
            gen_qs = gen_qs.filter(status__iexact=status)
        except Exception:
            pass

    # Search (q) applied to GeneratePayroll.user fields where possible
    if q:
        try:
            from django.db.models import Q

            gen_qs = gen_qs.filter(
                Q(user__first_name__icontains=q) |
                Q(user__last_name__icontains=q) |
                Q(user__username__icontains=q) |
                Q(user__employee_id__icontains=q)
            )
        except Exception:
            # If related-field filtering is unsupported, ignore the query
            pass

    # Sorting support (best-effort)
    if sort:
        try:
            if sort.startswith('-'):
                key = sort[1:]
                gen_qs = gen_qs.order_by(f'-{key}')
            else:
                gen_qs = gen_qs.order_by(sort)
        except Exception:
            # ignore invalid sort keys
            pass

    # helper lists for selects
    months_list = [str(i) for i in range(1, 13)]
    now_year = date.today().year
    years_list = [str(y) for y in range(now_year - 10, now_year + 1)]

    try:
        statuses = list(GeneratePayroll.objects.order_by().values_list('status', flat=True).distinct())
    except Exception:
        statuses = ['Paid', 'Not Paid']

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

    # Include user-specific employment/bank/tax info and the latest payroll detail
    try:
        try:
            banking_info = getattr(user, 'bankinginfo', None)
        except Exception:
            banking_info = None
        try:
            tax_info = getattr(user, 'taxinfo', None)
        except Exception:
            tax_info = None
        try:
            employee_profile = getattr(user, 'employeeprofile', None)
        except Exception:
            employee_profile = None

        try:
            latest_payroll_detail = None
            if not for_hr:
                # only fetch the user's payroll detail when used for a user dashboard
                latest_payroll_detail = EmployeePayrollDetails.objects.filter(user=user).order_by('-id').first()
            else:
                # for HR view, do not eagerly fetch per-user latest record here
                latest_payroll_detail = None
        except Exception:
            latest_payroll_detail = None

        context.update({
            'banking_info': banking_info,
            'tax_info': tax_info,
            'employee_profile': employee_profile,
            'latest_payroll_detail': latest_payroll_detail,
        })
    except Exception:
        # If anything unexpected fails while building these optional keys,
        # keep going without them.
        pass

    # Compute cumulative earnings/deductions for the user (best-effort).
    try:
        if not for_hr:
            # Sum earnings fields across generated payrolls for this user
            from decimal import Decimal as _D
            try:
                gen_qs_user = GeneratePayroll.objects.filter(user=user)
            except Exception:
                gen_qs_user = []

            def _to_decimal(v):
                try:
                    from bson.decimal128 import Decimal128 as BsonDecimal128
                except Exception:
                    BsonDecimal128 = None
                try:
                    if v is None:
                        return _D('0')
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

            total_earn = _D('0')
            total_ded = _D('0')
            if gen_qs_user:
                try:
                    for (b, h, s, c, bo, epf, esi, prof, tds, adv) in gen_qs_user.values_list(
                        'basic_salary', 'hra', 'special_allowances', 'conveyance_allowances', 'bonuses',
                        'epf_contribution', 'esi_contribution', 'professional_tax', 'tds', 'advance_adjustment'
                    ):
                        try:
                            total_earn += _to_decimal(b) + _to_decimal(h) + _to_decimal(s) + _to_decimal(c) + _to_decimal(bo)
                        except Exception:
                            pass
                        try:
                            total_ded += _to_decimal(epf) + _to_decimal(esi) + _to_decimal(prof) + _to_decimal(tds) + _to_decimal(adv)
                        except Exception:
                            pass
                except Exception:
                    # fallback iteration if values_list not supported by backend
                    try:
                        for g in gen_qs_user:
                            total_earn += _to_decimal(getattr(g, 'basic_salary', 0)) + _to_decimal(getattr(g, 'hra', 0)) + _to_decimal(getattr(g, 'special_allowances', 0)) + _to_decimal(getattr(g, 'conveyance_allowances', 0)) + _to_decimal(getattr(g, 'bonuses', 0))
                            total_ded += _to_decimal(getattr(g, 'epf_contribution', 0)) + _to_decimal(getattr(g, 'esi_contribution', 0)) + _to_decimal(getattr(g, 'professional_tax', 0)) + _to_decimal(getattr(g, 'tds', 0)) + _to_decimal(getattr(g, 'advance_adjustment', 0))
                    except Exception:
                        total_earn = _D('0')
                        total_ded = _D('0')

            context['total_earnings_to_date'] = total_earn
            context['total_deductions_to_date'] = total_ded
        else:
            context['total_earnings_to_date'] = None
            context['total_deductions_to_date'] = None
    except Exception:
        # Do not break the caller if this calculation fails
        context['total_earnings_to_date'] = None
        context['total_deductions_to_date'] = None
    # Determine payroll status for the current month (Paid / Not Paid)
    try:
        if not for_hr:
            today = date.today()
            try:
                cur_month = int(today.month)
                cur_year = int(today.year)
            except Exception:
                cur_month = None
                cur_year = None

            payroll_status = None
            try:
                if cur_month and cur_year:
                    rec = GeneratePayroll.objects.filter(user=user, month=cur_month, year=cur_year).order_by('-id').first()
                    if rec:
                        st = (getattr(rec, 'status', '') or '').strip().lower()
                        payroll_status = 'Paid' if st == 'paid' else 'Not Paid'
                    else:
                        payroll_status = 'Not Paid'
                else:
                    payroll_status = None
            except Exception:
                payroll_status = None
        else:
            payroll_status = None
    except Exception:
        payroll_status = None

    context['payroll_status'] = payroll_status
    # If this dashboard is for HR, compute high-level KPI summaries for the
    # selected filters (month/year/status). These are best-effort and defensive
    # to tolerate backends that may not support some operations (djongo etc.).
    try:
        if for_hr:
            from decimal import Decimal as _D
            try:
                from bson.decimal128 import Decimal128 as BsonDecimal128
            except Exception:
                BsonDecimal128 = None

            def _to_decimal(v):
                try:
                    if v is None:
                        return _D('0')
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

            # Total employees (use EmployeeProfile if available)
            try:
                from accounts.models import EmployeeProfile
                total_employees = EmployeeProfile.objects.count()
            except Exception:
                try:
                    from accounts.models import User
                    total_employees = User.objects.count()
                except Exception:
                    total_employees = None

            # Use the already-filtered gen_qs (filtered by month/year/status above)
            try:
                gp = gen_qs
            except Exception:
                try:
                    gp = GeneratePayroll.objects.all()
                except Exception:
                    gp = []

            
            try:
                pending_generate_list = []
                pending_generate_count = 0
            except Exception:
                pending_generate_list = []
                pending_generate_count = 0

            # Compute how many employees do NOT have a generated payroll for
            # the selected filters (used in the template as `not_paid_till`).
            try:
                generated_user_count = 0
                try:
                    # Prefer database distinct count when available
                    generated_user_count = gen_qs.values_list('user', flat=True).distinct().count()
                except Exception:
                    # Fallback: iterate and collect unique user ids
                    s = set()
                    try:
                        for r in gp:
                            try:
                                uid = getattr(r, 'user_id', None)
                                if uid is None:
                                    uobj = getattr(r, 'user', None)
                                    uid = getattr(uobj, 'id', None) if uobj is not None else None
                                if uid is not None:
                                    s.add(uid)
                            except Exception:
                                continue
                    except Exception:
                        s = set()
                    generated_user_count = len(s)

                try:
                    if total_employees is None:
                        not_paid_till = None
                    else:
                        not_paid = int(total_employees) - int(generated_user_count)
                        not_paid_till = not_paid if not_paid > 0 else 0
                except Exception:
                    not_paid_till = None
            except Exception:
                not_paid_till = None

            total_payroll_cost = _D('0')
            net_salary_paid = _D('0')
            overtime_cost = _D('0')
            total_deductions = _D('0')
            # component level sums for pie chart
            total_basic = _D('0')
            total_hra = _D('0')
            total_allowances = _D('0')

            # 12-month trend: compute total payroll cost per month for the
            # last 12 months (oldest -> newest). Expose as labels and values
            # for the template's line chart. This is best-effort and will
            # fallback to zeros on error.
            trend_labels = []
            trend_values = []
            try:
                # Build months from oldest to newest
                for delta in range(11, -1, -1):
                    # compute target month/year by subtracting delta months
                    m = today.month - delta
                    y = today.year
                    while m <= 0:
                        m += 12
                        y -= 1
                    # human-friendly label like 'Dec 2025'
                    label = f"{calendar.month_abbr[m]} {y}"
                    trend_labels.append(label)
                    # sum payrolls for month/year
                    month_total = _D('0')
                    try:
                        month_qs = GeneratePayroll.objects.filter(month=int(m), year=int(y))
                    except Exception:
                        month_qs = []
                    try:
                        for rec in month_qs:
                            try:
                                gross = _to_decimal(getattr(rec, 'basic_salary', 0)) + _to_decimal(getattr(rec, 'hra', 0)) + _to_decimal(getattr(rec, 'special_allowances', 0)) + _to_decimal(getattr(rec, 'conveyance_allowances', 0)) + _to_decimal(getattr(rec, 'bonuses', 0))
                            except Exception:
                                gross = _D('0')
                            try:
                                deductions = _to_decimal(getattr(rec, 'epf_contribution', 0)) + _to_decimal(getattr(rec, 'esi_contribution', 0)) + _to_decimal(getattr(rec, 'professional_tax', 0)) + _to_decimal(getattr(rec, 'tds', 0)) + _to_decimal(getattr(rec, 'advance_adjustment', 0))
                            except Exception:
                                deductions = _D('0')
                            try:
                                ot = _to_decimal(getattr(rec, 'overtime_compensation', 0))
                            except Exception:
                                ot = _D('0')
                            month_total += gross + deductions + ot
                    except Exception:
                        # fallback: try values_list if iteration fails
                        try:
                            for vals in month_qs.values_list('basic_salary', 'hra', 'special_allowances', 'conveyance_allowances', 'bonuses', 'epf_contribution', 'esi_contribution', 'professional_tax', 'tds', 'advance_adjustment', 'overtime_compensation'):
                                try:
                                    b, h, s, c, bo, epf, esi, prof, tds, adv, ot = vals
                                except Exception:
                                    continue
                                gross = _to_decimal(b) + _to_decimal(h) + _to_decimal(s) + _to_decimal(c) + _to_decimal(bo)
                                deductions = _to_decimal(epf) + _to_decimal(esi) + _to_decimal(prof) + _to_decimal(tds) + _to_decimal(adv)
                                month_total += gross + deductions + _to_decimal(ot)
                        except Exception:
                            month_total = _D('0')
                    # store numeric string for safe injection in template JS
                    trend_values.append(str(month_total))
            except Exception:
                # if anything fails, provide empty/default arrays
                trend_labels = []
                trend_values = []

            if gp:
                try:
                    for r in gp:
                        # gross earnings: basic + hra + special + conveyance + bonuses
                        gross = _to_decimal(getattr(r, 'basic_salary', 0)) + _to_decimal(getattr(r, 'hra', 0)) + _to_decimal(getattr(r, 'special_allowances', 0)) + _to_decimal(getattr(r, 'conveyance_allowances', 0)) + _to_decimal(getattr(r, 'bonuses', 0))
                        # deductions: epf + esi + professional_tax + tds + advance_adjustment
                        deductions = _to_decimal(getattr(r, 'epf_contribution', 0)) + _to_decimal(getattr(r, 'esi_contribution', 0)) + _to_decimal(getattr(r, 'professional_tax', 0)) + _to_decimal(getattr(r, 'tds', 0)) + _to_decimal(getattr(r, 'advance_adjustment', 0))
                        net = gross - deductions
                        # accumulate total deductions for the KPI
                        total_deductions += deductions
                        # overtime for this record
                        overtime_val = _to_decimal(getattr(r, 'overtime_compensation', 0))
                        # total payroll cost is defined as gross + deductions + overtime
                        total_payroll_cost += gross + deductions + overtime_val
                        # accumulate component breakdown
                        total_basic += _to_decimal(getattr(r, 'basic_salary', 0))
                        total_hra += _to_decimal(getattr(r, 'hra', 0))
                        # allowances include special_allowances, conveyance_allowances and bonuses
                        total_allowances += _to_decimal(getattr(r, 'special_allowances', 0)) + _to_decimal(getattr(r, 'conveyance_allowances', 0)) + _to_decimal(getattr(r, 'bonuses', 0))
                        # treat status 'paid' (case-insensitive) as paid
                        st = (getattr(r, 'status', '') or '').strip().lower()
                        # total earnings for this record = gross + overtime
                        earnings = gross + overtime_val
                        if st == 'paid':
                            # Net Salary Paid should reflect total earnings for generated (paid) payrolls
                            net_salary_paid += earnings
                        overtime_cost += overtime_val
                except Exception:
                    # fallback if iteration over queryset fails
                    try:
                        for vals in gp.values_list('basic_salary', 'hra', 'special_allowances', 'conveyance_allowances', 'bonuses', 'epf_contribution', 'esi_contribution', 'professional_tax', 'tds', 'advance_adjustment', 'status', 'overtime_compensation'):
                            try:
                                b, h, s, c, bo, epf, esi, prof, tds, adv, st, ot = vals
                            except Exception:
                                continue
                            gross = _to_decimal(b) + _to_decimal(h) + _to_decimal(s) + _to_decimal(c) + _to_decimal(bo)
                            deductions = _to_decimal(epf) + _to_decimal(esi) + _to_decimal(prof) + _to_decimal(tds) + _to_decimal(adv)
                            total_deductions += deductions
                            net = gross - deductions
                            # Use gross + deductions + overtime for total payroll cost
                            ot_dec = _to_decimal(ot)
                            total_payroll_cost += gross + deductions + ot_dec
                            # accumulate component breakdown from values_list fallback
                            total_basic += _to_decimal(b)
                            total_hra += _to_decimal(h)
                            total_allowances += _to_decimal(s) + _to_decimal(c) + _to_decimal(bo)
                            # total earnings for this record = gross + overtime
                            earnings = gross + ot_dec
                            if (st or '').strip().lower() == 'paid':
                                # Net Salary Paid = total earnings of payrolls marked as paid
                                net_salary_paid += earnings
                            overtime_cost += ot_dec
                    except Exception:
                        # give up and leave zeros
                        pass

            context['total_employees'] = total_employees
            context['total_payroll_cost'] = total_payroll_cost
            context['net_salary_paid'] = net_salary_paid
            context['overtime_cost'] = overtime_cost
            context['deductions'] = total_deductions
            # component sums for charting
            context['total_basic'] = total_basic
            context['total_hra'] = total_hra
            context['total_allowances'] = total_allowances
            # trend data for 12-month line chart
            context['trend_labels'] = trend_labels
            context['trend_values'] = trend_values
            # expose number of employees without a generated payroll for the
            # selected filters (used in template as `not_paid_till`)
            context['not_paid_till'] = not_paid_till
            context['pending_generate_count'] = pending_generate_count
            context['pending_generate_payrolls'] = pending_generate_list
        else:
            # for non-HR dashboards, these keys are not applicable
            context['total_employees'] = None
            context['total_payroll_cost'] = None
            context['net_salary_paid'] = None
            context['overtime_cost'] = None
            context['deductions'] = None
            context['pending_generate_count'] = 0
            context['pending_generate_payrolls'] = []
    except Exception:
        # ensure we always return without raising
        context.setdefault('total_employees', None)
        context.setdefault('total_payroll_cost', None)
        context.setdefault('net_salary_paid', None)
        context.setdefault('overtime_cost', None)
    return context
