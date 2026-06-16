from djongo import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.core.validators import RegexValidator

class CustomUserManager(BaseUserManager):
    """Custom user manager for MongoDB"""
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError('The Username field must be set')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'hr_admin')
        extra_fields.setdefault('is_approved', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    """Custom User model with role-based access"""
    
    ROLE_CHOICES = [
        ('hr_admin', 'HR Admin'),
        ('employee', 'Employee'),
    ]

    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('unspecified', 'Unspecified'),
    ]
    # Name validator: allow letters, spaces, hyphens and apostrophes — no digits
    name_regex = RegexValidator(regex=r"^[A-Za-z\s'-]+$", message="Name must contain only letters, spaces, hyphens or apostrophes (no numbers).")
    phone_regex = RegexValidator(
    regex=r'^\+?\d{10,15}$',
    message="Enter a valid phone number with 10 to 15 digits."
    )
    # Override inherited name fields to enforce validation
    first_name = models.CharField(max_length=150, blank=True, validators=[name_regex])
    last_name = models.CharField(max_length=150, blank=True, validators=[name_regex])
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    employee_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    emp_code = models.CharField(max_length=50, unique=False, null=True, blank=True)
    project_name = models.CharField(max_length=100, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    addhar_id = models.CharField(max_length=50, unique=False, null=True, blank=True)
    grade = models.CharField(max_length=20, blank=True, null=True)
    # E.164 phone number validator (optional leading +, up to 15 digits)
    phone_number = models.CharField(max_length=16, blank=True, validators=[phone_regex])
    company_email = models.EmailField(max_length=254, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True)
    date_of_joining = models.DateField(null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    middle_name = models.CharField(max_length=150, blank=True, null=True, validators=[name_regex])
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, default='unspecified', blank=True)
    
    objects = CustomUserManager()
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    def is_hr_admin(self):
        return self.role == 'hr_admin'
    
    def is_employee(self):
        return self.role == 'employee'

    def get_full_name(self):
        """Return the user's full name including middle name when present.

        Keeps a single canonical method for templates and code to call
        (overrides AbstractUser.get_full_name to include middle_name).
        """
        parts = [self.first_name or '', self.middle_name or '', self.last_name or '']
        # filter out empty parts and join with spaces
        return ' '.join([p for p in parts if p]).strip()


class EmployeeProfile(models.Model):
    """Extended profile for employees"""
    emergency_contact_regex = RegexValidator(
    regex=r'^\+?\d{10,15}$',
    message="Enter a valid phone number with 10 to 15 digits."
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    skills = models.JSONField(default=list, blank=True)
    emergency_contact = models.CharField(max_length=16, blank=True, validators=[emergency_contact_regex])
    current_address = models.TextField(blank=True)
    permanent_address = models.TextField(blank=True)
    ctc = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Optional date of birth for employees (used in HR dashboard upcoming birthdays)
    dob = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"Profile of {self.user.username}"


class LoginAttempt(models.Model):
    """Track login attempts for security"""
    
    username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField()
    success = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    user_agent = models.TextField(blank=True)
    
    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"{self.username} - {status} - {self.timestamp}"
    
    class Meta:
        ordering = ['-timestamp']


class TaxInfo(models.Model):
    """Tax information tied to a User (concrete model)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='taxinfo')
    pan_number = models.CharField(max_length=20, blank=True, null=True)
    pf_number = models.CharField(max_length=20, blank=True, null=True)
    esi_number = models.CharField(max_length=20, blank=True, null=True)
    uan_number = models.CharField(max_length=20, blank=True, null=True)
    # Benefits fields added alongside existing tax identifiers
    health_insurance_provider = models.CharField(max_length=100, blank=True, null=True)
    health_insurance_number = models.CharField(max_length=50, blank=True, null=True)
    other_benefits = models.TextField(blank=True, null=True)
    # Tax slab stored as Decimal (percent or rate). Matches HR form `tax_slab`.
    tax_slab = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"TaxInfo for {self.user.username}"

# class BenefitsInfo(models.Model):
#     """Benefits information tied to a User (concrete model)."""
#     user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='benefitsinfo')
#     health_insurance_provider = models.CharField(max_length=100, blank=True, null=True)
#     health_insurance_number = models.CharField(max_length=50, blank=True, null=True)
#     other_benefits = models.TextField(blank=True, null=True)

#     def __str__(self):
#         return f"BenefitsInfo for {self.user.username}"
    

class BankingInfo(models.Model):
    """Banking information tied to a User (concrete model)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='bankinginfo')
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    ifsc_code = models.CharField(max_length=20, blank=True, null=True)
    branch = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"BankingInfo for {self.user.username}"