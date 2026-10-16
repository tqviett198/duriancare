from django.contrib import admin

from .models import Payment, Sale, SaleLine

admin.site.register(Sale)
admin.site.register(SaleLine)
admin.site.register(Payment)
