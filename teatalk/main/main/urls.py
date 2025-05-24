"""
URL configuration for main project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from chat_app import views as chat_views
from django.contrib.auth.decorators import login_required

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Ana sayfalar
    # if user is not logged in, show login page; if logged in, redirect to home
    path('', chat_views.login_view, name='login_view'),
    path('home/', login_required(chat_views.home), name='home'),
    path('register/', chat_views.register, name='register'),
    path('profile/', login_required(chat_views.profile), name='profile'),
    path('update-profile/', login_required(chat_views.update_profile), name='update_profile'),
    path('update-availability/', login_required(chat_views.update_availability), name='update_availability'),
    path('notifications/mark-as-read/', login_required(chat_views.mark_notifications_read), name='mark_notifications_read'),
    path('notifications/delete/<int:notification_id>/', login_required(chat_views.delete_notification), name='delete_notification'),
    
    # Kimlik doğrulama
    path('login/', chat_views.login_view, name='login_view'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login_view'), name='logout'),
    
    # Şifre sıfırlama
    path('password_reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html',
        email_template_name='registration/password_reset_email.html',
        subject_template_name='registration/password_reset_subject.txt'
    ), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html'
    ), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html'
    ), name='password_reset_complete'),
    
    # Chat sayfaları
    path('chat/', chat_views.chat, name='chat'),
    path('chat/<int:conversation_id>/', chat_views.chat, name='chat_with_id'),
    path('chat/<int:conversation_id>/delete/', chat_views.delete_chat, name='delete_chat'),
    
    # Find psychology students and start consultation
    path('find/', login_required(chat_views.find_psych_student), name='find_psych_student'),
    path('send-request/', login_required(chat_views.send_request), name='send_request'),
    path('accept-request/', login_required(chat_views.accept_request), name='accept_request'),
    path('reject-request/', login_required(chat_views.reject_request), name='reject_request'),
    path('delete-request/', login_required(chat_views.delete_request), name='delete_request'),
    path('psychology-home/', login_required(chat_views.psychology_student_home), name='psychology_student_home'),
    
    # API
    path('api/send-message/', chat_views.send_message, name='send_message'),
    path('api/get-messages/', chat_views.get_messages, name='get_messages'),

]
