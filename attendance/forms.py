from django import forms
from django.utils import timezone
from .models import Leave, AttendanceRequest
from .models import BiometricLog
from django import forms
from accounts.models import User
from django.db import DatabaseError

class LeaveRequestForm(forms.ModelForm):
    leave_type = forms.ChoiceField(
        choices=[
            ('paid_casual', 'Paid Casual Leave'),
            ('paid_sick', 'Paid Sick Leave'),
            ('paid_privilege', 'Paid Privilege Leave'),
            # ('unpaid', 'Unpaid Leave'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Leave
        fields = ['start_date', 'end_date', 'reason', 'leave_type', 'supporting_document', 'contact_during_leave']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'contact_during_leave': forms.TextInput(attrs={'class': 'form-control'}),
            'supporting_document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')

        if start and end and end < start:
            raise forms.ValidationError("End date cannot be earlier than start date.")

        today = timezone.localdate()
        if start and start < today:
            raise forms.ValidationError("Start date cannot be in the past.")

        return cleaned


class HRAddAttendanceForm(forms.ModelForm):
    # allow choosing an existing user or entering employee_id directly
    user = forms.ModelChoiceField(queryset=User.objects.all(), required=False, widget=forms.Select(attrs={'class':'form-select'}))

    class Meta:
        model = BiometricLog
        fields = ['user', 'employee_id', 'punch_date', 'punch_time', 'status', 'hr_reason']
        widgets = {
            'employee_id': forms.TextInput(attrs={'class':'form-control'}),
            'punch_date': forms.DateInput(attrs={'type':'date', 'class':'form-control'}),
            'punch_time': forms.TimeInput(attrs={'type':'time', 'class':'form-control'}),
            'status': forms.Select(choices=[('IN','IN'),('OUT','OUT')], attrs={'class':'form-select'}),
            'hr_reason': forms.Textarea(attrs={'class':'form-control', 'rows':3}),
        }

    def clean(self):
        cleaned = super().clean()
        eid = cleaned.get('employee_id')
        user = cleaned.get('user')
        if not eid and not user:
            raise forms.ValidationError('Please provide either an employee or employee id.')
        # if user is provided but employee_id blank, populate employee_id
        if user and not eid:
            try:
                cleaned['employee_id'] = getattr(user, 'employee_id', '')
            except Exception:
                pass
        return cleaned


class EmployeeAttendanceRequestForm(forms.ModelForm):
    """Employee submits attendance request when not in office"""
    punch_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        help_text='Optional: Leave blank to use current time'
    )

    class Meta:
        model = AttendanceRequest
        fields = ['request_date', 'reason', 'punch_time']
        widgets = {
            'request_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'rows': 4, 'class': 'form-control', 'placeholder': 'e.g., Working from home, Remote meeting, etc.'}),
        }

    def clean(self):
        cleaned = super().clean()
        request_date = cleaned.get('request_date')
        
        # Validate date
        today = timezone.localdate()
        if request_date:
            if request_date > today:
                raise forms.ValidationError("Request date cannot be in the future.")
            if request_date < today - timezone.timedelta(days=30):
                raise forms.ValidationError("Cannot request attendance for dates older than 30 days.")
        
        # Auto-fill punch_time if blank (remove microseconds)
        if not cleaned.get('punch_time'):
            cleaned['punch_time'] = timezone.localtime().time().replace(microsecond=0)
        
        return cleaned


class HRApproveAttendanceRequestForm(forms.Form):
    """HR form to approve or reject attendance request"""
    STATUS_CHOICES = [
        ('approved', '✓ Approve'),
        ('rejected', '✗ Reject'),
    ]
    
    action = forms.ChoiceField(
        choices=STATUS_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='Action'
    )
    
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Mandatory if rejecting'}),
        label='Reason (Required if rejecting)'
    )

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get('action')
        rejection_reason = cleaned.get('rejection_reason')
        
        if action == 'rejected' and not rejection_reason:
            raise forms.ValidationError("Rejection reason is mandatory when rejecting a request.")
        
        return cleaned


