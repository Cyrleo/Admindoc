from rest_framework import serializers

from cors.models import Category


class CategorySerializer(serializers.ModelSerializer):
    # write-only : injecté automatiquement à la création, jamais exposé en lecture
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    # is_default est géré uniquement par les admins via l'admin Django
    is_default = serializers.BooleanField(read_only=True)

    class Meta:
        model = Category
        fields = "__all__"
