from rest_framework import status, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from account.models import Organization
from sms.views import send_bulk_sms
from .models import Survey, SurveyQuestion, SurveyResponse
from .serializers import SurveySerializer, SurveyQuestionSerializer, SurveyResponseSerializer


class SurveyViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SurveySerializer

    def get_queryset(self):
        org = Organization.objects.filter(owner=self.request.user).first()
        if org:
            return Survey.objects.filter(space__organization=org)
        return Survey.objects.none()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='add-question')
    def add_question(self, request, pk=None):
        survey = self.get_object()
        q_serializer = SurveyQuestionSerializer(data=request.data)
        if q_serializer.is_valid():
            q_serializer.save(survey=survey)
            return Response(q_serializer.data, status=status.HTTP_201_CREATED)
        return Response(q_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='send-sms')
    def send_survey_sms(self, request, pk=None):
        survey = self.get_object()
        space = survey.space
        org = space.organization
        recipients = list(space.members.values_list('phone_number', flat=True))
        
        prompt = f"Survey '{survey.title}': Dial USSD or reply with your answer to participate."
        res = send_bulk_sms(recipients, prompt, sender_id=org.sender_id if org else None, org_name=org.name if org else None)
        
        return Response({
            'message': f"Survey notifications sent to {len(recipients)} members of {space.name}.",
            'sms_result': res
        })

    @action(detail=True, methods=['get'], url_path='analytics')
    def analytics(self, request, pk=None):
        survey = self.get_object()
        questions = survey.questions.all()
        data = []

        for q in questions:
            responses = q.responses.all()
            total_r = responses.count()
            counts = {}
            for r in responses:
                val = r.answer_value or r.answer_text
                counts[val] = counts.get(val, 0) + 1

            percentages = {k: round((v / total_r) * 100, 2) for k, v in counts.items()} if total_r > 0 else {}

            data.append({
                'question_id': q.id,
                'question_text': q.question_text,
                'question_type': q.question_type,
                'total_responses': total_r,
                'breakdown': counts,
                'percentages': percentages
            })

        return Response({
            'survey_id': survey.id,
            'title': survey.title,
            'space': survey.space.name,
            'questions_analytics': data
        })
