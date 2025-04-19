from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import UserProfile, ChatSession, Message, PsychologyStudentProfile, ExpertiseArea, Report
from django.utils import timezone
import json

class ModelTests(TestCase):
    def setUp(self):
        # Create test users
        self.normal_user = User.objects.create_user(username='normal_user', password='password123')
        self.psych_user = User.objects.create_user(username='psych_user', password='password123')
        self.supervisor_user = User.objects.create_user(username='supervisor_user', password='password123')
        
        # Create user profiles
        self.normal_profile = UserProfile.objects.create(
            user=self.normal_user,
            is_psych_student=False,
            is_supervisor=False
        )
        
        self.psych_profile = UserProfile.objects.create(
            user=self.psych_user,
            is_psych_student=True,
            is_supervisor=False
        )
        
        self.supervisor_profile = UserProfile.objects.create(
            user=self.supervisor_user,
            is_psych_student=False,
            is_supervisor=True
        )
        
        # Set supervisor relationship
        self.psych_profile.supervisor = self.supervisor_profile
        self.psych_profile.save()
        
        # Create expertise area
        self.expertise = ExpertiseArea.objects.create(
            name="Depression",
            description="Help with depression"
        )
        
        # Create psychology student profile
        self.psych_student_profile = PsychologyStudentProfile.objects.create(
            user_profile=self.psych_profile,
            bio="Psychology student helping others",
            school_year=3,
            is_available=True
        )
        self.psych_student_profile.expertise_areas.add(self.expertise)
        
        # Create chat session
        self.chat_session = ChatSession.objects.create(
            psych_student=self.psych_profile,
            normal_user=self.normal_profile,
            is_active=True
        )
        self.chat_session.supervisor_access.add(self.supervisor_profile)
        
        # Create messages
        self.message1 = Message.objects.create(
            chat_session=self.chat_session,
            sender=self.normal_profile,
            content="Hello, I need help"
        )
        
        self.message2 = Message.objects.create(
            chat_session=self.chat_session,
            sender=self.psych_profile,
            content="Hi, I'm here to help"
        )

    def test_user_profile_model(self):
        self.assertEqual(self.normal_profile.role, "Normal User")
        self.assertEqual(self.psych_profile.role, "Psychology Student")
        self.assertEqual(self.supervisor_profile.role, "Supervisor")
        
    def test_chat_session_model(self):
        # Test unread message count
        self.assertEqual(self.chat_session.get_unread_count(self.normal_profile), 1)
        self.assertEqual(self.chat_session.get_unread_count(self.psych_profile), 1)
        
        # Test mark all read
        self.chat_session.mark_all_read(self.normal_profile)
        self.assertEqual(self.chat_session.get_unread_count(self.normal_profile), 0)
        
    def test_message_model(self):
        # Test mark as read
        self.assertFalse(self.message1.is_read)
        self.message1.mark_as_read()
        self.assertTrue(self.message1.is_read)
        self.assertIsNotNone(self.message1.read_at)
        
    def test_report_model(self):
        # Create a report
        report = Report.objects.create(
            message=self.message1,
            reported_by=self.psych_profile,
            reason_category="inappropriate",
            reason_details="This message contains inappropriate content"
        )
        
        # Test resolve method
        self.assertFalse(report.is_resolved)
        report.resolve(self.supervisor_profile, "Message was reviewed and removed")
        self.assertTrue(report.is_resolved)
        self.assertEqual(report.resolved_by, self.supervisor_profile)
        self.assertEqual(report.action_taken, "Message was reviewed and removed")

class ViewTests(TestCase):
    def setUp(self):
        # Create a client for making requests
        self.client = Client()
        
        # Create test users
        self.normal_user = User.objects.create_user(username='normal_user', password='password123')
        self.psych_user = User.objects.create_user(username='psych_user', password='password123')
        
        # Create user profiles
        self.normal_profile = UserProfile.objects.create(
            user=self.normal_user,
            is_psych_student=False,
            is_supervisor=False
        )
        
        self.psych_profile = UserProfile.objects.create(
            user=self.psych_user,
            is_psych_student=True,
            is_supervisor=False
        )
        
        # Create a chat session
        self.chat_session = ChatSession.objects.create(
            psych_student=self.psych_profile,
            normal_user=self.normal_profile,
            is_active=True
        )

    def test_register_view(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        
        # Test registration with valid data
        response = self.client.post(reverse('register'), {
            'username': 'testuser',
            'password1': 'complex_password_123',
            'password2': 'complex_password_123',
            'email': 'test@example.com'
        })
        
        # Should redirect to home on success
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='testuser').exists())
        
    def test_login_view(self):
        # Test login page
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        
        # Test login with valid credentials
        response = self.client.post(reverse('login'), {
            'username': 'normal_user',
            'password': 'password123'
        })
        
        # Should redirect to home on success
        self.assertEqual(response.status_code, 302)
        
        # Test login with invalid credentials
        response = self.client.post(reverse('login'), {
            'username': 'normal_user',
            'password': 'wrong_password'
        })
        self.assertEqual(response.status_code, 200)  # stays on login page with error
        
    def test_home_view(self):
        # Login first
        self.client.login(username='normal_user', password='password123')
        
        # Test home view
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        
        # Check if chat_sessions are in context
        self.assertIn('chat_sessions', response.context)
        
    def test_chat_view(self):
        # Login first
        self.client.login(username='normal_user', password='password123')
        
        # Test chat view with valid session_id
        response = self.client.get(reverse('chat', args=[self.chat_session.id]))
        self.assertEqual(response.status_code, 200)
        
        # Check context data
        self.assertIn('chat_session', response.context)
        self.assertIn('messages', response.context)
        self.assertIn('is_normal_user', response.context)
        self.assertTrue(response.context['is_normal_user'])
        
    def test_send_message(self):
        # Login first
        self.client.login(username='normal_user', password='password123')
        
        # Prepare message data
        message_data = {
            'session_id': self.chat_session.id,
            'content': 'Test message'
        }
        
        # Send message
        response = self.client.post(
            reverse('send_message'),
            data=json.dumps(message_data),
            content_type='application/json'
        )
        
        # Check response
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data['success'])
        
        # Check if message was created
        self.assertTrue(Message.objects.filter(
            chat_session=self.chat_session,
            sender=self.normal_profile,
            content='Test message'
        ).exists())

class FormTests(TestCase):
    def test_user_register_form(self):
        from .forms import UserRegisterForm
        
        # Test form with valid data
        form_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password_123',
            'password2': 'complex_password_123'
        }
        form = UserRegisterForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        # Test form with invalid data (password mismatch)
        form_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password_123',
            'password2': 'different_password'
        }
        form = UserRegisterForm(data=form_data)
        self.assertFalse(form.is_valid())
