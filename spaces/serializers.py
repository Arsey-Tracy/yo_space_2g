from rest_framework import serializers
from .models import Space, SpaceMember, ActiveSpaceParticipant, Broadcast, Survey, SurveyQuestion, SurveyResponse


class SpaceMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpaceMember
        fields = ['id', 'space', 'user', 'name', 'phone_number', 'role', 'joined_at']
        read_only_fields = ['id', 'space', 'joined_at']


class SpaceSerializer(serializers.ModelSerializer):
    members_count = serializers.SerializerMethodField()
    active_listeners_count = serializers.SerializerMethodField()

    class Meta:
        model = Space
        fields = [
            'id', 'organization', 'name', 'description', 'host_phone', 
            'pin', 'is_public', 'is_active', 'members_count', 
            'active_listeners_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'host_phone', 'pin', 'created_at', 'updated_at']

    def get_members_count(self, obj):
        return obj.members.count()

    def get_active_listeners_count(self, obj):
        return obj.active_participants.count()


class BroadcastSerializer(serializers.ModelSerializer):
    space_name = serializers.CharField(source='space.name', read_only=True)

    class Meta:
        model = Broadcast
        fields = [
            'id', 'space', 'space_name', 'created_by', 'message', 
            'status', 'scheduled_at', 'sent_at', 'recipients_count', 
            'cost_credits', 'created_at'
        ]
        read_only_fields = ['id', 'sent_at', 'recipients_count', 'cost_credits', 'created_at']


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


class MergeSpacesSerializer(serializers.Serializer):
    source_space_id = serializers.IntegerField()
    target_space_id = serializers.IntegerField()
    keep_source_space = serializers.BooleanField(default=False)
