from rest_framework import permissions
from apps.comptes.models import Role


class EstCitoyen(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.CITOYEN)


class EstCollecteur(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.COLLECTEUR)


class EstOperateurTri(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.OPERATEUR_TRI)


class EstResponsableMethanisation(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.RESPONSABLE_METHANISATION)


class EstReferent(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.REFERENT)


class EstAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.role == Role.ADMINISTRATEUR or request.user.is_superuser))


class EstCapteur(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.CAPTEUR)


class EstAdminOuReferent(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            (request.user.role in [Role.ADMINISTRATEUR, Role.REFERENT] or request.user.is_superuser)
        )


class EstAdminOuResponsable(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            (request.user.role in [Role.ADMINISTRATEUR, Role.RESPONSABLE_METHANISATION] or request.user.is_superuser)
        )
