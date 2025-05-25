from django.db import models
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from django.utils import timezone
from django_cryptography.fields import encrypt

def generate_anonymous_id():
    return get_random_string(length=10)

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    is_psych_student = models.BooleanField(default=False)
    is_supervisor = models.BooleanField(default=False)
    anonymous_id = models.CharField(max_length=100, unique=True, default=generate_anonymous_id)
    supervisor = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='supervised_students')
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.user.username
    
    @property
    def role(self):
        if self.is_supervisor:
            return "Supervisor"
        elif self.is_psych_student:
            return "Psychology Student"
        else:
            return "Normal User"
            
    def update_last_login(self):
        self.last_login = timezone.now()
        self.save()

class ExpertiseArea(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class PsychologyStudentProfile(models.Model):
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='psych_student_profile')
    expertise_areas = models.ManyToManyField(ExpertiseArea, blank=True)
    bio = models.TextField(blank=True, null=True)
    school_year = models.PositiveSmallIntegerField(default=1)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"Psychology Profile of {self.user_profile.user.username}"

class ChatSession(models.Model):
    psych_student = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='psych_chats', limit_choices_to={'is_psych_student': True})
    normal_user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='user_chats', limit_choices_to={'is_psych_student': False, 'is_supervisor': False})
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    last_message_time = models.DateTimeField(auto_now=True)
    supervisor_access = models.ManyToManyField(UserProfile, blank=True, related_name='supervised_chats', limit_choices_to={'is_supervisor': True})

    class Meta:
        unique_together = ('psych_student', 'normal_user')

    def __str__(self):
        return f"Chat between Psych Student {self.psych_student.anonymous_id} and User {self.normal_user.anonymous_id}"
        
    def get_unread_count(self, user_profile):
        return self.messages.filter(is_read=False).exclude(sender=user_profile).count()
        
    def mark_all_read(self, user_profile):
        self.messages.filter(is_read=False).exclude(sender=user_profile).update(
            is_read=True, 
            read_at=timezone.now()
        )
    def get_last_message(self):
        return self.messages.order_by('-timestamp').first()

class Message(models.Model):
    chat_session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    content = encrypt(models.TextField())
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    is_flagged = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    is_system_message = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Message from {self.sender.anonymous_id} in chat {self.chat_session.id}"
        
    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

class ChatRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    )
    
    normal_user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='sent_requests')
    psych_student = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='received_requests')
    issue_description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    def __str__(self):
        return f"Request from {self.normal_user.anonymous_id} to {self.psych_student.anonymous_id}"

class Report(models.Model):
    REPORT_REASONS = [
        ('inappropriate', 'Inappropriate Content'),
        ('harassment', 'Harassment'),
        ('spam', 'Spam'),
        ('other', 'Other'),
    ]
    
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reports')
    reported_by = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    reason_category = models.CharField(max_length=20, choices=REPORT_REASONS, default='other')
    reason_details = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_reports')
    resolved_at = models.DateTimeField(null=True, blank=True)
    action_taken = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Report for message {self.message.id} by {self.reported_by.anonymous_id}"
        
    def resolve(self, resolver, action_taken=None):
        self.is_resolved = True
        self.resolved_by = resolver
        self.resolved_at = timezone.now()
        self.action_taken = action_taken
        self.save()
class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('message', 'Message'),
        ('request', 'Request'),
        ('report', 'Report'),
        ('other', 'Other'),
    ]
    receiver = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='other')

    def __str__(self):
        return f"Notification for {self.receiver.anonymous_id}"

# Create your models here.
