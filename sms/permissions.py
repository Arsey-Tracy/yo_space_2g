from rest_framework import permissions


class IsOrganizationOwner(permissions.BasePermission):
    """Allow authenticated organization owners to access their SMS records."""

    message = "You do not have permission to access this resource."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        organization = getattr(obj, "organization", None)

        if organization is None:
            space = getattr(obj, "space", None)
            organization = getattr(space, "organization", None)

        return organization is not None and organization.owner_id == request.user.id
