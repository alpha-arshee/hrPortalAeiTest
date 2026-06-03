from django.urls import path
from . import views

app_name = 'payroll'

urlpatterns = [
    path('dashboard/', views.user_payroll_dashboard, name='user_payroll_dashboard'),
    
    path('hr/dashboard/', views.hr_payroll_dashboard, name='hr_payroll_dashboard'),
    
    path('advance-request/', views.advance_salary_request_view, name='advance_salary_request'),

    # Employee payroll list
    path('list/', views.list_employee_payrolls, name='employee_payroll_list'),
    path('generate/<int:payroll_id>/', views.generate_payroll, name='generate_payroll'),
    path('salary-slip/<int:gen_id>/download/', views.salary_slip_download, name='salary_slip_download'),
    path('overtime-for-month/', views.overtime_for_month, name='overtime_for_month'),
    path('present-absent/', views.present_absent_for_month, name='present_absent_for_month'),

    # HR
    path('hr/requests/', views.hr_requests_list, name='hr_requests_list'),
    path('hr/request/<int:request_id>/approve/', views.approve_request, name='approve_request'),
    path('hr/request/<int:request_id>/reject/', views.reject_request, name='reject_request'),
    path('request/<int:request_id>/status/', views.advance_request_status, name='advance_request_status'),
    
    path('salary-slip/', views.salary_slip_view, name='salary_slip_view'),
    
    
]
