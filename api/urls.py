from django.urls import path, include
from rest_framework.routers import DefaultRouter
# 👇 Добавили CurrentUserView 👇
from .views import CategoryViewSet, InterviewTemplateViewSet, SessionHistoryViewSet, RegisterView, CurrentUserView

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="categories")
router.register("templates", InterviewTemplateViewSet, basename="templates")
router.register("history", SessionHistoryViewSet, basename="history")

urlpatterns = [
    path("", include(router.urls)),
    path("register/", RegisterView.as_view(), name="register"),
    path("users/me/", CurrentUserView.as_view(), name="current_user"), # 👈 Новый путь
]