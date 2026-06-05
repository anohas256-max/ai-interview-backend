from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Category, InterviewTemplate, SessionHistory, UserCustomPreset

User = get_user_model()

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug")

class InterviewTemplateSerializer(serializers.ModelSerializer):
    owner_name = serializers.ReadOnlyField(source="owner.username")
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source="category",
        write_only=True
    )
    image_url = serializers.SerializerMethodField()
    
    # 👇 Перехватываем стандартные поля 👇
    title = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    class Meta:
        model = InterviewTemplate
        fields = (
            "id", "title", "description", "is_active", "mode", # 👈 добавил mode
            "image", "image_url", "owner", "owner_name", 
            "category", "category_id", "created_at"
        )
        read_only_fields = ("id", "owner", "owner_name", "created_at", "image_url", "category")

    # 👇 Магия перевода на лету 👇
    def get_title(self, obj):
        request = self.context.get("request")
        if request and request.query_params.get("lang") == "en" and obj.title_en:
            return obj.title_en
        return obj.title

    def get_description(self, obj):
        request = self.context.get("request")
        if request and request.query_params.get("lang") == "en" and obj.description_en:
            return obj.description_en
        return obj.description

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

class SessionHistorySerializer(serializers.ModelSerializer):
    template = InterviewTemplateSerializer(read_only=True)
    template_id = serializers.PrimaryKeyRelatedField(
        queryset=InterviewTemplate.objects.all(),
        source="template",
        write_only=True,
        allow_null=True
    )

    class Meta:
        model = SessionHistory
        fields = (
            "id", "user", "template", "template_id", "score", 
            "is_finished", "is_failed", "full_data_json", "created_at"
        )
        read_only_fields = ("id", "user", "created_at", "template")

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=4)

    class Meta:
        model = User
        fields = ('username', 'password', 'email')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data.get('email', '')
        )
        return user

# 👇 ДОБАВЛЯЕМ coins_balance В СЕРИАЛИЗАТОР 👇
class UserSerializer(serializers.ModelSerializer):
    # Достаем баланс из связанной модели UserProfile
    coins_balance = serializers.IntegerField(source='profile.coins_balance', read_only=True)

    class Meta:
        model = User
        # Обязательно добавь "coins_balance" в список полей
        fields = ("id", "username", "email", "coins_balance")


class SessionConfigSerializer(serializers.Serializer):
    questionLimit = serializers.IntegerField(
        min_value=3,
        max_value=100,
        required=False,
        default=5,
    )

    isEndlessMode = serializers.BooleanField(
        required=False,
        default=False,
    )

    language = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=50,
    )

    role = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )

    difficulty = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=100,
    )

    modelName = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )


class StartSessionSerializer(serializers.Serializer):
    config = SessionConfigSerializer()

class UserCustomPresetSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCustomPreset
        fields = ("id", "mode", "title", "created_at")
        read_only_fields = ("id", "created_at")

    def validate_title(self, value):
        value = " ".join(value.strip().split())

        if len(value) < 2:
            raise serializers.ValidationError("Title is too short.")

        if len(value) > 100:
            raise serializers.ValidationError("Title is too long.")

        return value

    def validate_mode(self, value):
        if value not in ("roleplay", "quiz"):
            raise serializers.ValidationError("Invalid mode.")
        return value