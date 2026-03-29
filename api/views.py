from rest_framework import viewsets, permissions, generics
from rest_framework.views import APIView # 👈 Добавили для профиля
from rest_framework.response import Response # 👈 Добавили для профиля
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import AllowAny, IsAuthenticated # 👈 Добавили IsAuthenticated
from django.contrib.auth import get_user_model

from .models import Category, InterviewTemplate, SessionHistory
# 👇 Добавили UserSerializer в импорт
from .serializers import CategorySerializer, InterviewTemplateSerializer, SessionHistorySerializer, RegisterSerializer, UserSerializer
from .permissions import IsAdminOrReadOnly

User = get_user_model()

# --- КАТЕГОРИИ ---
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]

# --- ШАБЛОНЫ ИНТЕРВЬЮ ---
class InterviewTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = InterviewTemplateSerializer
    permission_classes = [IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category", "is_active", "mode"]
    search_fields = ["title", "description"]
    ordering_fields = ["price", "created_at", "title"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = InterviewTemplate.objects.select_related("owner", "category").order_by("-created_at")
        if not (self.request.user.is_authenticated and self.request.user.is_staff):
            queryset = queryset.filter(is_deleted=False)
        else:
            show_deleted = self.request.query_params.get("show_deleted")
            if show_deleted != "true":
                queryset = queryset.filter(is_deleted=False)
        return queryset

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()

# --- ИСТОРИЯ СЕССИЙ ---
class SessionHistoryViewSet(viewsets.ModelViewSet):
    serializer_class = SessionHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SessionHistory.objects.filter(
            user=self.request.user, 
            is_deleted=False
        ).select_related("template").order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()

# --- РЕГИСТРАЦИЯ ---
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

# 👇 НОВАЯ ВЬЮХА (Выдает имя текущего юзера по токену) 👇
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


        
        # 👇 НОВАЯ ВЬЮХА ДЛЯ ПРОВЕРКИ ИМЕНИ НА ЛЕТУ 👇
class CheckUsernameView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        username = request.query_params.get('username', '')
        if not username:
            return Response({'is_taken': False})
        is_taken = User.objects.filter(username__iexact=username).exists()
        return Response({'is_taken': is_taken})


        # 👇 НОВАЯ ВЬЮХА ДЛЯ ПРОВЕРКИ EMAIL НА ЛЕТУ 👇
class CheckEmailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        email = request.query_params.get('email', '')
        if not email:
            return Response({'is_taken': False})
        is_taken = User.objects.filter(email__iexact=email).exists()
        return Response({'is_taken': is_taken})