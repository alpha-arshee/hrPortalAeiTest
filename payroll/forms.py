from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import AdvanceSalaryRequest

class AdvanceSalaryRequestForm(forms.ModelForm):
    """Form for employees to request advance salary"""
    class Meta:
        model = AdvanceSalaryRequest
        fields = ['amount', 'reason']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reason': forms.Textarea(attrs={'rows': 4, 'cols': 40, 'class': 'form-control'}),
        }
        
class ApproveAdvanceSalaryForm(forms.ModelForm):
    """Form for HR Admin to approve/reject advance salary requests"""
    class Meta:
        model = AdvanceSalaryRequest
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def save(self, commit=True):
        obj = super().save(commit=False)
        # set decision_date when status is changed from pending
        if obj.status in ('approved', 'rejected') and obj.decision_date is None:
            from django.utils import timezone
            obj.decision_date = timezone.now()
        if commit:
            obj.save()
        return obj