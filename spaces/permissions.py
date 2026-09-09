from rest_framework import permissions


class IsOrganizationOwner(permissions.BasePermission):
    message = "You do not have permission to access this resource"

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            # and request.user.is_organization_owner
        )

    def has_object_permission(self, request, view, obj):
        # Space

        if hasattr(obj, "organization"):
            organization = obj.organization

        elif hasattr(obj, "space"):
            organization = obj.space.organization
        else:
            return False
        return organization is not None and organization.owner_id == request.user.id
