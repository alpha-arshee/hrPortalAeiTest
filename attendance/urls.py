from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .views import request_leave

app_name = 'attendance'

urlpatterns = [
    # Authentication URLs
    path('user_attendance_dashboard/', views.user_attendance_dashboard, name='user_attendance_dashboard'),

    # Leave request URL
    path('leave/request/', request_leave, name='leave_request'),
    path('hr/biometric_logs/', views.hr_biometric_logs_view, name='hr_biometric_logs'),
    path('hr/add_attendance/', views.hr_add_attendance, name='hr_add_attendance'),
    path('hr/mark_holiday/', views.hr_mark_holiday, name='hr_mark_holiday'),
    path('hr/employee_attendance_log/', views.employee_attendance_log_view, name='employee_attendance_log'),
    path('hr/employee/<int:user_id>/', views.employee_attendance_detail_view, name='employee_attendance_detail'),
    # HR leave requests management
    path('hr/leave_requests/', views.hr_leave_requests, name='hr_leave_requests'),
    path('hr/leave/<int:leave_id>/approve/', views.approve_leave, name='approve_leave'),
    path('hr/leave/<int:leave_id>/reject/', views.reject_leave, name='reject_leave'),
    
    # Attendance Request URLs (Employee + HR approval workflow)
    path('request/', views.request_attendance, name='request_attendance'),
    path('my_requests/', views.my_attendance_requests, name='my_attendance_requests'),
    path('hr/pending_requests/', views.pending_attendance_requests, name='pending_attendance_requests'),
    path('hr/review/<int:request_id>/', views.review_attendance_request, name='review_attendance_request'),
]