import requests
from django.conf import settings
from django.db import transaction
from django.contrib.auth import get_user_model

from rest_framework import viewsets, permissions, generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import Category, InterviewTemplate, SessionHistory
from .serializers import (
    CategorySerializer, 
    InterviewTemplateSerializer, 
    SessionHistorySerializer, 
    RegisterSerializer, 
    UserSerializer
)
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
    ordering_fields = ["created_at", "title"]
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

# --- ПРОФИЛЬ ---
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

class CheckUsernameView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        username = request.query_params.get('username', '')
        if not username:
            return Response({'is_taken': False})
        is_taken = User.objects.filter(username__iexact=username).exists()
        return Response({'is_taken': is_taken})

class CheckEmailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        email = request.query_params.get('email', '')
        if not email:
            return Response({'is_taken': False})
        is_taken = User.objects.filter(email__iexact=email).exists()
        return Response({'is_taken': is_taken})
    
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")
        
        user = request.user

        if not user.check_password(old_password):
            return Response({"error": "current_password_incorrect"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        
        return Response({"message": "success"}, status=status.HTTP_200_OK)
    
# --- ИНТЕГРАЦИЯ С ИИ И СЕССИИ ---
class AIChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        user_message = data.get('userMessage', '')
        session_id = data.get('sessionId')

        if not session_id:
            return Response({"error": "sessionId is required"}, status=400)

        try:
            session = SessionHistory.objects.get(id=session_id, user=request.user)
            
            full_data = session.full_data_json or {"messages": []}
            messages_history = full_data.get('messages', [])
            config = data.get('config', {}) 

            # Сохраняем сообщение юзера ПРЯМО СЕЙЧАС
            messages_history.append({"isUser": True, "text": user_message, "timestamp": str(request.user.profile.user.date_joined)})
            session.full_data_json['messages'] = messages_history
            session.save()

            is_eng = config.get('language') == 'English'
            user_name = config.get('userName', 'User')
            user_bio = config.get('userBio', '')
            user_legend = data.get('userLegend', '')
            asked_questions = data.get('askedQuestions', [])
            
            persona = config.get('persona', '')
            feedback_style = config.get('feedbackStyle', '')
            role = config.get('role', '')
            difficulty = config.get('difficulty', '')

            # Выбор промпта в зависимости от режима
            if config.get('isRoleplayMode'):
                if is_eng:
                    sys_inst = f"""You are an INTERVIEWER conducting an interview for the position: '{role}'.
Your name/persona: {persona}.
Difficulty level: {difficulty}.
Feedback style: {feedback_style}.
Candidate's name: {user_name}.
Candidate's bio: {user_bio if user_bio else "Not provided"}.
Candidate's intro/legend: {user_legend if user_legend else "Not provided"}.

RULES:
1. Conduct the interview ONE QUESTION AT A TIME. DO NOT send a list of questions. Wait for the candidate's answer.
2. The questions should be technically accurate and appropriate for the specified role and difficulty.
3. Stay strictly in character ({persona}).
4. Use the specified feedback style ({feedback_style}) to react to the candidate's answers.
5. Do NOT repeat questions you have already asked. Previously asked questions: {asked_questions}.
6. CRITICAL: If the user says something completely irrelevant or hallucinates, politely steer them back or ask a clarifying question. DO NOT break character.
"""
                else:
                    sys_inst = f"""Ты — ИНТЕРВЬЮЕР, проводишь собеседование на позицию: '{role}'.
Твоя роль/характер: {persona}.
Уровень сложности: {difficulty}.
Стиль общения: {feedback_style}.
Имя кандидата: {user_name}.
Био кандидата: {user_bio if user_bio else "Не указано"}.
Легенда/вводная кандидата: {user_legend if user_legend else "Не указано"}.

ПРАВИЛА:
1. Задавай ровно ПО ОДНОМУ вопросу за раз. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдавать список вопросов. Жди ответ.
2. Вопросы должны быть технически грамотными и соответствовать роли и сложности.
3. Строго отыгрывай свою роль ({persona}).
4. Используй выбранный стиль общения ({feedback_style}) для реакции на ответы.
5. НЕ повторяй вопросы. Список уже заданных: {asked_questions}.
6. КРИТИЧНО: Если кандидат несет бред или уходит от темы, вежливо (в рамках роли) верни его к сути или задай уточняющий вопрос. Не ломай персонажа.
"""
            else:
                sys_inst = f"""You are conducting a strict knowledge QUIZ on the topic: '{role}'.
Difficulty: {difficulty}. Style: {feedback_style}. User: {user_name}.
Rule: Ask ONE clear, direct question about this topic. Wait for the answer. Grade it based on your style.""" if is_eng else f"""Ты проводишь строгий КВИЗ/Викторину по теме: '{role}'.
Сложность: {difficulty}. Стиль: {feedback_style}. Пользователь: {user_name}.
Правило: Задай ОДИН четкий вопрос по теме. Жди ответ. Оценивай строго в своем стиле."""

            # Готовим пакет сообщений
            api_messages = [{"role": "system", "content": sys_inst}]
            for msg in messages_history:
                api_messages.append({
                    "role": "user" if msg.get("isUser") else "assistant", 
                    "content": msg.get("text")
                })

            response = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={'Authorization': f'Bearer {settings.OPENROUTER_API_KEY}'},
                json={
                    "model": config.get("modelName", "google/gemini-2.0-flash-exp:free"), 
                    "messages": api_messages,
                    "max_tokens": 1000
                },
                timeout=60
            )
            response.raise_for_status()
            res_json = response.json()
            ai_text = res_json['choices'][0]['message']['content']

            # Сохраняем ответ ИИ
            messages_history.append({"isUser": False, "text": ai_text})
            session.full_data_json['messages'] = messages_history
            session.save()

            return Response({
                "text": ai_text,
                "inputTokens": res_json.get('usage', {}).get('prompt_tokens', 0),
                "outputTokens": res_json.get('usage', {}).get('completion_tokens', 0),
                "cost": res_json.get('usage', {}).get('total_cost', 0.0)
            })

        except SessionHistory.DoesNotExist:
            return Response({"error": "Session not found"}, status=404)
        except Exception as e:
            return Response({"text": f"⚠️ Server Error: {str(e)}"}, status=500)


class StartSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        data = request.data
        
        config = data.get('config', {})
        question_limit = config.get('questionLimit', 5)
        
        is_endless = config.get('isEndlessMode', False)
        cost = 55.0 if is_endless else (question_limit * 0.5)

        with transaction.atomic():
            profile = user.profile
            
            if profile.coins_balance < cost:
                return Response(
                    {"error": f"Недостаточно монет. Нужно: {cost} ⚡️, у вас: {profile.coins_balance} ⚡️"}, 
                    status=402
                )
            
            profile.coins_balance -= cost
            profile.save()
            
            new_session = SessionHistory.objects.create(
                user=user,
                full_data_json={"config": config, "messages": []} 
            )

        return Response({
            "message": "Сессия начата",
            "session_id": new_session.id,
            "cost": cost,
            "new_balance": profile.coins_balance
        }, status=200)