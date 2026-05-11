from rest_framework import permissions
from rest_framework.permissions import BasePermission

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Разрешает чтение всем авторизованным юзерам.
    Изменение (POST, PUT, DELETE) — только админам (staff).
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS: 
            return True
        return request.user and request.user.is_authenticated and request.user.is_staff


class IsAdminRole(BasePermission):
    """ Доступ только для пользователей с ролью 'admin' в профиле """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            hasattr(request.user, 'profile') and 
            request.user.profile.role == 'admin'
        )

class IsManagerOrAdminRole(BasePermission):
    """ Доступ для ролей 'manager' и 'admin' """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            hasattr(request.user, 'profile') and 
            request.user.profile.role in ['admin', 'manager']
        )