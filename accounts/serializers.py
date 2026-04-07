import djoser.serializers
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


class CustomUserCreateSerializer(djoser.serializers.UserCreateSerializer):
    """
    Serializer for user registration/signup via /auth/users/.
    """
    
    class Meta:
        model = User
        fields = ('id', 'email', 'password', 'first_name', 'last_name')

    def validate(self, attrs):
        attrs = super().validate(attrs)

        first_name = str(attrs.get('first_name', '')).strip()
        last_name = str(attrs.get('last_name', '')).strip()

        if not first_name:
            raise serializers.ValidationError({'first_name': 'This field is required.'})
        if not last_name:
            raise serializers.ValidationError({'last_name': 'This field is required.'})

        attrs['first_name'] = first_name
        attrs['last_name'] = last_name
        return attrs
