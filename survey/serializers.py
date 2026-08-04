from .models import Survey, SurveyQuestion, SurveyResponse
from rest_framework import serializers

class SurveyQuestionSerializer(serializers.ModelSerializer):
    responses_count = serializers.SerializerMethodField()

    class Meta:
        model = SurveyQuestion
        fields = ['id', 'survey', 'question_text', 'question_type', 'options', 'order', 'responses_count']
        read_only_fields = ['id', 'survey']

    def get_responses_count(self, obj):
        return obj.responses.count()

class SurveySerializer(serializers.ModelSerializer):
    questions = SurveyQuestionSerializer(many=True, read_only=True)
    space_name = serializers.CharField(source='space.name', read_only=True)
    total_responses = serializers.SerializerMethodField()

    class Meta:
        model = Survey
        fields = [
            'id', 'space', 'space_name', 'created_by', 'title', 
            'description', 'is_active', 'questions', 'total_responses', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_total_responses(self, obj):
        return SurveyResponse.objects.filter(survey_question__survey=obj).count()


class SurveyResponseSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='survey_question.question_text', read_only=True)

    class Meta:
        model = SurveyResponse
        fields = [
            'id', 'survey_question', 'question_text', 'user', 
            'respondent_phone', 'answer_text', 'answer_value', 'answered_at'
        ]
        read_only_fields = ['id', 'answered_at']

