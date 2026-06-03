from django.contrib import admin
from .models import AttendanceRecord, Leave, Overtime, AttendanceRequest

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'status', 'working_hours', 'check_in_time', 'check_out_time')
    list_filter = ('status', 'date')
    search_fields = ('user__username',)

@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ('user', 'start_date', 'end_date', 'status')
    list_filter = ('status', 'start_date')
    search_fields = ('user__username', 'reason')

@admin.register(Overtime)
class OvertimeAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'hours')
    search_fields = ('user__username',)

@admin.register(AttendanceRequest)
class AttendanceRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'request_date', 'status', 'submitted_at', 'reviewed_by')
    list_filter = ('status', 'request_date', 'submitted_at')
    search_fields = ('user__username', 'reason')
    readonly_fields = ('submitted_at', 'reviewed_at', 'reviewed_by')
    fieldsets = (
        ('Employee Info', {
            'fields': ('user', 'request_date')
        }),
        ('Request Details', {
            'fields': ('reason', 'check_in_time', 'check_out_time')
        }),
        ('Status', {
            'fields': ('status', 'rejection_reason')
        }),
        ('Review Info', {
            'fields': ('reviewed_by', 'reviewed_at', 'submitted_at')
        }),
    )
