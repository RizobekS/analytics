from allauth.account.forms import LoginForm, SignupForm, ResetPasswordForm
from django import forms

BS_INPUT = {"class": "form-control", "autocomplete": "on"}

class BSLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["login"].widget = forms.EmailInput(attrs={**BS_INPUT, "placeholder": "email@domain.com"})
        self.fields["password"].widget = forms.PasswordInput(attrs={**BS_INPUT, "placeholder": "Пароль"})
        if "remember" in self.fields:
            self.fields["remember"].widget.attrs.update({"class": "form-check-input"})

class BSSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update({**BS_INPUT, "placeholder": "email@domain.com"})
        if "username" in self.fields:
            self.fields["username"].widget.attrs.update(BS_INPUT)
        self.fields["password1"].widget.attrs.update({**BS_INPUT, "placeholder": "Пароль"})
        self.fields["password2"].widget.attrs.update({**BS_INPUT, "placeholder": "Повторите пароль"})

class BSResetPasswordForm(ResetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update({**BS_INPUT, "placeholder": "email@domain.com"})
