from rest_framework import serializers
from .models import CustomUser, Organization, Member


class CustomUserSerializer(serializers.ModelModelSerializer if hasattr(serializers, 'ModelModelSerializer') else serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'phone', 'preferred_language', 'first_name', 'last_name']
        read_only_fields = ['id']


class OrganizationSerializer(serializers.ModelSerializer):
    owner = CustomUserSerializer(read_only=True)
    spaces_count = serializers.SerializerMethodField()
    sms_balance = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'sender_id',
            'default_language', 'sms_balance', 'owner', 'spaces_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'sms_balance', 'created_at', 'updated_at']

    def get_spaces_count(self, obj):
        return obj.spaces.count()

    def get_sms_balance(self, obj):
        wallet = getattr(obj, 'wallet', None)
        if wallet is not None:
            return wallet.balance_credits
        return getattr(obj, 'sms_balance', 0)


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    organization_name = serializers.CharField(max_length=255)
    default_language = serializers.CharField(max_length=20, default='en')

    def create(self, validated_data):
        user = CustomUser.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            phone=validated_data.get('phone', ''),
            preferred_language=validated_data.get('default_language', 'en')
        )
        org = Organization.objects.create(
            owner=user,
            name=validated_data['organization_name'],
            default_language=validated_data.get('default_language', 'en'),
        )

        Member.objects.create(
            user=user,
            organization=org,
            role='admin'
        )
        return user, org


class MemberSerializer(serializers.ModelSerializer):
    user_details = CustomUserSerializer(source='user', read_only=True)

    class Meta:
        model = Member
        fields = ['id', 'user', 'user_details', 'organization', 'role', 'created']
        read_only_fields = ['id', 'created']
