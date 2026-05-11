from django.db import models
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название сферы", help_text="Отображаемое название категории профессий")
    slug = models.SlugField(unique=True, verbose_name="URL-имя (slug)", help_text="Уникальный идентификатор для URL")

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

    title = models.CharField(max_length=200, verbose_name="Профессия / Тема (RU)", help_text="Русское название шаблона")
    description = models.TextField(blank=True, verbose_name="Описание (RU)", help_text="Детальное описание для пользователя")
    
    title_en = models.CharField(max_length=200, blank=True, null=True, verbose_name="Профессия / Тема (EN)", help_text="Английское название шаблона")
    description_en = models.TextField(blank=True, null=True, verbose_name="Описание (EN)", help_text="Английское описание")
    
    mode = models.CharField(
        max_length=20, 
        choices=MODE_CHOICES, 
        default='roleplay',
        verbose_name="Тип режима",
        help_text="Определяет логику работы ИИ (опрос или отыгрыш роли)"
    )
    
    is_active = models.BooleanField(default=True, verbose_name="Активен", help_text="Отображать ли шаблон в приложении")
    is_deleted = models.BooleanField(default=False, verbose_name="В корзине", help_text="Метка мягкого удаления")
    image = models.ImageField(upload_to="templates/", blank=True, null=True, verbose_name="Иконка", help_text="Изображение карточки")
    
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="templates", verbose_name="Создатель", help_text="Администратор, создавший шаблон")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="templates", verbose_name="Сфера", help_text="К какой категории относится")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_mode_display()}] {self.title}"

    class Meta:
        verbose_name = "Шаблон интервью"
        verbose_name_plural = "Шаблоны интервью"

class SessionHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="history", help_text="Пользователь, проходящий интервью")
    template = models.ForeignKey(InterviewTemplate, on_delete=models.SET_NULL, null=True, related_name="history", help_text="Использованный шаблон (опционально)")
    score = models.DecimalField(max_digits=4, decimal_places=1, default=0.0, help_text="Итоговый балл, выставленный ИИ")
    is_finished = models.BooleanField(default=False, help_text="Флаг успешного завершения сессии")
    is_failed = models.BooleanField(default=False, help_text="Флаг провала (например, за троллинг)")
    full_data_json = models.JSONField(default=dict, blank=True, help_text="Полная история переписки и конфиг сессии в формате JSON")
    is_deleted = models.BooleanField(default=False, verbose_name="В корзине", help_text="Метка мягкого удаления")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Время начала сессии")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Последнее изменение")

    def __str__(self):
        return f"Сессия {self.user.username} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        verbose_name = "История сессии"
        verbose_name_plural = "История сессий"

class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('admin', 'Администратор'),
        ('manager', 'Менеджер'),
        ('user', 'Пользователь'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile", verbose_name="Пользователь", help_text="Связь с базовой моделью авторизации")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user', verbose_name="Роль", help_text="Уровень доступа пользователя (RBAC)")
    coins_balance = models.FloatField(default=10.0, verbose_name="Баланс монет ⚡️", help_text="Текущее количество энергии пользователя")
    last_daily_reward = models.DateTimeField(null=True, blank=True, verbose_name="Последняя награда", help_text="Дата выдачи последнего ежедневного бонуса")

    def __str__(self):
        return f"Профиль {self.user.username} (Роль: {self.get_role_display()})"

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()