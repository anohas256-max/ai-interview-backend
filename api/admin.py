from django.contrib import admin
from .models import Category, InterviewTemplate, SessionHistory

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug")
    prepopulated_fields = {"slug": ("name",)} # Автоматически генерирует slug из названия
    search_fields = ("name",)

@admin.register(InterviewTemplate)
class InterviewTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "is_active", "is_deleted", "owner")
    list_filter = ("is_active", "is_deleted", "category")
    search_fields = ("title", "description")

@admin.register(SessionHistory)
class SessionHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "template", "score", "is_finished", "is_failed", "is_deleted", "created_at")
    list_filter = ("is_finished", "is_failed", "is_deleted")