from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Category, InterviewTemplate, SessionHistory

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

    class Meta:
        model = InterviewTemplate
        fields = (
            "id", "title", "description", "is_active", 
            "image", "image_url", "owner", "owner_name", 
            "category", "category_id", "created_at"
        )
        read_only_fields = ("id", "owner", "owner_name", "created_at", "image_url", "category")

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

# 👇 ОБНОВЛЕННЫЙ КЛАСС (Добавили first_name) 👇
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name') # 👈 Добавили сюда