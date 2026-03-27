from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название сферы")
    slug = models.SlugField(unique=True, verbose_name="URL-имя (slug)")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Сфера (Категория)"
        verbose_name_plural = "Сферы (Категории)"


class InterviewTemplate(models.Model):
    # 👇 1. ВАРИАНТЫ РЕЖИМОВ 👇
    MODE_CHOICES = (
        ('roleplay', 'Сюжетное собеседование'),
        ('quiz', 'Проверка знаний (Викторина)'),
    )

    title = models.CharField(max_length=200, verbose_name="Профессия / Тема")
    description = models.TextField(blank=True, verbose_name="Описание (Легенда)")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Цена (монет)") 
    
    # 👇 2. САМО ПОЛЕ 👇
    mode = models.CharField(
        max_length=20, 
        choices=MODE_CHOICES, 
        default='roleplay',
        verbose_name="Тип режима"
    )
    
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    is_deleted = models.BooleanField(default=False, verbose_name="В корзине (Soft Delete)")
    image = models.ImageField(upload_to="templates/", blank=True, null=True, verbose_name="Иконка/Обложка")
    
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="templates", verbose_name="Создатель (Admin)")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="templates", verbose_name="Сфера")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_mode_display()}] {self.title}"

    class Meta:
        verbose_name = "Шаблон интервью"
        verbose_name_plural = "Шаблоны интервью"


class SessionHistory(models.Model):
    # Модель для сохранения результатов твоих пройденных собеседований
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="history")
    template = models.ForeignKey(InterviewTemplate, on_delete=models.SET_NULL, null=True, related_name="history")
    
    score = models.DecimalField(max_digits=4, decimal_places=1, default=0.0)
    is_finished = models.BooleanField(default=False)
    is_failed = models.BooleanField(default=False)
    
    # Сюда мы будем класть ВЕСЬ лог чата и JSON аналитики
    full_data_json = models.JSONField(default=dict, blank=True)
    
    is_deleted = models.BooleanField(default=False, verbose_name="В корзине (Soft Delete)")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Сессия {self.user.username} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        verbose_name = "История сессии"
        verbose_name_plural = "История сессий"