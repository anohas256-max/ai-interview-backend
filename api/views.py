import requests
from django.conf import settings
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

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

class CategoryViewSet(viewsets.ModelViewSet):
    """
    CRUD операции для категорий профессий.
    Обычные пользователи могут только просматривать список (GET).
    Администраторы могут создавать, изменять и удалять (POST, PUT, DELETE).
    """
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]

class InterviewTemplateViewSet(viewsets.ModelViewSet):
    """
    Управление шаблонами интервью (пресетами профессий).
    Поддерживает фильтрацию по сфере, статусу активности и режиму.
    Доступен полнотекстовый поиск по названию и описанию.
    Удаление шаблонов является "мягким" (soft delete) — они просто скрываются.
    """
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

class SessionHistoryViewSet(viewsets.ModelViewSet):
    """
    Управление историей сессий текущего пользователя.
    Возвращает список всех проведенных интервью, включая незавершенные.
    При удалении (DELETE) применяется мягкое удаление (is_deleted=True).
    Запрещено просматривать историю чужих пользователей.
    """
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

class RegisterView(generics.CreateAPIView):
    """
    Регистрация нового пользователя.
    Ожидает username, password и email.
    Токены доступа генерируются и возвращаются сразу после успешного создания аккаунта.
    """
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

class CurrentUserView(APIView):
    """
    Получение и редактирование профиля текущего пользователя.
    GET — возвращает данные авторизованного юзера.
    PATCH — позволяет частично обновить профиль (например, изменить имя).
    """
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
    """
    Проверка занятости никнейма.
    Используется на этапе регистрации. Возвращает {"is_taken": true/false}.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        username = request.query_params.get('username', '')
        if not username:
            return Response({'is_taken': False})
        is_taken = User.objects.filter(username__iexact=username).exists()
        return Response({'is_taken': is_taken})

class CheckEmailView(APIView):
    """
    Проверка занятости email адреса.
    Используется на этапе регистрации. Возвращает {"is_taken": true/false}.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        email = request.query_params.get('email', '')
        if not email:
            return Response({'is_taken': False})
        is_taken = User.objects.filter(email__iexact=email).exists()
        return Response({'is_taken': is_taken})
    
class ChangePasswordView(APIView):
    """
    Изменение пароля пользователя.
    Требует ввода текущего (старого) пароля и нового пароля.
    В случае 5 неверных попыток клиентская часть должна блокировать доступ.
    """
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

class StartSessionView(APIView):
    """
    Инициализация новой сессии интервью.
    Списывает баланс энергии в зависимости от выбранных настроек и лимита вопросов.
    Защищено от двойного списания через transaction.atomic + select_for_update.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        data = request.data

        config = data.get("config", {})

        question_limit = int(config.get("questionLimit", 5))
        is_endless = bool(config.get("isEndlessMode", False))

        if question_limit < 1:
            return Response(
                {"error": "questionLimit must be greater than 0"},
                status=400
            )

        if question_limit > 100:
            return Response(
                {"error": "questionLimit is too large"},
                status=400
            )

        cost = 55.0 if is_endless else question_limit * 0.5

        with transaction.atomic():
            profile = user.profile.__class__.objects.select_for_update().get(user=user)

            if profile.coins_balance < cost:
                return Response(
                    {
                        "error": "not_enough_energy",
                        "message": f"Недостаточно монет. Нужно: {cost} ⚡️, у вас: {profile.coins_balance} ⚡️",
                        "required": cost,
                        "balance": profile.coins_balance,
                    },
                    status=402
                )

            profile.coins_balance -= cost
            profile.save(update_fields=["coins_balance"])

            new_session = SessionHistory.objects.create(
                user=user,
                full_data_json={
                    "config": config,
                    "messages": [],
                },
            )

        return Response({
            "message": "Сессия начата",
            "session_id": new_session.id,
            "cost": cost,
            "new_balance": profile.coins_balance,
        }, status=200)

class DailyRewardView(APIView):
    """
    Получение ежедневного бонуса (энергии).
    Работает только если баланс меньше 30.
    Защищено от двойного начисления через transaction.atomic + select_for_update.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        now = timezone.now()

        REWARD_AMOUNT = 15.0
        COOLDOWN_HOURS = 24
        MAX_BALANCE_FOR_REWARD = 30.0

        with transaction.atomic():
            profile = user.profile.__class__.objects.select_for_update().get(user=user)

            # Нельзя получать награду с большим балансом
            if profile.coins_balance >= MAX_BALANCE_FOR_REWARD:
                return Response({
                    "success": False,
                    "message": f"Daily reward available only if balance is below {MAX_BALANCE_FOR_REWARD} ⚡️",
                    "balance": profile.coins_balance,
                }, status=403)

            # Проверка кулдауна
            if profile.last_daily_reward:
                time_since_last_reward = now - profile.last_daily_reward

                if time_since_last_reward < timedelta(hours=COOLDOWN_HOURS):
                    time_left = timedelta(hours=COOLDOWN_HOURS) - time_since_last_reward

                    return Response({
                        "success": False,
                        "message": "Ежедневная награда пока недоступна.",
                        "seconds_left": int(time_left.total_seconds()),
                        "balance": profile.coins_balance,
                    }, status=200)

            # Начисление
            profile.coins_balance += REWARD_AMOUNT
            profile.last_daily_reward = now

            profile.save(update_fields=[
                "coins_balance",
                "last_daily_reward"
            ])

            return Response({
                "success": True,
                "message": f"Получено {REWARD_AMOUNT} ⚡️",
                "seconds_left": COOLDOWN_HOURS * 3600,
                "balance": profile.coins_balance,
            }, status=200)

class AddEnergyView(APIView):
    """
    Отключено.
    Пополнение баланса должно происходить только через платежный webhook.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response(
            {
                "error": "disabled",
                "message": "Manual energy top-up is disabled. Use payment flow."
            },
            status=status.HTTP_403_FORBIDDEN
        )
    

class AIChatView(APIView):
    """
    Главный шлюз для общения с нейросетью.
    Ветка 1: Если isAnalysis=True, отправляет JSON с историей чата в ИИ для выставления итогового балла.
    Ветка 2: Обрабатывает реплики пользователя, собирает системный промпт с учетом истории и передает в OpenRouter.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        session_id = data.get('sessionId')
        is_analysis = data.get('isAnalysis', False) 
        is_limit_reached = data.get('isLimitReached', False) 

        if not session_id:
            return Response({"error": "sessionId is required"}, status=400)

        try:
            session = SessionHistory.objects.get(id=session_id, user=request.user)
            full_data = session.full_data_json or {"messages": []}
            messages_history = full_data.get('messages', [])
            config = data.get('config', {}) 

            if is_analysis:
                user_message = data.get('userMessage', '')
                api_messages = [
                    {"role": "system", "content": "You are a strictly analytical AI. Return ONLY valid JSON without markdown formatting. Do NOT output conversational text."},
                    {"role": "user", "content": user_message}
                ]

                response = requests.post(
                    'https://openrouter.ai/api/v1/chat/completions',
                    headers={'Authorization': f'Bearer {settings.OPENROUTER_API_KEY}'},
                    json={"model": config.get("modelName", "google/gemini-2.0-flash-exp:free"), "messages": api_messages, "max_tokens": 4000},
                    timeout=60
                )
                response.raise_for_status()
                res_json = response.json()
                ai_text = res_json['choices'][0]['message']['content']

                session.is_finished = True
                
                import json, re
                try:
                    match = re.search(r'\{.*\}', ai_text, re.DOTALL)
                    if match:
                        parsed = json.loads(match.group(0))
                        session.score = float(parsed.get('score', 0.0))
                        full_data['analysis'] = parsed
                        session.full_data_json = full_data
                except: pass
                
                session.save()
                return Response({"text": ai_text})

            user_message = data.get('userMessage', '').strip()
            is_start_cmd = (user_message == "START_INTERVIEW")

            if not is_start_cmd:
                messages_history.append({"isUser": True, "text": user_message, "timestamp": timezone.now().isoformat()})
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

            memory_block = f"CANDIDATE NAME: {user_name}.\n" if is_eng else f"ИМЯ КАНДИДАТА: {user_name}.\n"
            
            # 👇 ОБНОВЛЕННАЯ ЛОГИКА БИОГРАФИИ (ЖЕСТКИЙ ПРИОРИТЕТ РОЛИ) 👇
            if user_bio: 
                memory_block += (
                    f"BACKGROUND BIO (Secondary context): {user_bio}. CRITICAL: The interview strictly focuses on the role/topic '{role}'. Ignore the bio if it contradicts or distracts from the main role.\n"
                ) if is_eng else (
                    f"ФОНОВАЯ БИОГРАФИЯ (Вторичный контекст): {user_bio}. КРИТИЧЕСКИ ВАЖНО: Главная тема собеседования СТРОГО '{role}'. Игнорируй навыки из биографии, если они противоречат или отвлекают от основной темы '{role}'.\n"
                )
                
            if user_legend: memory_block += f"ANSWER TO 'TELL ME ABOUT YOURSELF': {user_legend}\n" if is_eng else f"ОТВЕТ НА 'РАССКАЖИ О СЕБЕ': {user_legend}\n"
            if asked_questions: memory_block += f"TOPICS AND QUESTIONS YOU ALREADY ASKED: {' | '.join(asked_questions)}.\n" if is_eng else f"ТЕМЫ И ВОПРОСЫ, КОТОРЫЕ ТЫ УЖЕ ЗАДАВАЛ: {' | '.join(asked_questions)}.\n"

            anti_troll_rule = (
                "ANTI-TROLLING RULE: If the user is explicitly mocking, spamming incoherent nonsense (e.g. 'no', 'a', 'uh', '123'), swearing, or insulting you — you MUST respond. First, write 2-3 sentences with a strictly cold and firm refusal (point out the unacceptability of such behavior). And ONLY AFTER THIS TEXT, at the very end of the message, add the tag [FAIL]. Never send the [FAIL] tag without a textual explanation. ATTENTION: An honest admission 'I don't know' is NOT trolling, terminating the session for this is forbidden."
            ) if is_eng else (
                "ЗАЩИТА ОТ ТРОЛЛИНГА: Если пользователь откровенно издевается, спамит бессвязным бредом (например 'не', 'а', 'ы', '123'), матерится или посылает тебя — ты ОБЯЗАН ответить. Сначала напиши 2-3 предложения с максимально строгим и холодным отказом (укажи на недопустимость такого поведения). И ТОЛЬКО ПОСЛЕ ЭТОГО ТЕКСТА, в самом конце сообщения, добавь тег [FAIL]. Никогда не присылай тег [FAIL] без текстового пояснения. ВНИМАНИЕ: Честное признание 'я не знаю' — это НЕ троллинг, за это прерывать сессию запрещено."
            )

            lang_rule = (
                "CRITICAL RULE: YOU MUST SPEAK EXCLUSIVELY IN ENGLISH. ALL YOUR RESPONSES, QUESTIONS AND FEEDBACK MUST BE IN ENGLISH."
            ) if is_eng else (
                "КРИТИЧЕСКОЕ ПРАВИЛО: ТЫ ОБЯЗАН ГОВОРИТЬ ИСКЛЮЧИТЕЛЬНО НА РУССКОМ ЯЗЫКЕ. ВСЕ ТВОИ ОТВЕТЫ, ВОПРОСЫ И ФИДБЕК ДОЛЖНЫ БЫТЬ НА РУССКОМ."
            )

            if config.get('isRoleplayMode'):
                sys_inst = (
                    f"You are conducting a roleplay interview. Candidate's role: '{role}'. Difficulty: {difficulty}.\n"
                    f"Your persona: {persona}, Style: {feedback_style}.\nRULES:\n"
                    f"1. INVENT A NAME: Call yourself a suitable name. No [Your Name] placeholders!\n"
                    f"2. NATURAL SPEECH: DO NOT quote the role title word-for-word. Weave it naturally into speech.\n"
                    f"3. LORE: Questions must STRICTLY follow the universe's canon.\n4. {anti_troll_rule}\n"
                    f"5. DRILL-DOWN MODE: If the candidate answers correctly, NEVER praise them. Instead, immediately complicate the condition.\n"
                    f"6. DYNAMICS AND TOPIC CHANGE: You have a question limit. DO NOT stall on one topic for more than 2 messages! Asked -> answered -> 1 clarification -> MOVE TO A NEW TOPIC.\n"
                    f"7. {lang_rule}\n{memory_block}"
                ) if is_eng else (
                    f"Ты проводишь сюжетное собеседование. Роль кандидата: '{role}'. Уровень сложности: {difficulty}.\n"
                    f"Твой характер: {persona}, Стиль: {feedback_style}.\nПРАВИЛА:\n"
                    f"1. ПРИДУМАЙ ИМЯ: Назови себя подходящим именем. Никаких [Твоё Имя]!\n"
                    f"2. ЖИВАЯ РЕЧЬ: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО цитировать название роли буква в букву. Вплетай название в речь естественно.\n"
                    f"3. ЛОР: Вопросы должны СТРОГО соответствовать канону вселенной.\n4. {anti_troll_rule}\n"
                    f"5. РЕЖИМ «ДОЖИМ» (Drill-Down): Если кандидат отвечает правильно, НИКОГДА не хвали его. Вместо этого сразу усложни условие задачи.\n"
                    f"6. ДИНАМИКА И СМЕНА ТЕМ: У тебя лимит вопросов. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО топтаться на одной теме больше 2 сообщений! Задал вопрос -> получил ответ -> задал 1 уточнение -> СРАЗУ ПЕРЕХОДИШЬ К АБСОЛЮТНО НОВОЙ ТЕМЕ.\n"
                    f"7. {lang_rule}\n{memory_block}"
                )
            else:
                difficulty_rules = ""
                if "Легкий" in difficulty or "Junior" in difficulty: difficulty_rules = "Ask the most basic, fundamental questions. Check the foundation." if is_eng else "Задавай самые базовые, фундаментальные вопросы. Проверяй основы."
                elif "Средний" in difficulty or "Middle" in difficulty: difficulty_rules = "Ask intermediate level questions requiring understanding of processes and typical tasks." if is_eng else "Задавай вопросы среднего уровня, требующие понимания процессов, взаимосвязей и умения решать типовые задачи."
                elif "Сложный" in difficulty or "Senior" in difficulty: difficulty_rules = "Ask expert, tricky questions. Demand deep understanding of architecture and complex scenarios. Evaluate strictly." if is_eng else "Задавай экспертные, каверзные вопросы. Требуй глубокого понимания неочевидных нюансов. Оценивай максимально строго."

                sys_inst = (
                    f"You are an AI-examiner. Task: test the user's knowledge on the topic (or profession): '{role}'.\n"
                    f"Communication style: {feedback_style}.\nDIFFICULTY: {difficulty}. {difficulty_rules}\n\nRULES:\n"
                    f"1. NO ROLEPLAY: No names, greetings, or HR fluff. Get straight to business.\n"
                    f"2. DIALOG FORMAT: Ask ONE question at a time. Wait for an answer. Briefly evaluate it, correct mistakes if any, and IMMEDIATELY ask the next question.\n"
                    f"3. {anti_troll_rule}\n4. DYNAMICS: Test from different angles. Strictly change subtopics. Do not loop on one concept!\n"
                    f"5. If user says 'I don't know' - briefly explain and move on.\n6. If user asks to clarify the question - do it, do not count it as a mistake.\n"
                    f"7. {lang_rule}\n{memory_block}"
                ) if is_eng else (
                    f"Ты — нейросеть-экзаменатор. Твоя задача — проверить знания пользователя по теме (или профессии): '{role}'.\n"
                    f"Стиль общения: {feedback_style}.\nУРОВЕНЬ СЛОЖНОСТИ: {difficulty}. {difficulty_rules}\n\nПРАВИЛА:\n"
                    f"1. БЕЗ РОЛЕЙ: Никаких имен, приветствий и HR-шелухи. Переходи сразу к делу.\n"
                    f"2. ФОРМАТ ДИАЛОГА: Задавай только ОДИН вопрос за раз. Жди ответа. Получив ответ, коротко оцени его, исправь ошибку, если она есть, и СРАЗУ задай следующий вопрос.\n"
                    f"3. {anti_troll_rule}\n4. ДИНАМИКА ТЕМ: Ты должен протестировать пользователя с разных сторон темы. СТРОГО меняй подтему. Не зацикливайся на одном и том же понятии!\n"
                    f"5. Если пользователь отвечает 'не знаю' — кратко объясни суть и переходи к следующему вопросу.\n"
                    f"6. Если пользователь просит уточнить или перефразировать вопрос — сделай это, не считая за ошибку.\n"
                    f"7. {lang_rule}\n{memory_block}"
                )

            if is_limit_reached:
                if is_eng:
                    sys_inst += "\n\nCRITICAL OVERRIDE: THE INTERVIEW IS OVER. Evaluate the last answer, say goodbye, and MUST append [END] at the end of your response. DO NOT ASK ANY MORE QUESTIONS."
                else:
                    sys_inst += "\n\nКРИТИЧЕСКОЕ ПРАВИЛО: ЛИМИТ ВОПРОСОВ ИСЧЕРПАН. Оцени последний ответ, попрощайся и ОБЯЗАТЕЛЬНО добавь тег [END] в конце. НИКАКИХ НОВЫХ ВОПРОСОВ."

            api_messages = [{"role": "system", "content": sys_inst}]
            for msg in messages_history:
                api_messages.append({"role": "user" if msg.get("isUser") else "assistant", "content": msg.get("text")})

            if is_start_cmd:
                if config.get('includeLegend'):
                    start_prompt = "[SYSTEM: Greet the candidate by name, introduce yourself in your role, and ask them to briefly tell you about themselves.]" if is_eng else "[СИСТЕМНОЕ: Поздоровайся, обратившись по имени, представься в своей роли и попроси кандидата коротко рассказать о себе.]"
                else:
                    start_prompt = "[SYSTEM: Greet the candidate, introduce yourself and immediately ask the first professional question.]" if is_eng else "[СИСТЕМНОЕ: Поздоровайся, представься и сразу задай первый сложный профильный вопрос.]"
                api_messages.append({"role": "user", "content": start_prompt})

            response = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={'Authorization': f'Bearer {settings.OPENROUTER_API_KEY}'},
                json={"model": config.get("modelName", "google/gemini-2.0-flash-exp:free"), "messages": api_messages, "max_tokens": 1000},
                timeout=60
            )
            response.raise_for_status()
            res_json = response.json()
            ai_text = res_json['choices'][0]['message']['content']

            if '[END]' in ai_text: session.is_finished = True
            if '[FAIL]' in ai_text: session.is_failed = True

            messages_history.append({"isUser": False, "text": ai_text, "timestamp": timezone.now().isoformat()})
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
        
        # ==========================================
# 🛡 ТЕСТОВЫЕ ЭНДПОИНТЫ ДЛЯ RBAC (ПРАКТИКА) 🛡
# ==========================================
from .permissions import IsAdminRole, IsManagerOrAdminRole

class AdminOnlyTestView(APIView):
    """ Эндпоинт только для администраторов """
    permission_classes = [IsAdminRole]

    def get(self, request):
        return Response({"message": "СЕКРЕТНАЯ ИНФОРМАЦИЯ: Доступ разрешен. Вы — Администратор."})

class ManagerAndAdminTestView(APIView):
    """ Эндпоинт для менеджеров и администраторов """
    permission_classes = [IsManagerOrAdminRole]

    def get(self, request):
        return Response({"message": "РАБОЧАЯ ИНФОРМАЦИЯ: Доступ разрешен. Ваша роль позволяет просматривать это."})

class AllAuthTestView(APIView):
    """ Эндпоинт для любого авторизованного пользователя (User, Manager, Admin) """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"message": "ОБЩАЯ ИНФОРМАЦИЯ: Доступ разрешен. Вы успешно авторизованы."})