from example.models import Visit, Source
from django import forms
from django.db.models import Q
import django_filters

class VisitFilter(django_filters.FilterSet):
    visit_number = django_filters.NumberFilter(label='Visit #', widget=forms.NumberInput(attrs={'class': 'form-control'}))
    status = django_filters.ChoiceFilter(choices=Visit.STATUS_CHOICES, label='Status', widget=forms.Select(attrs={'class': 'form-select'}))
    source = django_filters.ModelChoiceFilter(queryset=Source.objects.filter(is_active=True), label='Source', widget=forms.Select(attrs={'class': 'form-select'}))
    name = django_filters.CharFilter(method='filter_by_name', label='Name', widget=forms.TextInput(attrs={'class': 'form-control'}))
    import_file = django_filters.CharFilter(label='Import Ref.', method='filter_by_import_file', widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Visit
        fields = ['visit_number', 'status', 'source', 'name', 'import_file']

    def filter_by_name(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(patient_name__icontains=value) |
            Q(practitioner_on_file__user__first_name__icontains=value) |
            Q(practitioner_on_file__user__last_name__icontains=value) |
            Q(performing_practitioner__user__first_name__icontains=value) |
            Q(performing_practitioner__user__last_name__icontains=value)
        )

    def filter_by_import_file(self, queryset, name, value):
        return queryset.filter(import_file__icontains=value)