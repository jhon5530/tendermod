from django import forms


class IndicadoresUploadForm(forms.Form):
    archivo = forms.FileField(
        label='Archivo rib.xlsx',
        help_text='Excel con indicadores financieros de la empresa (rib.xlsx)',
    )

    def clean_archivo(self):
        f = self.cleaned_data['archivo']
        if not f.name.endswith('.xlsx'):
            raise forms.ValidationError('Solo se aceptan archivos .xlsx')
        return f


class ExperienciaUploadForm(forms.Form):
    archivo = forms.FileField(
        label='Archivo experiencia_rup.xlsx',
        help_text='Excel con la experiencia RUP de la empresa (experiencia_rup.xlsx)',
    )

    def clean_archivo(self):
        f = self.cleaned_data['archivo']
        if not f.name.endswith('.xlsx'):
            raise forms.ValidationError('Solo se aceptan archivos .xlsx')
        return f
