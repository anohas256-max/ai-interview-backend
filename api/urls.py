from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AIChatView, CategoryViewSet, InterviewTemplateViewSet, SessionHistoryViewSet, 
    RegisterView, CurrentUserView, CheckUsernameView, CheckEmailView, ChangePasswordView, 
    StartSessionView, DailyRewardView, AddEnergyView,
    # 👇 ИМПОРТ НОВЫХ ТЕСТОВЫХ ВЬЮХ 👇
    AdminOnlyTestView, ManagerAndAdminTestView, AllAuthTestView
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="categories")
router.register("templates", InterviewTemplateViewSet, basename="templates")
router.register("history", SessionHistoryViewSet, basename="history")

urlpatterns = [
    path("", include(router.urls)),
    path("register/", RegisterView.as_view(), name="register"),
    path('chat/', AIChatView.as_view(), name='ai-chat'),
    path("users/me/", CurrentUserView.as_view(), name="current_user"),
    path("check-username/", CheckUsernameView.as_view(), name="check_username"),
    path("change-password/", ChangePasswordView.as_view(), name="change_password"),
    path('start-session/', StartSessionView.as_view(), name='start-session'),
    path('daily-reward/', DailyRewardView.as_view(), name='daily-reward'),
    path('add-energy/', AddEnergyView.as_view(), name='add-energy'),
    
    # 👇 ПУТИ ДЛЯ ТЕСТИРОВАНИЯ RBAC 👇
    path('rbac/admin-only/', AdminOnlyTestView.as_view(), name='rbac-admin'),
    path('rbac/manager-only/', ManagerAndAdminTestView.as_view(), name='rbac-manager'),
    path('rbac/auth-only/', AllAuthTestView.as_view(), name='rbac-auth'),
]