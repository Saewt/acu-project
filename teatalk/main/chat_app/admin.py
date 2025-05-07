from django.contrib import admin
from .models import (
    UserProfile, 
    ExpertiseArea, 
    PsychologyStudentProfile, 
    ChatSession, 
    Message, 
    ChatRequest, 
    Report
)

# Register your models here.
admin.site.register(UserProfile)
admin.site.register(ExpertiseArea)
admin.site.register(PsychologyStudentProfile)
admin.site.register(ChatSession)
admin.site.register(Message)
admin.site.register(ChatRequest)
admin.site.register(Report)
