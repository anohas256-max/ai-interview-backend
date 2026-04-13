import requests
from django.conf import settings
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone

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
        # Отдаем ВСЕ не удаленные сессии (и завершенные, и нет)
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
        session_id = data.get('sessionId')
        is_analysis = data.get('isAnalysis', False) 
        is_limit_reached = data.get('isLimitReached', False) # 👈 ЛОВИМ ФЛАГ ЛИМИТА ОТ ФЛАТТЕРА

        if not session_id:
            return Response({"error": "sessionId is required"}, status=400)

        try:
            session = SessionHistory.objects.get(id=session_id, user=request.user)
            full_data = session.full_data_json or {"messages": []}
            messages_history = full_data.get('messages', [])
            config = data.get('config', {}) 

            # ==========================================
            # 🛑 ВЕТКА 1: ИЗОЛИРОВАННАЯ АНАЛИТИКА 🛑
            # ==========================================
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

            # ==========================================
            # 💬 ВЕТКА 2: ОБЫЧНЫЙ ЧАТ И СТАРТ 💬
            # ==========================================
            user_message = data.get('userMessage', '').strip()
            is_start_cmd = (user_message == "START_INTERVIEW")

            # 🛑 СОХРАНЯЕМ В БАЗУ ТОЛЬКО РЕАЛЬНЫЕ СООБЩЕНИЯ ЮЗЕРА (Старт игнорируем)
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

            # --- ВОССТАНОВЛЕНИЕ ИДЕАЛЬНОГО ПРОМПТА ИЗ GEMINI_API_SOURCE ---
            memory_block = f"CANDIDATE NAME: {user_name}.\n" if is_eng else f"ИМЯ КАНДИДАТА: {user_name}.\n"
            if user_bio: memory_block += f"CANDIDATE PROFILE: {user_bio}.\n" if is_eng else f"ПРОФИЛЬ КАНДИДАТА: {user_bio}.\n"
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

            # 🛑 ФЛАТТЕР СКАЗАЛ ЧТО ЛИМИТ ДОСТИГНУТ — МЕНЯЕМ ПРАВИЛА
            if is_limit_reached:
                if is_eng:
                    sys_inst += "\n\nCRITICAL OVERRIDE: THE INTERVIEW IS OVER. Evaluate the last answer, say goodbye, and MUST append [END] at the end of your response. DO NOT ASK ANY MORE QUESTIONS."
                else:
                    sys_inst += "\n\nКРИТИЧЕСКОЕ ПРАВИЛО: ЛИМИТ ВОПРОСОВ ИСЧЕРПАН. Оцени последний ответ, попрощайся и ОБЯЗАТЕЛЬНО добавь тег [END] в конце. НИКАКИХ НОВЫХ ВОПРОСОВ."

            api_messages = [{"role": "system", "content": sys_inst}]
            for msg in messages_history:
                api_messages.append({"role": "user" if msg.get("isUser") else "assistant", "content": msg.get("text")})

            # 🛑 ЕСЛИ ЭТО ПЕРВОЕ СООБЩЕНИЕ (СТАРТ) — ПИХАЕМ СКРЫТЫЙ ПИНОК ИИ
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