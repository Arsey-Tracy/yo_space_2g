from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ContactMessage
from .serializers import ContactMessageSerializer


class ContactMessageCreateView(APIView):
    """Public endpoint for the contact form.

    AllowAny — anyone (with or without an account) can submit a message.
    Only the create action is exposed publicly; listing/reading messages is
    intentionally not available here.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"detail": "Message received. Our team will get back to you within 24 hours."},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

