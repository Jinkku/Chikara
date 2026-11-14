from django.contrib import admin

from .models import Ban, Report, StaffMember

admin.site.register(StaffMember)
admin.site.register(Report)
admin.site.register(Ban)
