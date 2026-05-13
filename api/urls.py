from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AIChatView,
    CategoryViewSet,
    InterviewTemplateViewSet,
    SessionHistoryViewSet,
    RegisterView,
    CurrentUserView,
    CheckUsernameView,
    CheckEmailView,
    ChangePasswordView,
    StartSessionView,
    DailyRewardView,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="categories")
router.register("templates", InterviewTemplateViewSet, basename="templates")
router.register("history", SessionHistoryViewSet, basename="history")

urlpatterns = [
    path("", include(router.urls)),

    path("register/", RegisterView.as_view(), name="register"),
    path("users/me/", CurrentUserView.as_view(), name="current_user"),

    path("check-username/", CheckUsernameView.as_view(), name="check_username"),
    path("check-email/", CheckEmailView.as_view(), name="check_email"),

    path("change-password/", ChangePasswordView.as_view(), name="change_password"),

    path("start-session/", StartSessionView.as_view(), name="start-session"),
    path("chat/", AIChatView.as_view(), name="ai-chat"),
    path("daily-reward/", DailyRewardView.as_view(), name="daily-reward"),
]