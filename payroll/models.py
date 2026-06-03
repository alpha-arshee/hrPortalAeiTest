from django.db import models
from accounts.models import User
# Create your models here.

class EmployeePayrollDetails(models.Model):
    """Model to store payroll details for employees"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payroll_details')
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2)
    hra = models.DecimalField(max_digits=10, decimal_places=2)
    special_allowances = models.DecimalField(max_digits=10, decimal_places=2)
    conveyance_allowances = models.DecimalField(max_digits=10, decimal_places=2)
    epf_contribution = models.DecimalField(max_digits=10, decimal_places=2)
    esi_contribution = models.DecimalField(max_digits=10, decimal_places=2)
    professional_tax = models.DecimalField(max_digits=10, decimal_places=2)
    tds = models.DecimalField(max_digits=10, decimal_places=2)
    pay_day=models.DecimalField(max_digits=2, decimal_places=0, default=1)
    fooding_allowance=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    medical_allowance=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    education_allowance=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transport_allowance=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    

    def __str__(self):
        return f"Payroll for {self.user.username}"
    
    
    
class AdvanceSalaryRequest(models.Model):
    """Model to store advance salary requests from employees"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='advance_salary_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    request_date = models.DateTimeField(auto_now_add=True)
    decision_date = models.DateTimeField(null=True, blank=True)
    approver = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_advance_requests')
    
    def __str__(self):
        return f"Advance Salary Request by {self.user.username} - {self.status}"
    
    
class GeneratePayroll(models.Model):
    """Model to log payroll generation activities"""
    generated_on = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payroll_generation_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='generated_payrolls', null=True, blank=True)
    month = models.IntegerField()
    year = models.IntegerField()
    date = models.DateField(auto_now_add=True)
    present_days = models.IntegerField(default=0)
    absent_days = models.IntegerField(default=0)
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2)
    hra = models.DecimalField(max_digits=10, decimal_places=2)
    special_allowances = models.DecimalField(max_digits=10, decimal_places=2)
    conveyance_allowances = models.DecimalField(max_digits=10, decimal_places=2)
    epf_contribution = models.DecimalField(max_digits=10, decimal_places=2)
    esi_contribution = models.DecimalField(max_digits=10, decimal_places=2)
    professional_tax = models.DecimalField(max_digits=10, decimal_places=2)
    tds = models.DecimalField(max_digits=10, decimal_places=2)
    
    # additional allowances
    fooding_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    medical_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    education_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transport_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    bonous = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bonuses = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    advance_adjustment = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    overtime_compensation = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20,default='Not Paid')
    
    
    def __str__(self):
        return f"Payroll generated for {self.month}/{self.year} by {self.generated_by.username} on {self.generated_on}"
    
    
class PayrollHistory(models.Model):
    """Model to store payroll history for employees"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payroll_history')
    month = models.IntegerField()
    year = models.IntegerField()
    total_paid = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return f"Payroll History for {self.user.username} - {self.month}/{self.year}"