from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .forms import CustomPasswordResetForm

app_name = 'accounts'

urlpatterns = [
    # Authentication URLs
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    
    path('reset_password/', auth_views.PasswordResetView.as_view(form_class=CustomPasswordResetForm), name='reset_password'),

    
    path('reset_password_sent/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),

    path('reset/<uidb64>/token/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    path('reset_password_complete/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),


    
    # Dashboard and Profile
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    
    # HR Admin URLs
    path('employees/', views.employee_management, name='employee_management'),
    path('employee/<int:user_id>/', views.edit_employee_detail, name='edit_employee_detail'),
    path('employee_detail/<int:user_id>/', views.employee_detail, name='employee_detail'),
    path('user_details/<int:user_id>/', views.user_details, name='user_details'),
    
    path('employee/<int:user_id>/approve/', views.approve_employee, name='approve_employee'),
    path('employee/<int:user_id>/reject/', views.reject_employee, name='reject_employee'),
    path('employee/<int:user_id>/delete/', views.delete_employee, name='delete_employee'),
    path('employee/<int:user_id>/reactivate/', views.reactivate_employee, name='reactivate_employee'),
    path('analytics/', views.analytics, name='analytics'),
]