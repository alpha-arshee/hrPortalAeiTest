from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, EmployeeProfile, LoginAttempt


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'middle_name', 'last_name', 'gender', 'role', 'is_approved', 'is_active')
    list_filter = ('role', 'is_approved', 'is_active', 'is_staff', 'date_joined')
    search_fields = ('username', 'first_name', 'middle_name', 'last_name', 'email', 'employee_id')
    ordering = ('-date_joined',)
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Role Information', {
            'fields': ('role', 'employee_id', 'phone_number', 'department', 'hire_date', 'profile_picture', 'is_approved')
        }),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Role Information', {
            'fields': ('role', 'employee_id', 'phone_number', 'department', 'hire_date', 'is_approved')
        }),
    )


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'emergency_contact', 'ctc')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    list_filter = ('user__department',)


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('username', 'ip_address', 'success', 'timestamp')
    list_filter = ('success', 'timestamp')
    search_fields = ('username', 'ip_address')
    readonly_fields = ('username', 'ip_address', 'success', 'timestamp', 'user_agent')
    ordering = ('-timestamp',)