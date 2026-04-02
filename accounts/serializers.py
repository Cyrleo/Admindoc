from rest_framework import serializers
from djoser.serializers import UserCreatePasswordRetypeSerializer
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """
    Custom User serializer for Djoser /me endpoint.
    Returns complete user profile including first_name and last_name.
    """
    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'first_name',
            'last_name',
            'is_staff',
            'is_active',
            'date_joined',
            'is_verified',
        )
        read_only_fields = ('id', 'date_joined', 'is_staff', 'is_active')


class UserCreateSerializer(UserCreatePasswordRetypeSerializer):
    """
    Serializer for user registration/signup via /auth/users/.
    """
    first_name = serializers.CharField(required=True, allow_blank=False)
    last_name = serializers.CharField(required=True, allow_blank=False)
    
    class Meta:
        model = User
        fields = ('email', 'password', 're_password', 'first_name', 'last_name')
