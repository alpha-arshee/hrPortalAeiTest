from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.forms import PasswordResetForm
from django.core.exceptions import ValidationError
from .models import User, EmployeeProfile
from payroll.models import EmployeePayrollDetails
from attendance.models import LeaveQuota
from decimal import Decimal
import datetime
import logging

logger = logging.getLogger(__name__)


def _normalize_ctc(value):
    """Normalize various CTC representations into Decimal or None.

    Handles:
    - bson.decimal128.Decimal128
    - strings with curly quotes or whitespace
    - floats
    - Decimal instances (passed through)
    """
    if value is None:
        return None

    # Try to import BSON Decimal128 if available
    try:
        from bson.decimal128 import Decimal128 as BsonDecimal128
    except Exception:
        BsonDecimal128 = None

    # BSON Decimal128
    if BsonDecimal128 and isinstance(value, BsonDecimal128):
        try:
            return value.to_decimal()
        except Exception:
            try:
                return Decimal(str(value))
            except Exception:
                return None

    # Decimal already
    if isinstance(value, Decimal):
        return value

    # Float -> Decimal via string to avoid binary float issues
    if isinstance(value, float):
        try:
            return Decimal(str(value))
        except Exception:
            return None

    # String: remove common unicode quotes and commas
    if isinstance(value, str):
        # remove left/right curly quotes and non-breaking spaces
        cleaned = value.replace('\u201c', '').replace('\u201d', '').replace('\u2018', '').replace('\u2019', '')
        cleaned = cleaned.replace('\xa0', '').replace(',', '').strip()
        # also strip normal quotes
        cleaned = cleaned.strip('"\'')
        if cleaned == '':
            return None
        try:
            return Decimal(cleaned)
        except Exception:
            try:
                # fallback: cast via float
                return Decimal(str(float(cleaned)))
            except Exception:
                return None

    # Unknown type
    try:
        return Decimal(value)
    except Exception:
        return None


class UserRegistrationForm(UserCreationForm):
    """Employee registration form"""
    
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    middle_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    gender = forms.ChoiceField(
        choices=(('male','Male'),('female','Female'),('other','Other'),('unspecified','Unspecified')),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    employee_id = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    phone_number = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    department = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    date_of_joining = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
    company_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'middle_name', 'last_name', 'gender', 'email', 'employee_id',
            'phone_number', 'department', 'date_of_joining', 'profile_picture',
            'company_email',
            'password1', 'password2'
        )
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Check for existing users with this email manually to avoid djongo issues
            try:
                existing_users = list(User.objects.filter(email=email))
                if existing_users:
                    raise forms.ValidationError("A user with this email already exists.")
            except Exception:
                # If there's a database error, just continue
                pass
        return email
    
    def clean_employee_id(self):
        employee_id = self.cleaned_data.get('employee_id')
        if employee_id:
            # Check for existing users with this employee_id manually to avoid djongo issues
            try:
                existing_users = list(User.objects.filter(employee_id=employee_id))
                if existing_users:
                    raise forms.ValidationError("A user with this employee ID already exists.")
            except Exception:
                # If there's a database error, just continue
                pass
        return employee_id


class UserLoginForm(forms.Form):
    """User login form"""
    
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password',
            'id': 'id_password'
        })
    )


class ProfileUpdateForm(forms.ModelForm):
    """Profile update form for employees"""
    
    project_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    designation = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    addhar_id = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    skills = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter skills separated by commas'
        }),
        help_text='Enter skills separated by commas'
    )
    emergency_contact = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    current_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )
    permanent_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        help_text='Permanent address'
    )
    ctc = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text='Gross CTC'
    )
    company_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    dob = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )

    
    class Meta:
        model = User
        fields = (
            'first_name', 'middle_name', 'last_name', 'gender', 'email', 'phone_number',
            'department', 'profile_picture', 'addhar_id', 'company_email'
        )
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            # Provide a stable id and accept image types so the template JS
            # can reliably find and trigger the file input.
            'profile_picture': forms.FileInput(attrs={'class': 'form-control', 'id': 'id_profile_picture', 'accept': 'image/*'}),
            'company_email': forms.EmailInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        # Extract employee_profile and banking/tax objects and prepare initial values
        self.employee_profile = kwargs.pop('employee_profile', None)
        initial = kwargs.pop('initial', {}) or {}
        if self.employee_profile:
            
            initial.setdefault('emergency_contact', getattr(self.employee_profile, 'emergency_contact', ''))
            initial.setdefault('current_address', getattr(self.employee_profile, 'current_address', ''))
            initial.setdefault('permanent_address', getattr(self.employee_profile, 'permanent_address', ''))
            initial.setdefault('ctc', getattr(self.employee_profile, 'ctc', None))
            initial.setdefault('dob', getattr(self.employee_profile, 'dob', None))
            if getattr(self.employee_profile, 'skills', None):
                initial.setdefault('skills', ', '.join(self.employee_profile.skills))

        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        # populate user-level fields if instance provided (only addhar_id for employees)
        if getattr(self, 'instance', None):
            try:
                self.fields['addhar_id'].initial = getattr(self.instance, 'addhar_id', '')
            except Exception:
                pass
    
    def save(self, commit=True):
        user = super().save(commit=commit)
        
        if self.employee_profile and commit:
            self.employee_profile.emergency_contact = self.cleaned_data.get('emergency_contact', '')
            self.employee_profile.current_address = self.cleaned_data.get('current_address', '')
            self.employee_profile.permanent_address = self.cleaned_data.get('permanent_address', '')
            
            # Process skills
            skills_str = self.cleaned_data.get('skills', '')
            if skills_str:
                skills_list = [skill.strip() for skill in skills_str.split(',') if skill.strip()]
                self.employee_profile.skills = skills_list
            else:
                self.employee_profile.skills = []
            
            # Save CTC coming from the form (normalize defensively)
            try:
                raw_ctc = self.cleaned_data.get('ctc', None)
                self.employee_profile.ctc = _normalize_ctc(raw_ctc)
            except Exception:
                pass

            # Save date of birth if provided
            try:
                self.employee_profile.dob = self.cleaned_data.get('dob', None)
            except Exception as e:
                logger.exception('Failed to set employee_profile.dob: %s', e)

            self.employee_profile.save()
        # persist simple fields on user that are part of profile form
        try:
            # employees are allowed to update only addhar_id from their profile
            user.addhar_id = self.cleaned_data.get('addhar_id', '')
            if commit:
                user.save()
        except Exception:
            pass
        
        return user

    def clean_dob(self):
        dob = self.cleaned_data.get('dob')
        if dob:
            try:
                today = datetime.date.today()
                # reject today or any future date
                # if dob >= today:
                #     raise ValidationError('Date of birth must be before today.')
                # # enforce minimum age (18 years)
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                if age < 18:
                    raise ValidationError('Employee must be at least 18 years old.')
            except ValidationError:
                raise
            except Exception:
                # If dob is not a date-like object, let Django's field validation handle it
                pass
        return dob


class HRUserManagementForm(forms.ModelForm):
    """HR form for managing user accounts"""
    
    skills = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter skills separated by commas'
        })
    )
    emergency_contact = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    current_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )
    permanent_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        help_text='Permanent address'
    )
    ctc = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    dob = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    gender = forms.ChoiceField(
        choices=(('male','Male'),('female','Female'),('other','Other'),('unspecified','Unspecified')),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    company_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    # Tax fields
    pan_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    pf_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    esi_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    tax_slab = forms.DecimalField(max_digits=5, decimal_places=2, required=False, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    uan = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    health_insurance_provider = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    health_insurance_number = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    other_benefits = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    
    bank_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    account_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    ifsc_code = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    branch = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    # employee payroll details can also be edited by HR
    basic_salary = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    hra = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    special_allowances = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    conveyance_allowances = forms.DecimalField(
        max_digits=10,
        decimal_places=2,   
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    fooding_allowance = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    medical_allowance = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    education_allowance = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    transport_allowance = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    epf_contribution = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    esi_contribution = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    professional_tax = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    tds = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    pay_day = forms.DecimalField(
        max_digits=2,
        decimal_places=0,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    
    total_paid_leaves = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    total_unpaid_leaves = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    # Note: `pay_date` removed from HR form. Payroll rows are identified
    # and updated by the latest existing record; new rows are created with
    # today's date to avoid requiring the HR to provide a date.
    
    class Meta:
        model = User
        fields = (
            'first_name', 'middle_name', 'last_name', 'gender', 'email', 'employee_id',
            'phone_number', 'department', 'date_of_joining', 'is_approved',
            'is_active', 'profile_picture', 'grade', 'role',
            'project_name', 'designation', 'addhar_id','emp_code', 'company_email'
        )
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-control'}),
            'emp_code': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_joining': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_approved': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'profile_picture': forms.FileInput(attrs={'class': 'form-control'}),
            'project_name': forms.TextInput(attrs={'class': 'form-control'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'addhar_id': forms.TextInput(attrs={'class': 'form-control'}),
            'grade': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'company_email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    # Add pf_id to the form fields dynamically so HR can edit it like employee_id
    # def get_pf_field(self):
    #     # ensure pf_id is present on the user model
    #     try:
    #         self.fields['pf_id'] = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    #     except Exception:
    #         pass
    
    # def get_grade_field(self):
    #     # ensure grade is present on the user model
    #     try:
    #         self.fields['grade'] = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    #     except Exception:
    #         pass
        
        
    def __init__(self, *args, **kwargs):
        self.employee_profile = kwargs.pop('employee_profile', None)
        self.tax_info = kwargs.pop('tax_info', None)
        self.banking_info = kwargs.pop('banking_info', None)
        # Accept payroll details passed from the view. `payroll_details` may
        # be a single instance (latest) or None.
        self.payroll_details = kwargs.pop('payroll_details', None)
        super().__init__(*args, **kwargs)
        
        if self.employee_profile:
            self.fields['emergency_contact'].initial = self.employee_profile.emergency_contact
            self.fields['current_address'].initial = getattr(self.employee_profile, 'current_address', '')
            self.fields['permanent_address'].initial = getattr(self.employee_profile, 'permanent_address', '')
            self.fields['ctc'].initial = self.employee_profile.ctc
            # initialize dob for HR form as well
            self.fields['dob'].initial = getattr(self.employee_profile, 'dob', None)
            if self.employee_profile.skills:
                self.fields['skills'].initial = ', '.join(self.employee_profile.skills)
        # Initialize tax and banking fields from provided objects (if any)
        if getattr(self, 'tax_info', None):
            self.fields['pan_number'].initial = getattr(self.tax_info, 'pan_number', '')
            self.fields['pf_number'].initial = getattr(self.tax_info, 'pf_number', '')
            self.fields['esi_number'].initial = getattr(self.tax_info, 'esi_number', '')
            self.fields['tax_slab'].initial = getattr(self.tax_info, 'tax_slab', 0.0)
            self.fields['uan'].initial = getattr(self.tax_info, 'uan_number', '')
            self.fields['health_insurance_provider'].initial = getattr(self.tax_info, 'health_insurance_provider', '')
            self.fields['health_insurance_number'].initial = getattr(self.tax_info, 'health_insurance_number', '')
            self.fields['other_benefits'].initial = getattr(self.tax_info, 'other_benefits', '')
        if getattr(self, 'banking_info', None):
            self.fields['bank_name'].initial = getattr(self.banking_info, 'bank_name', '')
            self.fields['account_number'].initial = getattr(self.banking_info, 'account_number', '')
            self.fields['ifsc_code'].initial = getattr(self.banking_info, 'ifsc_code', '')
            self.fields['branch'].initial = getattr(self.banking_info, 'branch', '')

        # Initialize payroll fields from provided data. The view now typically
        # passes `payroll_pay_date` (a date) so we set the `pay_date` initial
        # value from that. If a full payroll object/queryset was passed, use it
        # to prefill all payroll fields (backwards compatibility).
        payroll_obj = None
        try:
            if self.payroll_details is not None:
                # If a queryset or list was passed, take the first (latest) record
                if hasattr(self.payroll_details, 'first'):
                    payroll_obj = self.payroll_details.first() if self.payroll_details.count() > 0 else None
                else:
                    if isinstance(self.payroll_details, (list, tuple)) and len(self.payroll_details) > 0:
                        payroll_obj = self.payroll_details[0]
                    else:
                        payroll_obj = self.payroll_details
        except Exception:
            payroll_obj = None

        if payroll_obj:
            self.fields['basic_salary'].initial = getattr(payroll_obj, 'basic_salary', None)
            self.fields['hra'].initial = getattr(payroll_obj, 'hra', None)
            self.fields['special_allowances'].initial = getattr(payroll_obj, 'special_allowances', None)
            self.fields['conveyance_allowances'].initial = getattr(payroll_obj, 'conveyance_allowances', None)
            self.fields['epf_contribution'].initial = getattr(payroll_obj, 'epf_contribution', None)
            self.fields['esi_contribution'].initial = getattr(payroll_obj, 'esi_contribution', None)
            self.fields['professional_tax'].initial = getattr(payroll_obj, 'professional_tax', None)
            self.fields['tds'].initial = getattr(payroll_obj, 'tds', None)
            self.fields['pay_day'].initial = getattr(payroll_obj, 'pay_day', None)
            self.fields['fooding_allowance'].initial = getattr(payroll_obj, 'fooding_allowance', None)
            self.fields['medical_allowance'].initial = getattr(payroll_obj, 'medical_allowance', None)
            self.fields['education_allowance'].initial = getattr(payroll_obj, 'education_allowance', None)
            self.fields['transport_allowance'].initial = getattr(payroll_obj, 'transport_allowance', None)
            self._existing_payroll = payroll_obj
            
        else:
            self._existing_payroll = None

        # Prefill leave quota fields for the current year if present
        try:
            from attendance.models import LeaveQuota
            current_year = datetime.date.today().year
            if getattr(self, 'instance', None):
                quota = LeaveQuota.objects.filter(user=self.instance, year=current_year).first()
                if quota:
                    self.fields['total_paid_leaves'].initial = getattr(quota, 'total_paid_leaves', 0)
                    self.fields['total_unpaid_leaves'].initial = getattr(quota, 'total_unpaid_leaves', 0)
        except Exception:
            # best-effort; don't break form init if attendance app or model not available
            pass
            
    def save(self, commit=True):
        user = super().save(commit=commit)
        
        if self.employee_profile and commit:
            self.employee_profile.emergency_contact = self.cleaned_data.get('emergency_contact', '')
            self.employee_profile.current_address = self.cleaned_data.get('current_address', '')
            self.employee_profile.permanent_address = self.cleaned_data.get('permanent_address', '')
            self.employee_profile.ctc = self.cleaned_data.get('ctc')
            
            # Process skills
            skills_str = self.cleaned_data.get('skills', '')
            if skills_str:
                skills_list = [skill.strip() for skill in skills_str.split(',') if skill.strip()]
                self.employee_profile.skills = skills_list
            else:
                self.employee_profile.skills = []

            # Normalize CTC coming from form (could be string/Decimal/float)
            try:
                self.employee_profile.ctc = _normalize_ctc(self.employee_profile.ctc)
            except Exception:
                pass

            # Save dob provided by HR
            try:
                self.employee_profile.dob = self.cleaned_data.get('dob', None)
            except Exception:
                pass



            self.employee_profile.save()
        # Save tax info
        try:
            tax = getattr(self, 'tax_info', None)
            if tax is None:
                from .models import TaxInfo
                tax = TaxInfo.objects.create(user=user)
            tax.pan_number = self.cleaned_data.get('pan_number', '') or None
            tax.pf_number = self.cleaned_data.get('pf_number', '') or None
            tax.esi_number = self.cleaned_data.get('esi_number', '') or None
            try:
                tax.uan_number = self.cleaned_data.get('uan', '') or None
            except Exception:
                pass
            try:
                tax.health_insurance_provider = self.cleaned_data.get('health_insurance_provider', '') or None
            except Exception:
                pass
            try:
                tax.health_insurance_number = self.cleaned_data.get('health_insurance_number', '') or None
            except Exception:
                pass
            try:
                tax.other_benefits = self.cleaned_data.get('other_benefits', '') or None
            except Exception:
                pass
            try:
                tax.tax_slab = float(self.cleaned_data.get('tax_slab') or 0.0)
            except Exception:
                tax.tax_slab = 0.0
            tax.save()
        except Exception:
            # best-effort: ignore tax save errors
            pass
        
        # Save banking info
        try:
            bank = getattr(self, 'banking_info', None)
            if bank is None:
                from .models import BankingInfo
                bank = BankingInfo.objects.create(user=user)
            bank.bank_name = self.cleaned_data.get('bank_name', '') or None
            bank.account_number = self.cleaned_data.get('account_number', '') or None
            bank.ifsc_code = self.cleaned_data.get('ifsc_code', '') or None
            bank.branch = self.cleaned_data.get('branch', '') or None
            bank.save()
        except Exception:
            # best-effort: ignore banking save errors
            pass
        # Save payroll info (create or update by pay_date)
        try:
            # No pay_date is required from the HR form. When creating a new
            # payroll row, we'll use today's date.
            pay_date_val = None

            payroll_fields = {
                'basic_salary': _normalize_ctc(self.cleaned_data.get('basic_salary')),
                'hra': _normalize_ctc(self.cleaned_data.get('hra')),
                'special_allowances': _normalize_ctc(self.cleaned_data.get('special_allowances')),
                'conveyance_allowances': _normalize_ctc(self.cleaned_data.get('conveyance_allowances')),
                    'fooding_allowance': _normalize_ctc(self.cleaned_data.get('fooding_allowance')),
                    'medical_allowance': _normalize_ctc(self.cleaned_data.get('medical_allowance')),
                    'education_allowance': _normalize_ctc(self.cleaned_data.get('education_allowance')),
                    'transport_allowance': _normalize_ctc(self.cleaned_data.get('transport_allowance')),
                'epf_contribution': _normalize_ctc(self.cleaned_data.get('epf_contribution')),
                'esi_contribution': _normalize_ctc(self.cleaned_data.get('esi_contribution')),
                'professional_tax': _normalize_ctc(self.cleaned_data.get('professional_tax')),
                'tds': _normalize_ctc(self.cleaned_data.get('tds')),
                'pay_day': _normalize_ctc(self.cleaned_data.get('pay_day')),
            }

            any_payroll_value = any(v is not None for v in payroll_fields.values())

            # Determine existing payroll row (latest) so we can update it.
            # Prefer stored `_existing_payroll` from init, otherwise attempt to look it up.
            existing = getattr(self, '_existing_payroll', None)
            if existing is None:
                try:
                    existing = EmployeePayrollDetails.objects.filter(user=user)
                except Exception:
                    existing = None
            # Only process when at least one payroll numeric field was provided
            if any_payroll_value:
                if existing:
                    try:
                        for k, v in payroll_fields.items():
                            if v is not None:
                                setattr(existing, k, v)
                        existing.save()
                    except Exception:
                        logger.exception('Failed to update existing payroll for user %s', getattr(user, 'username', 'unknown'))
                else:
                    # Create a new payroll record using today's date
                    try:
                        obj = EmployeePayrollDetails(user=user)
                        for k, v in payroll_fields.items():
                            if v is not None:
                                setattr(obj, k, v)
                        obj.save()
                    except Exception:
                        logger.exception('Failed to create payroll info for user %s', getattr(user, 'username', 'unknown'))
        except Exception:
            logger.exception('Payroll save step failed for user %s', getattr(user, 'username', 'unknown'))

        # Save leave quota for the current year if HR provided values
        try:
            paid = self.cleaned_data.get('total_paid_leaves')
            unpaid = self.cleaned_data.get('total_unpaid_leaves')
            # Only operate when either value is provided (not None)
            if paid is not None or unpaid is not None:
                from attendance.models import LeaveQuota
                year = datetime.date.today().year
                try:
                    quota, created = LeaveQuota.objects.get_or_create(user=user, year=year,
                                                                      defaults={'total_paid_leaves': paid or 0, 'total_unpaid_leaves': unpaid or 0})
                    if not created:
                        if paid is not None:
                            quota.total_paid_leaves = int(paid or 0)
                        if unpaid is not None:
                            quota.total_unpaid_leaves = int(unpaid or 0)
                        quota.save()
                except Exception:
                    logger.exception('Failed to save LeaveQuota for user %s', getattr(user, 'username', 'unknown'))
        except Exception:
            # Don't block overall save on quota errors
            logger.exception('Error while processing leave quota fields')

        return user

    def clean(self):
        """No special payroll validation required anymore; delegate to parent."""
        return super().clean()

    def clean_dob(self):
        dob = self.cleaned_data.get('dob')
        if dob:
            try:
                today = datetime.date.today()
                if dob >= today:
                    raise ValidationError('Date of birth must be before today.')
                # enforce minimum age (18 years)
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                if age < 18:
                    raise ValidationError('Employee must be at least 18 years old.')
            except ValidationError:
                raise
            except Exception:
                pass
        return dob


class CustomPasswordResetForm(PasswordResetForm):
    """Custom PasswordResetForm that avoids generating SQL constructs
    which djongo's SQL parser cannot handle. Instead of relying on a
    queryset filter that results in a bare boolean operand in SQL,
    iterate in Python and yield matching active users.
    """

    def get_users(self, email):
        """Return an iterable of active users matching the given email.

        This performs a case-insensitive match in Python to avoid djongo
        SQL->Mongo translation issues with boolean-only WHERE operands.
        """
        email = (email or '').strip().lower()
        if not email:
            return []

        users = []
        try:
            # Iterate all users and filter in Python to avoid problematic SQL
            for user in User.objects.all():
                user_email = (getattr(user, 'email', '') or '').strip().lower()
                if user_email == email and getattr(user, 'is_active', False):
                    users.append(user)
        except Exception:
            # On any DB issues, return empty list rather than raising
            return []

        return users