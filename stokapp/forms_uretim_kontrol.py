from django import forms

from .models_uretim_kontrol import (
    MEASUREMENT_METHOD_CHOICES,
    MEASUREMENT_UNIT_CHOICES,
    ProductionControlPlan,
    ProductionControlSession,
    ProductionControlStep,
)


class ProductionControlPlanForm(forms.ModelForm):
    class Meta:
        model = ProductionControlPlan
        fields = ['product', 'sub_part', 'description', 'is_active']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control', 'id': 'id_product'}),
            'sub_part': forms.Select(attrs={'class': 'form-control', 'id': 'id_sub_part'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ProductionControlStepForm(forms.ModelForm):
    class Meta:
        model = ProductionControlStep
        fields = [
            'step_no',
            'title',
            'description',
            'photo',
            'nominal_value',
            'nominal_unit',
            'plus_tolerance',
            'plus_tolerance_unit',
            'minus_tolerance',
            'minus_tolerance_unit',
            'measurement_method',
            'measurement_method_other',
            'is_required',
            'is_critical',
            'note',
        ]
        widgets = {
            'step_no': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'nominal_value': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'nominal_unit': forms.Select(attrs={'class': 'form-control'}),
            'plus_tolerance': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'plus_tolerance_unit': forms.Select(attrs={'class': 'form-control'}),
            'minus_tolerance': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'minus_tolerance_unit': forms.Select(attrs={'class': 'form-control'}),
            'measurement_method': forms.Select(attrs={'class': 'form-control'}),
            'measurement_method_other': forms.TextInput(attrs={'class': 'form-control'}),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_critical': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class ProductionControlSessionStartForm(forms.ModelForm):
    bagimsiz_kontrol = forms.BooleanField(
        required=False,
        label='Bağımsız kontrol',
        help_text='Sipariş dışı stok / serbest kontrol',
        widget=forms.CheckboxInput(attrs={'id': 'id_bagimsiz_kontrol'}),
    )

    class Meta:
        model = ProductionControlSession
        fields = [
            'order',
            'work_order',
            'control_plan',
            'inspector',
            'control_date',
            'lot_no',
            'quantity',
            'general_note',
        ]
        widgets = {
            'order': forms.Select(attrs={'class': 'form-control', 'id': 'id_order'}),
            'work_order': forms.Select(attrs={'class': 'form-control'}),
            'control_plan': forms.Select(attrs={'class': 'form-control'}),
            'inspector': forms.Select(attrs={'class': 'form-control'}),
            'control_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'lot_no': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'min': 1}),
            'general_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class MeasurementEntryForm(forms.Form):
    measured_value = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=4,
        widget=forms.NumberInput(
            attrs={'class': 'form-control uk-olcum-input', 'step': 'any', 'autocomplete': 'off'}
        ),
    )
    measured_unit = forms.ChoiceField(
        choices=MEASUREMENT_UNIT_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    measurement_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )


class RevisionNoteForm(forms.Form):
    change_note = forms.CharField(
        label='Revizyon açıklaması',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'required': True}),
    )


class ResultEditForm(forms.Form):
    measured_value = forms.DecimalField(
        required=False,
        max_digits=14,
        decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
    )
    measurement_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )
    change_note = forms.CharField(
        label='Değişiklik açıklaması',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )
