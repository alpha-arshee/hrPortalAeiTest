from django.db import models
from accounts.models import User
import logging
# Create your models here.

class LeaveQuota(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    year = models.IntegerField()
    total_paid_leaves = models.IntegerField(default=0)
    total_unpaid_leaves = models.IntegerField(default=0)
    used_paid_leaves = models.IntegerField(default=0)
    used_unpaid_leaves = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} - {self.year}"

class AttendanceRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    working_hours = models.DecimalField(max_digits=5, decimal_places=2)
    date = models.DateField()
    check_in_time = models.DateTimeField()
    check_out_time = models.DateTimeField()
    present_day = models.BooleanField(default=False)
    absent_day = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=[('present', 'Present'), ('absent', 'Absent')])

    def __str__(self):
        return f"{self.user.username} - {self.date}"

class Leave(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    leave_type = models.CharField(max_length=20, choices=[('paid', 'Paid'), ('unpaid', 'Unpaid')], default='paid')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    supporting_document = models.FileField(upload_to='leave_docs/', blank=True, null=True)
    contact_during_leave = models.CharField(max_length=150, blank=True, null=True)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending')
    decision_date = models.DateField(null=True, blank=True)
    decision_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='leave_decisions')

    def __str__(self):
        return f"{self.user.username} - {self.start_date} to {self.end_date}"
    

class Overtime(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    total_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    compensation = models.DecimalField(max_digits=10, decimal_places=2,default=0.00)
    total_compensation = models.DecimalField(max_digits=10, decimal_places=2,default=0.00)
    reason = models.TextField()
    
    def save(self, *args, **kwargs):
        """Compute suggested compensation and update monthly cumulative totals.

        Behavior:
        - If `compensation` is zero/empty, compute suggestion using `user.overtime_rate` or
          `settings.OVERTIME_RATE_PER_HOUR` fallback.
        - Save the record, then compute sums for the same user/month and update
          `total_hours` and `total_compensation` for this record (DB update to avoid recursion).
        """
        from decimal import Decimal
        from django.conf import settings
        # determine rate: prefer attribute on user, else settings fallback
        rate = None
        try:
            rate = getattr(self.user, 'overtime_rate', None)
        except Exception:
            rate = None
        if rate is None:
            rate = getattr(settings, 'OVERTIME_RATE_PER_HOUR', Decimal('0.00'))
        # normalize types
        try:
            hours_val = Decimal(self.hours)
        except Exception:
            hours_val = Decimal('0.00')

        # if compensation is falsy or zero, compute suggested value
        try:
            comp_val = Decimal(self.compensation)
        except Exception:
            comp_val = Decimal('0.00')

        if (not comp_val):
            try:
                # normalize rate to Decimal and ensure it's > 0
                rate_dec = Decimal(str(rate))
                if rate_dec > Decimal('0'):
                    comp_val = (hours_val * rate_dec)
                    # round to 2 decimal places
                    comp_val = comp_val.quantize(Decimal('0.01'))
                    self.compensation = comp_val
            except Exception:
                # leave compensation as-is (0.00) on error
                pass

        # Save first so we have a PK to update totals
        # Normalize any BSON Decimal128 values to Python Decimal to avoid
        # djongo/pymongo returning Decimal128 objects that Django's
        # DecimalField cannot convert during save.
        try:
            from bson.decimal128 import Decimal128 as _BsonDecimal128
            if isinstance(getattr(self, 'hours', None), _BsonDecimal128):
                try:
                    self.hours = self.hours.to_decimal()
                except Exception:
                    pass
            if isinstance(getattr(self, 'compensation', None), _BsonDecimal128):
                try:
                    self.compensation = self.compensation.to_decimal()
                except Exception:
                    pass
            if isinstance(getattr(self, 'total_hours', None), _BsonDecimal128):
                try:
                    self.total_hours = self.total_hours.to_decimal()
                except Exception:
                    pass
            if isinstance(getattr(self, 'total_compensation', None), _BsonDecimal128):
                try:
                    self.total_compensation = self.total_compensation.to_decimal()
                except Exception:
                    pass
        except Exception:
            # If bson isn't available or conversion fails, continue and let save attempt
            pass

        super().save(*args, **kwargs)

        # compute cumulative totals for this user's month
        try:
            from datetime import date as _date
            # build month range: start = first day of month, end = first day of next month
            start = _date(self.date.year, self.date.month, 1)
            if self.date.month == 12:
                end = _date(self.date.year + 1, 1, 1)
            else:
                end = _date(self.date.year, self.date.month + 1, 1)

            qs = Overtime.objects.filter(user=self.user, date__gte=start, date__lt=end)
            # perform Python-side Decimal summation to avoid DB date-extract SQL functions
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

            # persist totals using queryset update to avoid save recursion
            Overtime.objects.filter(pk=self.pk).update(total_hours=sum_hours, total_compensation=sum_comp)
        except Exception:
            # don't block save on aggregation errors
            logger = logging.getLogger(__name__)
            logger.exception('Failed to update overtime totals')

    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.hours} hours"


class BiometricLog(models.Model):
    employee_id = models.CharField(max_length=50)
    first_name = models.CharField(max_length=100, null=True, blank=True)
    department = models.CharField(max_length=150, null=True, blank=True)
    punch_time = models.CharField(max_length=8)  # ✅ "HH:MM:SS"
    punch_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=[("IN", "IN"), ("OUT", "OUT")])
    device_id = models.CharField(max_length=50)
    device_serial_no = models.CharField(max_length=100, null=True, blank=True)
    # Link to User so we can show attendance per-user easily. Optional because some logs
    # may not have a matching user yet. On save we attempt to auto-link by employee_id.
    user = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL)

    # When HR manually adds an attendance entry, mark it and capture reason
    marked_by_hr = models.BooleanField(default=False)
    hr_reason = models.TextField(null=True, blank=True)
    marked_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='marked_attendance')
    marked_at = models.DateTimeField(null=True, blank=True)


    
    # when hr mark holiday, it creates BiometricLog for every employee(both hr and employee) with status '0/In' , Name/Dept 'holiday_name' and no punch_time;
    holiday_name = models.CharField(max_length=150, null=True, blank=True)
    holiday_marked_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='marked_holidays')
    holiday_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.employee_id} - {self.status} - {self.punch_date} {self.punch_time}"

    def save(self, *args, **kwargs):
        """If a user isn't linked but employee_id is present, try to link automatically.

        This is a best-effort link; failures (DB errors, multiple matches) are ignored
        to avoid breaking ingestion. Use the management command to backfill/repair.
        """
        try:
            if not self.user and self.employee_id:
                from accounts.models import User
                try:
                    matched = User.objects.filter(employee_id=self.employee_id).first()
                    if matched:
                        self.user = matched
                except Exception:
                    # Don't raise here; allow save to proceed without a user
                    pass
        except Exception:
            # Guard the outer import/attribute errors as well
            pass

        super().save(*args, **kwargs)

    class Meta:
        indexes = [models.Index(fields=['employee_id'])]


class AttendanceRequest(models.Model):
    """
    Employee request for attendance marking when not in office.
    HR can approve or reject with mandatory rejection reason.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    # Employee requesting
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_requests')
    
    # Date of attendance being requested
    request_date = models.DateField()
    
    # Employee's reason (e.g., "Working from home", "Remote meeting")
    reason = models.TextField()
    
    # Punch time (check-in time when employee worked)
    punch_time = models.TimeField(null=True, blank=True)
    
    # Request status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # When employee submitted the request
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    # HR review info
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_attendance_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Mandatory rejection reason (if rejected)
    rejection_reason = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-submitted_at']
        unique_together = [['user', 'request_date']]  # One request per employee per day
        indexes = [models.Index(fields=['user', 'request_date', 'status'])]
    
    def __str__(self):
        return f"{self.user.username} - {self.request_date} ({self.status})"
