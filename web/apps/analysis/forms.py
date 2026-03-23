from django import forms


class PDFUploadForm(forms.Form):
    pdf_file = forms.FileField(
        label='PDF del pliego de condiciones',
        help_text='Suba el PDF del pliego de condiciones de la licitacion',
    )

    def clean_pdf_file(self):
        f = self.cleaned_data['pdf_file']
        if not f.name.lower().endswith('.pdf'):
            raise forms.ValidationError('Solo se aceptan archivos PDF')
        return f


class ExperienceEditForm(forms.Form):
    """
    Form A — Validacion humana de ExperienceResponse extraido del pliego.
    Los campos son pre-poblados desde session.experience_requirements_json.
    """
    listado_codigos = forms.CharField(
        label='Codigos UNSPSC (separados por coma)',
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        required=False,
        help_text='Codigos UNSPSC de 8 digitos separados por coma. Ej: 43211500, 43232202',
    )
    cantidad_codigos = forms.CharField(
        label='Cantidad de codigos',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
    )
    objeto = forms.CharField(
        label='Objeto / Alcance requerido',
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        required=False,
    )
    cantidad_contratos = forms.CharField(
        label='Cantidad de contratos a acreditar',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
    )
    valor = forms.CharField(
        label='Valor a acreditar (ej: 500 SMMLV, $100.000.000, 100% del presupuesto)',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
    )
    pagina = forms.CharField(
        label='Pagina de referencia',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
    )
    seccion = forms.CharField(
        label='Seccion del documento',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
    )
    regla_codigos = forms.ChoiceField(
        label='Regla de codigos',
        choices=[('ALL', 'Todos (AND)'), ('AT_LEAST_ONE', 'Al menos uno (OR)')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    objeto_exige_relevancia = forms.ChoiceField(
        label='El objeto exige relevancia semantica',
        choices=[
            ('SI', 'SI — el pliego exige experiencia relacionada con el objeto'),
            ('NO', 'NO — el pliego no exige relevancia'),
            ('NO_ESPECIFICADO', 'No especificado'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class IndicatorsEditForm(forms.Form):
    """
    Form B — Edicion de indicadores extraidos del pliego.
    Permite al usuario corregir nombre y valor de cada indicador antes de evaluar.
    """
    indicators_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )
