from rest_framework import serializers

from cors.models import Tag


class TagSerializer(serializers.ModelSerializer):
    # write-only: injecte automatiquement le proprietaire a la creation
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    # protege pour eviter la creation de tags par defaut via l'API publique
    is_default = serializers.BooleanField(read_only=True)

    class Meta:
        model = Tag
        fields = "__all__"
