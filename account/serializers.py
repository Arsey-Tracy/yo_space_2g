from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import CustomUser, Member, Organization


class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "phone",
            "preferred_language",
            "first_name",
            "last_name",
        ]
        read_only_fields = ["id"]


class OrganizationSerializer(serializers.ModelSerializer):
    owner = CustomUserSerializer(read_only=True)
    spaces_count = serializers.SerializerMethodField()
    sms_balance = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "sender_id",
            "default_language",
            "sms_balance",
            "owner",
            "spaces_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "sms_balance", "created_at", "updated_at"]

    def get_spaces_count(self, obj):
        return obj.spaces.count()

    def get_sms_balance(self, obj):
        wallet = getattr(obj, "wallet", None)
        if wallet is not None:
            return wallet.balance_credits
        return getattr(obj, "sms_balance", 0)


def create_organization_for_user(user, *, name, default_language="en"):
    organization = Organization.objects.create(
        owner=user,
        name=name,
        default_language=default_language,
    )
    Member.objects.get_or_create(
        user=user,
        organization=organization,
        defaults={"role": "admin"},
    )

    from wallet.models import Wallet

    Wallet.objects.get_or_create(
        organization=organization,
        defaults={"balance_credits": 0, "cash_balance_ugx": 0},
    )
    return organization


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    default_language = serializers.ChoiceField(
        choices=CustomUser._meta.get_field("preferred_language").choices,
        default="en",
    )
    organization_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )

    def validate_email(self, value):
        normalized_email = CustomUser.objects.normalize_email(value).strip().lower()
        if CustomUser.objects.filter(email__iexact=normalized_email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return normalized_email

    def validate_username(self, value):
        username = value.strip()
        if username and CustomUser.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("This username is already in use.")
        return username

    def validate(self, attrs):
        try:
            password_validation.validate_password(attrs["password"])
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": list(error.messages)}) from error
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        email = validated_data["email"]
        username = validated_data.get("username", "").strip()
        if not username:
            base_username = slugify(email.split("@", 1)[0]).replace("-", "_")[:130] or "user"
            username = base_username
            suffix = 1
            while CustomUser.objects.filter(username__iexact=username).exists():
                username = f"{base_username[:140]}{suffix}"
                suffix += 1

        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=validated_data["password"],
            first_name=validated_data.get("first_name", "").strip(),
            last_name=validated_data.get("last_name", "").strip(),
            phone=validated_data.get("phone", ""),
            preferred_language=validated_data.get("default_language", "en"),
        )

        organization_name = validated_data.get("organization_name", "").strip()
        organization = None
        if organization_name:
            organization = create_organization_for_user(
                user,
                name=organization_name,
                default_language=validated_data.get("default_language", "en"),
            )
        return user, organization


class OrganizationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    default_language = serializers.ChoiceField(
        choices=CustomUser._meta.get_field("preferred_language").choices,
        default="en",
    )

    def create(self, validated_data):
        return create_organization_for_user(
            self.context["request"].user,
            name=validated_data["name"].strip(),
            default_language=validated_data.get("default_language", "en"),
        )


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    username = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        identifier = (
            data.get("identifier") or data.get("email") or data.get("username") or ""
        ).strip()
        password = data.get("password", "")

        if not identifier or not password:
            raise serializers.ValidationError(
                "Must provide an email address and password."
            )

        user = CustomUser.objects.filter(email__iexact=identifier).first()
        if user is None:
            user = CustomUser.objects.filter(username__iexact=identifier).first()
        authenticated_user = (
            authenticate(
                request=self.context.get("request"),
                username=user.username,
                password=password,
            )
            if user is not None
            else None
        )
        if authenticated_user is None or not authenticated_user.is_active:
            raise serializers.ValidationError(
                "Unable to log in with provided credentials."
            )

        organization = (
            Organization.objects.filter(owner=authenticated_user).order_by("id").first()
        )
        if organization is None:
            membership = (
                Member.objects.filter(user=authenticated_user)
                .select_related("organization")
                .order_by("id")
                .first()
            )
            organization = membership.organization if membership else None

        data["user"] = authenticated_user
        data["organization"] = organization
        return data


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    identifier = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        identifier = str(
            attrs.get("identifier") or attrs.get("username", "")
        ).strip()
        password = attrs.get("password", "")
        user = CustomUser.objects.filter(email__iexact=identifier).first()
        if user is None:
            user = CustomUser.objects.filter(username__iexact=identifier).first()
        authenticated_user = (
            authenticate(
                request=self.context.get("request"),
                username=user.username,
                password=password,
            )
            if user is not None
            else None
        )
        if authenticated_user is None or not authenticated_user.is_active:
            raise serializers.ValidationError(
                "Unable to log in with provided credentials.",
                code="authorization",
            )

        refresh = self.get_token(authenticated_user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": CustomUserSerializer(authenticated_user).data,
        }


class MemberSerializer(serializers.ModelSerializer):
    user_details = CustomUserSerializer(source="user", read_only=True)

    class Meta:
        model = Member
        fields = ["id", "user", "user_details", "organization", "role", "created"]
        read_only_fields = ["id", "created"]
