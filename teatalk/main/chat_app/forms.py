from django import forms
from django.contrib.auth.models import User
from .models import UserProfile
from django.core.exceptions import ValidationError
import re

class UserRegisterForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)
    password = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput, label='Confirm Password')
    role = forms.ChoiceField(choices=[
        ('student', 'Student'),
        ('psych_student', 'Psychology Student'),
        ('supervisor', 'Supervisor'),
    ])

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password', 'password2']
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email.endswith('@live.acibadem.edu.tr'): # contains @live.acibadem  
            raise ValidationError('Email must end with @live.acibadem.edu.tr')
            
        # E-posta zaten kullanılıyor mu kontrol et
        username = email.split('@')[0]  # @ işaretinden önceki kısmı al
        if User.objects.filter(username=username).exists() and not self.instance.pk:
            raise ValidationError('This email is already in use.')
            
        return email
    
    def clean_password2(self):
        password = self.cleaned_data.get('password')
        password2 = self.cleaned_data.get('password2')
        if password and password2 and password != password2:
            raise ValidationError('Passwords do not match')
        return password2
    
    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data['email']
        username = email.split('@')[0]  # E-postanın @ işaretinden önceki kısmını kullan
        
        user.username = username
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = email
        user.set_password(self.cleaned_data['password'])
        
        if commit:
            user.save()
            role = self.cleaned_data['role']
            
            # Create UserProfile based on role
            profile = UserProfile.objects.create(
                user=user,
                is_psych_student=(role == 'psych_student'),
                is_supervisor=(role == 'supervisor')
            )
            profile.save()
        
        return user
    
        
