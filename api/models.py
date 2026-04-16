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
    MODE_CHOICES = (
        ('roleplay', 'Сюжетное собеседование'),
        ('quiz', 'Проверка знаний (Викторина)'),
    )

    # 👇 Базовые (русские) поля
    title = models.CharField(max_length=200, verbose_name="Профессия / Тема (RU)")
    description = models.TextField(blank=True, verbose_name="Описание (RU)")
    
    # 👇 НОВЫЕ АНГЛИЙСКИЕ ПОЛЯ 👇
    title_en = models.CharField(max_length=200, blank=True, null=True, verbose_name="Профессия / Тема (EN)")
    description_en = models.TextField(blank=True, null=True, verbose_name="Описание (EN)")
    
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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="history")
    template = models.ForeignKey(InterviewTemplate, on_delete=models.SET_NULL, null=True, related_name="history")
    score = models.DecimalField(max_digits=4, decimal_places=1, default=0.0)
    is_finished = models.BooleanField(default=False)
    is_failed = models.BooleanField(default=False)
    full_data_json = models.JSONField(default=dict, blank=True)
    is_deleted = models.BooleanField(default=False, verbose_name="В корзине (Soft Delete)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Последнее изменение")

    def __str__(self):
        return f"Сессия {self.user.username} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        verbose_name = "История сессии"
        verbose_name_plural = "История сессий"



        # 👇 ДОБАВЛЯЕМ В САМЫЙ НИЗ ФАЙЛА models.py 👇

from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    # Связь 1-к-1: У одного юзера ровно один профиль
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile", verbose_name="Пользователь")
    
    # Наш баланс монет. Выдаем 10 приветственных монет при регистрации.
    # БЫЛО: coins_balance = models.IntegerField(...)
    # СТАЛО:
    coins_balance = models.FloatField(default=10.0, verbose_name="Баланс монет ⚡️")

    def __str__(self):
        return f"Профиль {self.user.username} ({self.coins_balance} ⚡️)"

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

# СИГНАЛ: Автоматически создаем UserProfile, когда кто-то регистрирует нового User
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

# Сохраняем профиль при сохранении юзера
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()