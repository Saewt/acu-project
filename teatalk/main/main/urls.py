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
    
    # Chat sayfaları
    path('chat/', chat_views.chat, name='chat'),
    path('chat/<int:conversation_id>/', chat_views.chat, name='chat_with_id'),
    path('chat/<int:conversation_id>/delete/', chat_views.delete_chat, name='delete_chat'),
    path('chat/flag_session',chat_views.flag_chat_session, name='flag_chat_session'),
    path('chat/unreport_session',chat_views.unreport_chat_session, name='unreport_chat_session'),
    
    # Find psychology students and start consultation
    path('find/', login_required(chat_views.find_psych_student), name='find_psych_student'),
    path('send-request/', login_required(chat_views.send_request), name='send_request'),
    path('accept-request/', login_required(chat_views.accept_request), name='accept_request'),
    path('reject-request/', login_required(chat_views.reject_request), name='reject_request'),
    path('delete-request/', login_required(chat_views.delete_request), name='delete_request'),
   # path('psychology-home/', login_required(chat_views.psychology_student_home), name='psychology_student_home'),
    path('assign-students/', login_required(chat_views.assign_students), name='assign_students'),
    path('unassign-student/', login_required(chat_views.unassign_student), name='unassign_student'),
    # API
    path('api/send-message/', chat_views.send_message, name='send_message'),
    path('api/get-messages/', chat_views.get_messages, name='get_messages'),
    #supervisor
    path('supervisor/initiate_chat_with_student/<int:student_id>/', login_required(chat_views.supervisor_init_or_open_chat), name='initiate_supervisor_chat'),
    path('supervisor/chat_with_student/<int:session_id>/', login_required(chat_views.supervisor_student_chat_interface), name='supervisor_student_chat_interface'),
    path('supervisor/api/send_message/', chat_views.send_supervisor_message, name='send_supervisor_message'),
    path('supervisor/api/get_messages/', chat_views.get_supervisor_messages, name='get_supervisor_messages'),
    path('student/initiate_chat_with_supervisor/', login_required(chat_views.student_initiate_chat_with_supervisor), name='initiate_student_chat'),
]
