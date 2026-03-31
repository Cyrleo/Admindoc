from rest_framework import serializers
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


class UserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration/signup.
    """
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = ('email', 'password', 'first_name', 'last_name')
        
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user
