from django import forms


class InnSearchForm(forms.Form):
    inn = forms.CharField(label='ИНН', min_length=10, max_length=12)

    def clean_inn(self):
        inn = self.cleaned_data['inn'].strip()
        if not inn.isdigit():
            raise forms.ValidationError('ИНН должен состоять только из цифр.')
        if len(inn) not in (10, 12):
            raise forms.ValidationError('ИНН должен содержать 10 или 12 цифр.')
        return inn
