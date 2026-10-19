from django.db.models import Q
from rest_framework.permissions import BasePermission

from .models import Member, Organization


class IsAuthenticatedAndHasOrganization(BasePermission):
    message = "An active organization membership is required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        organization_id = request.headers.get("X-Organization-ID")
        organizations = Organization.objects.filter(
            Q(owner=user) | Q(members__user=user)
        ).distinct()

        if organization_id:
            try:
                organization = organizations.filter(pk=int(organization_id)).first()
            except (TypeError, ValueError):
                return False
        else:
            organization = organizations.order_by("id").first()

        if organization is None:
            return False

        request.active_organization = organization
        return True
