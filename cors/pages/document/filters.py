from datetime import date, timedelta

import django_filters

from cors.models import Document


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    pass


class DocumentFilter(django_filters.FilterSet):
    category = NumberInFilter(field_name="category_id", lookup_expr="in")
    categories = NumberInFilter(field_name="category_id", lookup_expr="in")
    tag = NumberInFilter(field_name="tags__id", lookup_expr="in")
    tags = NumberInFilter(field_name="tags__id", lookup_expr="in")

    expiration_from = django_filters.DateFilter(
        field_name="date_expiration", lookup_expr="gte"
    )
    expiration_to = django_filters.DateFilter(
        field_name="date_expiration", lookup_expr="lte"
    )
    no_expiration = django_filters.BooleanFilter(
        field_name="date_expiration", lookup_expr="isnull"
    )

    expiration_month = django_filters.CharFilter(method="filter_expiration_month")
    expires_in_days = django_filters.NumberFilter(method="filter_expires_in_days")
    expired = django_filters.BooleanFilter(method="filter_expired")

    class Meta:
        model = Document
        fields = []

    def filter_expiration_month(self, queryset, _name, value):
        try:
            year_str, month_str = value.split("-", 1)
            year = int(year_str)
            month = int(month_str)
            if not (1 <= month <= 12):
                return queryset
            return queryset.filter(date_expiration__year=year, date_expiration__month=month)
        except (ValueError, TypeError):
            return queryset

    def filter_expires_in_days(self, queryset, _name, value):
        if value is None:
            return queryset
        try:
            days = int(value)
        except (TypeError, ValueError):
            return queryset

        if days < 0:
            return queryset.none()

        today = date.today()
        limit = today + timedelta(days=days)
        return queryset.filter(date_expiration__gte=today, date_expiration__lte=limit)

    def filter_expired(self, queryset, _name, value):
        if value is True:
            return queryset.filter(date_expiration__lt=date.today())
        if value is False:
            return queryset.filter(date_expiration__gte=date.today())
        return queryset
