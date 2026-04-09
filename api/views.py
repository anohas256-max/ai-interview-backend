import requests
from django.conf import settings

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

# 👇 НОВАЯ ВЬЮХА (Выдает имя текущего юзера по токену) 👇
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    # 👇 ДОБАВЛЯЕМ ЭТОТ БЛОК 👇
    def patch(self, request):
        # partial=True значит, что мы можем обновить только имя, не трогая пароль и почту
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


        
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
    

    from django.contrib.auth import update_session_auth_hash
from rest_framework import status

from rest_framework import status

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
        
        # Строчку с update_session_auth_hash МЫ УДАЛИЛИ
        
        return Response({"message": "success"}, status=status.HTTP_200_OK)
    


class AIChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        user_message = data.get('userMessage', '')
        history = data.get('history', [])
        config = data.get('config', {})
        user_legend = data.get('userLegend', '')
        asked_questions = data.get('askedQuestions', [])

        is_eng = config.get('language') == 'English'

        # --- СОБИРАЕМ ПАМЯТЬ ---
        user_name = config.get('userName', 'User')
        memory_block = f"CANDIDATE NAME: {user_name}.\n" if is_eng else f"ИМЯ КАНДИДАТА: {user_name}.\n"

        user_bio = config.get('userBio', '')
        if user_bio:
            memory_block += f"CANDIDATE PROFILE: {user_bio}.\n" if is_eng else f"ПРОФИЛЬ КАНДИДАТА: {user_bio}.\n"

        if user_legend:
            memory_block += f"ANSWER TO 'TELL ME ABOUT YOURSELF': {user_legend}\n" if is_eng else f"ОТВЕТ НА 'РАССКАЖИ О СЕБЕ': {user_legend}\n"

        if asked_questions:
            joined_q = ' | '.join(asked_questions)
            memory_block += f"ASKED QUESTIONS (do not repeat!): {joined_q}.\n" if is_eng else f"УЖЕ ЗАДАННЫЕ ВОПРОСЫ (не повторяйся!): {joined_q}.\n"

        # --- ПРАВИЛА ---
        anti_troll = (
            "ANTI-TROLLING RULE: If user spams nonsense or insults, refuse coldly and add [FAIL] at the end." if is_eng else
            "ЗАЩИТА ОТ ТРОЛЛИНГА: Если юзер спамит бредом или оскорбляет, холодно откажи и добавь [FAIL] в конце."
        )

        lang_rule = (
            "CRITICAL RULE: YOU MUST SPEAK EXCLUSIVELY IN ENGLISH." if is_eng else
            "КРИТИЧЕСКОЕ ПРАВИЛО: ТЫ ОБЯЗАН ГОВОРИТЬ ИСКЛЮЧИТЕЛЬНО НА РУССКОМ ЯЗЫКЕ."
        )

        role = config.get('role', '')
        difficulty = config.get('difficulty', '')
        persona = config.get('persona', '')
        feedback_style = config.get('feedbackStyle', '')

        if config.get('isRoleplayMode', True):
            if is_eng:
                sys_inst = (
                    f"Roleplay interview. YOU ARE THE INTERVIEWER. Persona: '{persona}', Style: {feedback_style}. Candidate applies for: '{role}'. Diff: {difficulty}.\n"
                    f"1. Invent a name FOR YOURSELF matching your persona and introduce yourself. 2. Address the candidate by their name.\n"
                    f"3. Natural speech. 4. {lang_rule}. 5. {anti_troll}.\n"
                    "6. NEVER praise for a correct answer, just make it harder.\n"
                    "7. Max 2 messages per topic. Then change the subject.\n"
                    f"{memory_block}"
                )
            else:
                sys_inst = (
                    f"Сюжетное собеседование. ТЫ — ИНТЕРВЬЮЕР. Твой характер: '{persona}', Стиль: {feedback_style}. Кандидат пришел на должность: '{role}'. Сложность: {difficulty}.\n"
                    f"1. Придумай СЕБЕ подходящее имя (учитывая свой пол и характер) и представься. 2. Обращайся к кандидату по ЕГО имени.\n"
                    f"3. Живая речь. 4. {lang_rule}. 5. {anti_troll}.\n"
                    "6. РЕЖИМ «ДОЖИМ»: Если ответ верный, НИКОГДА не хвали, сразу усложняй.\n"
                    "7. Максимум 2 сообщения на тему! Потом меняй подтему.\n"
                    f"{memory_block}"
                )
        else:
            diff_rules = "Ask basic questions." if ("Junior" in difficulty or "Легкий" in difficulty) else ("Ask expert questions." if ("Senior" in difficulty or "Сложный" in difficulty) else "Ask intermediate questions.")
            if is_eng:
                sys_inst = f"AI-examiner for: '{role}'. {lang_rule}. Style: {feedback_style}. DIFF: {difficulty}. {diff_rules}\nFormat: 1 question at a time. {anti_troll}.\n{memory_block}"
            else:
                sys_inst = f"Экзаменатор по: '{role}'. {lang_rule}. Стиль: {feedback_style}. СЛОЖНОСТЬ: {difficulty}. {diff_rules}\nФормат: 1 вопрос за раз. {anti_troll}.\n{memory_block}"



        messages = [{"role": "system", "content": sys_inst}]

        for msg in history:
            messages.append({"role": "user" if msg.get("isUser") else "assistant", "content": msg.get("text")})
        messages.append({"role": "user", "content": user_message})

        if not getattr(settings, 'OPENROUTER_API_KEY', None):
            return Response({"error": "API key missing"}, status=500)

        try:
            response = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={'Authorization': f'Bearer {settings.OPENROUTER_API_KEY}'},
                json={"model": config.get("modelName", "google/gemini-2.5-flash"), "messages": messages, "max_tokens": 8000},
                timeout=60
            )
            response.raise_for_status()
            res_data = response.json()
            return Response({
                "text": res_data['choices'][0]['message']['content'],
                "inputTokens": res_data.get('usage', {}).get('prompt_tokens', 0),
                "outputTokens": res_data.get('usage', {}).get('completion_tokens', 0),
                "cost": res_data.get('usage', {}).get('total_cost', 0.0)
            })
        except Exception as e:
            return Response({"text": f"⚠️ Server Error: {str(e)}", "inputTokens": 0, "outputTokens": 0, "cost": 0.0})
        

        # 👇 ДОБАВЛЯЕМ В САМЫЙ НИЗ ФАЙЛА views.py 👇

from django.db import transaction

class StartSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        data = request.data
        
        # Получаем настройки из Флаттера
        config = data.get('config', {})
        question_limit = config.get('questionLimit', 5)
        
        # --- ФОРМУЛА СТОИМОСТИ ---
        # Например: 1 вопрос = 1 монета. Бесконечный режим (questionLimit=0) = 15 монет.
        cost = 15 if question_limit == 0 else question_limit

        # Используем transaction.atomic, чтобы списание монет и создание сессии 
        # произошли одновременно. Если одно упадет, второе откатится (защита от багов)
        with transaction.atomic():
            # Достаем профиль юзера
            profile = user.profile
            
            # Проверяем баланс
            if profile.coins_balance < cost:
                return Response(
                    {"error": f"Недостаточно монет. Нужно: {cost} ⚡️, у вас: {profile.coins_balance} ⚡️"}, 
                    status=402 # Payment Required
                )
            
            # Списываем монеты и сохраняем
            profile.coins_balance -= cost
            profile.save()
            
            # Создаем пустую сессию в базе
            new_session = SessionHistory.objects.create(
                user=user,
                # Сюда мы пишем только базовый конфиг, остальное заполнится по мере чата
                full_data_json={"config": config, "messages": []} 
            )

        # Отвечаем Флаттеру: Успех! Вот ID твоей новой сессии и твой новый баланс.
        return Response({
            "message": "Сессия начата",
            "session_id": new_session.id,
            "cost": cost,
            "new_balance": profile.coins_balance
        }, status=200)