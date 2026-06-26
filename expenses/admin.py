from django.contrib import admin
from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display  = ['user', 'title', 'amount', 'category', 'created_at']
    list_filter   = ['category', 'created_at']
    search_fields = ['title', 'user__username']
    ordering      = ['-created_at']
