from django.contrib import admin
from .models import EmployeePayrollDetails
# Register your models here.
@admin.register(EmployeePayrollDetails)
class EmployeePayrollDetailsAdmin(admin.ModelAdmin):
	list_display = ('user', 'basic_salary', 'hra', 'special_allowances', 'tds','professional_tax', 'epf_contribution', 'esi_contribution','pay_day')
	search_fields = ('user__username',)
	# ordering = ('-pay_date',)
	fieldsets = (
		(None, {
			'fields': ( 'basic_salary', 'hra', 'special_allowances', 'conveyance_allowances', 'tds','professional_tax', 'epf_contribution', 'esi_contribution','pay_day')
		}),
	)