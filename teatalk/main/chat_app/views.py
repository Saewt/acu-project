from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from .forms import UserRegisterForm
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth.models import User
from .models import UserProfile, Message, ChatSession, PsychologyStudentProfile, ExpertiseArea, Report, ChatRequest, Notification
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q
from django.contrib import messages

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            email = form.cleaned_data.get('email')
            username = email.split('@')[0]
            raw_password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=raw_password)
            login(request, user)
            return redirect('home')
    else:
        form = UserRegisterForm()
    return render(request, 'chat_app/register.html', {'form': form})


def login_view(request):
    # If the user is already authenticated, redirect to home page
    if request.user.is_authenticated:
        return redirect('home')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # If the username appears to be an email, extract just the username part
        if username and '@' in username:
            username = username.split('@')[0]
        
        user = authenticate(username=username, password=password)
        
        if user is not None:
            login(request, user)
            try:
                profile = UserProfile.objects.get(user=user)
                profile.update_last_login()
                
                if profile.is_psych_student:
                    return redirect('psychology_student_home')
            except UserProfile.DoesNotExist:
                pass
            return redirect('home')
        else:
            form = AuthenticationForm(request, data={
                'username': request.POST.get('username'),
                'password': request.POST.get('password')
            })
            form.is_valid()  # This will populate the errors
            return render(request, 'chat_app/login.html', {'form': form})
    else:
        form = AuthenticationForm()
    
    return render(request, 'chat_app/login.html', {'form': form})

@login_required
def home(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        unread_notifications = Notification.objects.filter(receiver=user_profile, is_read=False).order_by('-created_at')
        all_notifications = Notification.objects.filter(receiver=user_profile).order_by('-created_at')
        
        if user_profile.is_psych_student:
            return redirect('psychology_student_home')
        
        if user_profile.is_supervisor:
            supervised_students = UserProfile.objects.filter(supervisor=user_profile)
            active_conversations = ChatSession.objects.filter(
                Q(psych_student__in=supervised_students) | 
                Q(supervisor_access=user_profile)
            ).distinct().order_by('-last_message_time')
        else:
            active_conversations = ChatSession.objects.filter(normal_user=user_profile, is_active=True).order_by('-last_message_time')
            ended_conversations = ChatSession.objects.filter(normal_user=user_profile, is_active=False).order_by('-last_message_time')

        for session in active_conversations:
            session.unread_count = session.get_unread_count(user_profile)
        
        pending_requests = []
        if not user_profile.is_supervisor:
            pending_requests = ChatRequest.objects.filter(
                normal_user=user_profile,
                status='pending'
            ).order_by('-created_at')
        
        return render(request, 'chat_app/home.html', {
            'active_conversations': active_conversations,
            'ended_conversations': ended_conversations if 'ended_conversations' in locals() else [],
            'user_profile': user_profile,
            'pending_requests': pending_requests,
            'notifications': all_notifications,
            'unread_notifications': unread_notifications,
            'unread_notification_count': unread_notifications.count()
        })
        
    except UserProfile.DoesNotExist:
        return render(request, 'chat_app/home.html', {'error': 'User profile not found'})

@login_required
def chat(request, conversation_id=None):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        
        if conversation_id:
            chat_session = get_object_or_404(ChatSession, id=conversation_id)
            
            is_participant = (chat_session.psych_student == user_profile or 
                             chat_session.normal_user == user_profile)
            
            is_supervisor_with_access = (user_profile.is_supervisor and (
                chat_session.psych_student.supervisor == user_profile or
                chat_session.supervisor_access.filter(id=user_profile.id).exists()
            ))
            
            if not (is_participant or is_supervisor_with_access):
                return redirect('home')
                
            if is_participant:  # Only mark as read if actual participant (not supervisor)
                chat_session.mark_all_read(user_profile)
        else:
            # For demo purposes, redirect to home if no conversation_id provided
            return redirect('home')
        
        messages = chat_session.messages.order_by('timestamp')
        
        is_psych_student = (user_profile == chat_session.psych_student)
        is_normal_user = (user_profile == chat_session.normal_user)
        is_supervisor = user_profile.is_supervisor
        
        return render(request, 'chat_app/chat.html', {
            'chat_session': chat_session,
            'messages': messages,
            'user_profile': user_profile,
            'is_psych_student': is_psych_student,
            'is_normal_user': is_normal_user,
            'is_supervisor': is_supervisor,
            'conversation_id': conversation_id
        })
        
    except UserProfile.DoesNotExist:
        return render(request, 'chat_app/chat.html', {'error': 'User profile not found'})

@login_required
@csrf_exempt
def send_message(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
    try:
        # Extract data from request
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            conversation_id = data.get('conversation_id')
            content = data.get('content', data.get('message'))
        else:
            conversation_id = request.POST.get('conversation_id')
            content = request.POST.get('content', request.POST.get('message'))
        
        # Validation
        if not conversation_id:
            return JsonResponse({'error': 'Missing conversation_id parameter'}, status=400)
        if not content:
            return JsonResponse({'error': 'Missing message content'}, status=400)
        
        # Get user profile
        try:
            user_profile = UserProfile.objects.get(user=request.user)
        except UserProfile.DoesNotExist:
            return JsonResponse({'error': 'User profile not found'}, status=400)
        
        # Get chat session and check permission
        try:
            chat_session = ChatSession.objects.get(id=conversation_id)
            is_participant = (chat_session.psych_student == user_profile or 
                            chat_session.normal_user == user_profile)
            
            if not is_participant:
                return JsonResponse({'error': 'Not authorized'}, status=403)
            
            # Create and save the message
            message = Message.objects.create(
                chat_session=chat_session,
                sender=user_profile,
                content=content
            )
            chat_session.save()
            
            # Format timestamp for response
            timestamp = message.timestamp.isoformat()
            if '+' in timestamp:
                timestamp = timestamp.replace('+00:00', 'Z')
            
            return JsonResponse({
                'success': True,
                'message_id': message.id,
                'sender_id': user_profile.id,
                'sender_anonymous_id': user_profile.anonymous_id,
                'timestamp': timestamp
            })
            
        except ChatSession.DoesNotExist:
            return JsonResponse({'error': 'Chat session not found'}, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
    
@login_required
def get_messages(request):
    conversation_id = request.GET.get('conversation_id')
    since = request.GET.get('since', '0')
    
    if not conversation_id:
        return JsonResponse({'error': 'Missing conversation_id'}, status=400)
    
    try:
        # Get user and chat session
        user_profile = UserProfile.objects.get(user=request.user)
        chat_session = ChatSession.objects.get(id=conversation_id)
        
        # Check permissions
        is_participant = (chat_session.psych_student == user_profile or 
                         chat_session.normal_user == user_profile)
        is_supervisor = (user_profile.is_supervisor and (
            chat_session.psych_student.supervisor == user_profile or
            chat_session.supervisor_access.filter(id=user_profile.id).exists()
        ))
        
        if not (is_participant or is_supervisor):
            return JsonResponse({'error': 'Not authorized'}, status=403)
        
        # Get unread messages
        all_unread_messages = None
        if is_participant:
            all_unread_messages = chat_session.messages.filter(
                is_read=False
            ).exclude(sender=user_profile)
        
        # Get messages based on timestamp
        if since != '0':
            since_time = parse_timestamp(since)
            if since_time:
                # Get recent messages and messages newer than timestamp
                recent_messages = list(chat_session.messages.order_by('-timestamp')[:20])
                new_messages = list(chat_session.messages.filter(
                    timestamp__gt=since_time
                ).order_by('timestamp'))
                
                # Combine both lists without duplicates
                message_ids = set(m.id for m in recent_messages + new_messages)
                messages = chat_session.messages.filter(id__in=message_ids).order_by('timestamp')
            else:
                messages = chat_session.messages.order_by('timestamp')
        else:
            # No timestamp - get latest messages
            messages = chat_session.messages.order_by('timestamp')
        
        # Limit to 50 messages
        messages_list = list(messages[:50])
        
        # Format the messages for JSON response
        messages_data = []
        for msg in messages_list:
            messages_data.append({
                'id': msg.id,
                'content': msg.content,
                'sender_id': msg.sender.id,
                'sender_anonymous_id': msg.sender.anonymous_id,
                'is_current_user': msg.sender == user_profile,
                'timestamp': msg.timestamp.isoformat(),
                'is_flagged': msg.is_flagged
            })
        
        # Mark messages as read
        if is_participant and all_unread_messages:
            all_unread_messages.update(is_read=True, read_at=timezone.now())
        
        # Generate current timestamp
        current_time = timezone.now().isoformat()
        if '+' in current_time:
            current_time = current_time.replace('+00:00', 'Z')
        
        return JsonResponse({
            'messages': messages_data,
            'last_time': current_time,
            'server_time': timezone.now().timestamp(),
            'debug_info': {
                'since': since,
                'message_count': len(messages_data),
                'unread_count': all_unread_messages.count() if all_unread_messages else 0
            }
        })
        
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'User profile not found'}, status=400)
    except ChatSession.DoesNotExist:
        return JsonResponse({'error': 'Chat session not found'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

def parse_timestamp(timestamp_str):
    """Helper function to parse various timestamp formats."""
    try:
        # Try direct parsing first
        if '%' in timestamp_str:
            from urllib.parse import unquote
            timestamp_str = unquote(timestamp_str)
            
        return timezone.datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        # Handle other formats
        try:
            if 'T' in timestamp_str:
                # Simplified ISO format
                date_part, time_part = timestamp_str.split('T', 1)
                if '+' in time_part:
                    time_part, _ = time_part.split('+', 1)
                return timezone.datetime.fromisoformat(f"{date_part}T{time_part}")
            else:
                # Simple date only
                from datetime import datetime
                return datetime.strptime(timestamp_str, "%Y-%m-%d")
        except:
            return None

@login_required
@csrf_exempt
def flag_message(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
    try:
        # Parse the request data
        data = json.loads(request.body)
        message_id = data.get('message_id')
        
        if not message_id:
            return JsonResponse({'error': 'Missing message_id'}, status=400)
        
        # Get required objects
        user_profile = UserProfile.objects.get(user=request.user)
        message = Message.objects.get(id=message_id)
        
        # Flag the message
        message.is_flagged = True
        message.save()
        
        # Create a report
        report = Report.objects.create(
            message=message,
            reported_by=user_profile,
            reason_category=data.get('reason_category', 'other'),
            reason_details=data.get('reason_details', '')
        )
        
        return JsonResponse({
            'success': True,
            'report_id': report.id
        })
        
    except Message.DoesNotExist:
        return JsonResponse({'error': 'Message not found'}, status=404)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'User profile not found'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def find_psych_student(request):
    user_profile = UserProfile.objects.get(user=request.user)
    
    if user_profile.is_psych_student or user_profile.is_supervisor:
        return redirect('home')
    
    school_year = request.GET.get('school_year')
    expertise_id = request.GET.get('expertise')
    
    psych_students = PsychologyStudentProfile.objects.filter(
        user_profile__is_psych_student=True,
        is_available=True
    )
    
    if school_year:
        psych_students = psych_students.filter(school_year=int(school_year))
    
    if expertise_id:
        psych_students = psych_students.filter(expertise_areas__id=int(expertise_id))
    
    expertise_areas = ExpertiseArea.objects.all()
    
    return render(request, 'chat_app/find_psych_student.html', {
        'psych_students': psych_students,
        'expertise_areas': expertise_areas,
        'selected_year': int(school_year) if school_year else None,
        'selected_expertise': int(expertise_id) if expertise_id else None
    })

@login_required
def start_chat(request, student_id):
    user_profile = UserProfile.objects.get(user=request.user)
    
    psych_student = get_object_or_404(UserProfile, id=student_id, is_psych_student=True)
    
    existing_chat = ChatSession.objects.filter(
        psych_student=psych_student,
        normal_user=user_profile
    ).first()
    
    if existing_chat:
        return redirect('chat_with_id', conversation_id=existing_chat.id)
    else:
        new_chat = ChatSession.objects.create(
            psych_student=psych_student,
            normal_user=user_profile
        )
        
        return redirect('chat_with_id', conversation_id=new_chat.id)

@login_required
def profile(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        context = {
            'user': request.user,
            'profile': user_profile
        }
        
        if user_profile.is_psych_student:
            try:
                psych_profile = PsychologyStudentProfile.objects.get(user_profile=user_profile)
                context['psych_profile'] = psych_profile
                context['all_expertise_areas'] = ExpertiseArea.objects.all()
            except PsychologyStudentProfile.DoesNotExist:
                pass
        
        return render(request, 'chat_app/profile.html', context)
    except UserProfile.DoesNotExist:
        return redirect('home')

@login_required
def update_profile(request):
    if request.method == 'POST':
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            
            if user_profile.is_psych_student:
                try:
                    psych_profile = PsychologyStudentProfile.objects.get(user_profile=user_profile)
                    
                    school_year = request.POST.get('school_year')
                    if school_year:
                        psych_profile.school_year = int(school_year)
                    
                    bio = request.POST.get('bio')
                    if bio is not None:
                        psych_profile.bio = bio
                    
                    is_available = request.POST.get('is_available') == 'on'
                    psych_profile.is_available = is_available
                    
                    expertise_areas = request.POST.getlist('expertise_areas')
                    if expertise_areas:
                        psych_profile.expertise_areas.clear()
                        for area_id in expertise_areas:
                            try:
                                area = ExpertiseArea.objects.get(id=area_id)
                                psych_profile.expertise_areas.add(area)
                            except ExpertiseArea.DoesNotExist:
                                pass
                    
                    psych_profile.save()
                
                except PsychologyStudentProfile.DoesNotExist:
                    psych_profile = PsychologyStudentProfile(
                        user_profile=user_profile,
                        school_year=int(request.POST.get('school_year', 1)),
                        bio=request.POST.get('bio', ''),
                        is_available=request.POST.get('is_available') == 'on'
                    )
                    psych_profile.save()
                    
                    expertise_areas = request.POST.getlist('expertise_areas')
                    for area_id in expertise_areas:
                        try:
                            area = ExpertiseArea.objects.get(id=area_id)
                            psych_profile.expertise_areas.add(area)
                        except ExpertiseArea.DoesNotExist:
                            pass
            else:
                area_of_study = request.POST.get('area_of_study')
                semester = request.POST.get('semester')
                academic_interests = request.POST.get('academic_interests')
                about_me = request.POST.get('about_me')
                
                if area_of_study is not None:
                    user_profile.area_of_study = area_of_study
                if semester is not None:
                    user_profile.semester = semester
                if academic_interests is not None:
                    user_profile.academic_interests = academic_interests
                if about_me is not None:
                    user_profile.about_me = about_me
                
                user_profile.save()
            
            from django.contrib import messages
            messages.success(request, 'Your profile has been updated successfully.')
            
            return redirect('profile')
        except UserProfile.DoesNotExist:
            return redirect('home')
    
    return redirect('profile')

@login_required
def send_request(request):
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        issue_description = request.POST.get('issue_description')
        
        if not student_id or not issue_description:
            messages.error(request, "Please provide all required information.")
            return redirect('find_psych_student')
            
        try:
            normal_user_profile = UserProfile.objects.get(user=request.user)
            psych_student_profile = UserProfile.objects.get(id=student_id)
            
            existing_request = ChatRequest.objects.filter(
                normal_user=normal_user_profile,
                psych_student=psych_student_profile,
                status='pending'
            ).exists()
            
            if existing_request:
                messages.error(request, "You have already sent a request to this psychology student.")
                return redirect('find_psych_student')
            
            chat_request = ChatRequest.objects.create(
                normal_user=normal_user_profile,
                psych_student=psych_student_profile,
                issue_description=issue_description
            )
            
            # Future: Send email notification to psychology student
            
            messages.success(request, "Your request has been sent. You'll be notified when the psychology student accepts.")
            
            return redirect('home')
            
        except UserProfile.DoesNotExist:
            messages.error(request, "Could not find the selected psychology student.")
            return redirect('find_psych_student')
        except Exception as e:
            print(f"Error sending request: {str(e)}")
            messages.error(request, "An error occurred while sending your request. Please try again.")
            return redirect('find_psych_student')
    
    return redirect('find_psych_student')

@login_required
def accept_request(request):
    request_id = request.GET.get('request_id')
    
    if not request_id:
        return redirect('psychology_student_home')
        
    try:
        chat_request = ChatRequest.objects.get(id=request_id)
        
        if chat_request.psych_student.user != request.user:
            return redirect('psychology_student_home')
            
        chat_session = ChatSession.objects.create(
            psych_student=chat_request.psych_student,
            normal_user=chat_request.normal_user,
            is_active=True
        )
        
        initial_message = Message.objects.create(
            chat_session=chat_session,
            sender=chat_request.normal_user,
            content=f"Opening message: {chat_request.issue_description}",
            is_system_message=True
        )
        
        chat_request.status = 'accepted'
        chat_request.save()
        
        # Future: Send notification to normal user
        
        return redirect('chat_with_id', conversation_id=chat_session.id)
        
    except ChatRequest.DoesNotExist:
        return redirect('psychology_student_home')

@login_required
def reject_request(request):
    request_id = request.GET.get('request_id')
    
    if not request_id:
        return redirect('psychology_student_home')
        
    try:
        chat_request = ChatRequest.objects.get(id=request_id)
        
        if chat_request.psych_student.user != request.user:
            return redirect('psychology_student_home')
            
        chat_request.status = 'rejected'
        chat_request.save()
        
        # Future: Send notification to normal user
        
        from django.contrib import messages
        messages.success(request, 'The request has been declined.')
        
        return redirect('psychology_student_home')
        
    except ChatRequest.DoesNotExist:
        return redirect('psychology_student_home')
def delete_request(request):
    request_id = request.GET.get('request_id')
    if not request_id:
        return redirect('home')
    try:
        chat_request = ChatRequest.objects.get(id=request_id)
        if chat_request.status != 'pending':
            messages.error(request, 'Only pending requests can be deleted.')
            return redirect('home')
        chat_request.delete()
        messages.success(request, 'Request deleted successfully.')
        return redirect('home')
    except ChatRequest.DoesNotExist:
        messages.error(request, 'Request not found.')
        return redirect('home')

@login_required
def psychology_student_home(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        
        if not user_profile.is_psych_student:
            return redirect('home')
            
        waiting_requests = ChatRequest.objects.filter(
            psych_student=user_profile,
            status='pending'
        ).order_by('-created_at')
        
        active_conversations = ChatSession.objects.filter(
            psych_student=user_profile,
            is_active=True
        ).order_by('-last_message_time')
        
        ended_conversations = ChatSession.objects.filter(
            psych_student=user_profile,
            is_active=False
        ).order_by('-last_message_time')
        
        context = {
            'waiting_requests': waiting_requests,
            'active_conversations': active_conversations,
            'ended_conversations': ended_conversations,
            'active_cases': active_conversations.count(),
            'completed_cases': ended_conversations.count(),
            'user_profile': user_profile,
        }
        
        return render(request, 'chat_app/psychology_student_home.html', context)
        
    except UserProfile.DoesNotExist:
        return redirect('home')

@login_required
def delete_chat(request, conversation_id):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        
        chat_session = get_object_or_404(ChatSession, id=conversation_id)
        
        is_authorized = (chat_session.psych_student == user_profile or 
                        chat_session.normal_user == user_profile)
        
        if not is_authorized:
            return redirect('home')
        
        Message.objects.filter(chat_session=chat_session).delete()
        
        chat_session.delete()
        
        if user_profile.is_psych_student:
            return redirect('psychology_student_home')
        else:
            return redirect('home')
            
    except UserProfile.DoesNotExist:
        return redirect('home')
    except Exception as e:
        print(f"Error deleting chat: {str(e)}")
        return redirect('home')

@login_required
def update_availability(request):
    if request.method == 'POST':
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            
            if user_profile.is_psych_student:
                try:
                    psych_profile = PsychologyStudentProfile.objects.get(user_profile=user_profile)
                    
                
                    is_available = request.POST.get('is_available') == 'on'
                    psych_profile.is_available = is_available
                    psych_profile.save()
                    
                    messages.success(request, 'Your availability status has been updated to ' + ('Available' if is_available else 'Not Available') + '.')
                    
                except PsychologyStudentProfile.DoesNotExist:
                    messages.error(request, 'Psychology student profile not found.')
            else:
                messages.error(request, 'Only psychology students can update availability.')
            
            return redirect('psychology_student_home')
        except UserProfile.DoesNotExist:
            messages.error(request, 'User profile not found.')
            return redirect('home')
    
    return redirect('psychology_student_home')
def create_notification(user_profile, message, notification_type):
    Notification.objects.create(
        receiver=user_profile,
        message=message,
        notification_type=notification_type
    )
@login_required
def mark_notifications_read(request):
    user_profile = UserProfile.objects.get(user=request.user)
    Notification.objects.filter(receiver=user_profile, is_read=False).update(is_read=True)
    return JsonResponse({'success': True,})
def delete_notification(request, notification_id):
    user_profile= UserProfile.objects.get(user=request.user)
    notif = get_object_or_404(
        Notification,
        id=notification_id,
        receiver=user_profile
    )
    notif.delete()
    return JsonResponse({"success": True})