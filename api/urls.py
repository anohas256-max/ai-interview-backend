from django.urls import path, include
from rest_framework.routers import DefaultRouter
# 👇 Добавили CheckUsernameView 👇

from .views import CategoryViewSet, InterviewTemplateViewSet, SessionHistoryViewSet, RegisterView, CurrentUserView, CheckUsernameView, CheckEmailView
router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="categories")
router.register("templates", InterviewTemplateViewSet, basename="templates")
router.register("history", SessionHistoryViewSet, basename="history")

urlpatterns = [
    path("", include(router.urls)),
    path("register/", RegisterView.as_view(), name="register"),
    path("users/me/", CurrentUserView.as_view(), name="current_user"),
    path("check-username/", CheckUsernameView.as_view(), name="check_username"), # 👈 Новый путь
]