from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import CustomUser, Organization, Member


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Allow login with either username or email.

    SimpleJWT's default serializer only authenticates by username. This
    normalizes the identifier (trim + lowercase) and looks up the user by
    username OR email before authenticating, so users can sign in with either.
    """

    def validate(self, attrs):
        identifier = str(attrs.get(self.username_field, '')).strip().lower()
        password = attrs.get('password', '')

        if not identifier or not password:
            raise serializers.ValidationError(
                'Must include "username" (or email) and "password".'
            )

        user = None
        # Try username first, then email.
        user = CustomUser.objects.filter(username__iexact=identifier).first()
        if user is None:
            user = CustomUser.objects.filter(email__iexact=identifier).first()

        if user is not None:
            user = authenticate(
                request=self.context.get('request'),
                username=user.username,
                password=password,
            )
        else:
            raise serializers.ValidationError(
                'No user account found. Please register an acount.',
                code='authorization'
            )

        # if user is None or not user.is_active:
        #     raise serializers.ValidationError(
        #         'No active account found with the given credentials',
        #         code='authorization',
        #     )
        

        refresh = self.get_token(user)
        data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
        return data


class CustomUserSerializer(serializers.ModelSerializer if hasattr(serializers, 'ModelModelSerializer') else serializers.ModelSerializer):
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
        # Create wallet with default 500 SMS credits for new orgs
        from wallet.models import Wallet
        Wallet.objects.create(organization=org, balance_credits=500)

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
