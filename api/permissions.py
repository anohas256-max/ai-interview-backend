from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Разрешает чтение всем авторизованным юзерам.
    Изменение (POST, PUT, DELETE) — только админам (staff).
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS: # GET, HEAD, OPTIONS
            return True
        # Запись разрешена только если юзер авторизован и он админ
        return request.user and request.user.is_authenticated and request.user.is_staff