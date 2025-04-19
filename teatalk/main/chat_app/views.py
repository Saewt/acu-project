from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from .forms import UserRegisterForm
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth.models import User
from .models import UserProfile, Message, ChatSession, PsychologyStudentProfile, ExpertiseArea, Report, ChatRequest
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q

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
        
        # Authenticate the user
        user = authenticate(username=username, password=password)
        
        if user is not None:
            login(request, user)
            # Update last login time for the user profile
            try:
                profile = UserProfile.objects.get(user=user)
                profile.update_last_login()
                
                # Redirect based on user role
                if profile.is_psych_student:
                    return redirect('psychology_student_home')
            except UserProfile.DoesNotExist:
                pass
            # Redirect to the home page after successful login
            return redirect('home')
        else:
            # Create a form with the submitted username to show appropriate errors
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
        
        # Redirect psychology students to their custom home page
        if user_profile.is_psych_student:
            return redirect('psychology_student_home')
        
        # Get active chat sessions based on user role
        if user_profile.is_supervisor:
            # Supervisors can see both their supervised students' chats and chats they have explicit access to
            supervised_students = UserProfile.objects.filter(supervisor=user_profile)
            active_conversations = ChatSession.objects.filter(
                Q(psych_student__in=supervised_students) | 
                Q(supervisor_access=user_profile)
            ).distinct().order_by('-last_message_time')
        else:
            # Normal users only see their own chats
            active_conversations = ChatSession.objects.filter(normal_user=user_profile, is_active=True).order_by('-last_message_time')
            ended_conversations = ChatSession.objects.filter(normal_user=user_profile, is_active=False).order_by('-last_message_time')
        
        # Count unread messages for each chat session
        for session in active_conversations:
            session.unread_count = session.get_unread_count(user_profile)
        
        # Get pending requests for normal users
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
            'pending_requests': pending_requests
        })
        
    except UserProfile.DoesNotExist:
        # Handle case where user doesn't have a profile
        return render(request, 'chat_app/home.html', {'error': 'User profile not found'})

@login_required
def chat(request, conversation_id=None):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        
        if conversation_id:
            # Get existing chat session
            chat_session = get_object_or_404(ChatSession, id=conversation_id)
            
            # Check if user is a participant or supervisor with access
            is_participant = (chat_session.psych_student == user_profile or 
                             chat_session.normal_user == user_profile)
            
            is_supervisor_with_access = (user_profile.is_supervisor and (
                chat_session.psych_student.supervisor == user_profile or
                chat_session.supervisor_access.filter(id=user_profile.id).exists()
            ))
            
            if not (is_participant or is_supervisor_with_access):
                return redirect('home')
                
            # Mark messages as read for the current user
            if is_participant:  # Only mark as read if actual participant (not supervisor)
                chat_session.mark_all_read(user_profile)
        else:
            # For demo purposes, redirect to home if no conversation_id provided
            return redirect('home')
        
        # Get messages for this chat session, ensure they're ordered by timestamp
        messages = chat_session.messages.order_by('timestamp')
        
        # Determine if current user is the psychology student or normal user
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
            'conversation_id': conversation_id  # Use consistent parameter name
        })
        
    except UserProfile.DoesNotExist:
        return render(request, 'chat_app/chat.html', {'error': 'User profile not found'})

@login_required
@csrf_exempt
def send_message(request):
    if request.method == 'POST':
        try:
            # Handle both JSON and form data requests
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                conversation_id = data.get('conversation_id')
                content = data.get('content', data.get('message'))
            else:
                conversation_id = request.POST.get('conversation_id')
                content = request.POST.get('content', request.POST.get('message'))
            
            print(f"send_message called with conversation_id={conversation_id}, content length={len(content) if content else 0}")
            
            if not conversation_id:
                return JsonResponse({'error': 'Missing conversation_id parameter'}, status=400)
            
            if not content:
                return JsonResponse({'error': 'Missing message content'}, status=400)
            
            # Try to get user profile or create one if it doesn't exist
            try:
                user_profile = UserProfile.objects.get(user=request.user)
            except UserProfile.DoesNotExist:
                # Instead of creating a profile, return an error
                return JsonResponse({'error': 'User profile not found, please contact an administrator'}, status=400)
            
            try:
                # Get chat session
                chat_session = ChatSession.objects.get(id=conversation_id)
                
                # Check if user can send messages in this chat
                is_participant = (chat_session.psych_student == user_profile or 
                                chat_session.normal_user == user_profile)
                
                if not is_participant:
                    return JsonResponse({'error': 'You are not authorized to send messages in this chat'}, status=403)
                
                # Create message
                message = Message.objects.create(
                    chat_session=chat_session,
                    sender=user_profile,
                    content=content
                )
                
                print(f"Message created: id={message.id}, timestamp={message.timestamp}")
                
                # Format the timestamp in a JavaScript-friendly way
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
                return JsonResponse({'error': f'Chat session with ID {conversation_id} not found'}, status=400)
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)
        except Exception as e:
            import traceback
            print(f"Error in send_message: {str(e)}")
            print(traceback.format_exc())
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)
    
@login_required
def get_messages(request):
    conversation_id = request.GET.get('conversation_id')
    since = request.GET.get('since', '0')
    
    print(f"get_messages called with conversation_id={conversation_id}, since={since}")
    
    if not conversation_id:
        return JsonResponse({'error': 'Missing conversation_id parameter'}, status=400)
    
    try:
        # Try to get or create user profile
        try:
            user_profile = UserProfile.objects.get(user=request.user)
        except UserProfile.DoesNotExist:
            # Instead of creating a profile, return an error
            return JsonResponse({'error': 'User profile not found, please contact an administrator'}, status=400)
        
        try:
            chat_session = ChatSession.objects.get(id=conversation_id)
            
            # Check if user can access this chat
            is_participant = (chat_session.psych_student == user_profile or 
                             chat_session.normal_user == user_profile)
                             
            is_supervisor_with_access = (user_profile.is_supervisor and (
                chat_session.psych_student.supervisor == user_profile or
                chat_session.supervisor_access.filter(id=user_profile.id).exists()
            ))
            
            if not (is_participant or is_supervisor_with_access):
                return JsonResponse({'error': 'Not authorized to access this chat'}, status=403)
            
            # Get all unread messages first (before any slicing), so we can mark them as read later
            all_unread_messages = None
            if is_participant:
                all_unread_messages = chat_session.messages.filter(is_read=False).exclude(sender=user_profile)
                print(f"Found {all_unread_messages.count()} unread messages")
            
            # Get messages
            if since != '0':
                try:
                    # Try to parse the ISO format timestamp
                    since_time = None
                    try:
                        # Check if the timestamp is URL encoded
                        if '%' in since:
                            from urllib.parse import unquote
                            since = unquote(since)
                            print(f"URL decoded timestamp: {since}")
                            
                        since_time = timezone.datetime.fromisoformat(since)
                    except (ValueError, TypeError) as e:
                        print(f"Basic fromisoformat failed: {str(e)}")
                        # Python <3.11 might not handle timezone offsets correctly in fromisoformat
                        # Try alternative parsing if the standard approach fails
                        if 'T' in since:
                            date_part, time_part = since.split('T', 1)
                            if '+' in time_part:
                                time_part, _ = time_part.split('+', 1)
                            since_iso = f"{date_part}T{time_part}"
                            try:
                                since_time = timezone.datetime.fromisoformat(since_iso)
                                print(f"Modified ISO format successful: {since_time}")
                            except ValueError:
                                print(f"Failed to parse modified ISO format: {since_iso}")
                        else:
                            # Try to handle simple date format
                            try:
                                from datetime import datetime
                                # Try simple parsing for common formats like YYYY-MM-DD
                                since_time = datetime.strptime(since, "%Y-%m-%d")
                                print(f"Simple date parsing successful: {since_time}")
                            except:
                                print(f"All timestamp parsing methods failed for: {since}")
                                since_time = None
                    
                    if since_time:
                        print(f"Fetching messages after: {since_time}")
                        # Get last 20 messages regardless, to avoid missing anything
                        recent_messages = list(chat_session.messages.order_by('-timestamp')[:20])
                        recent_message_ids = [msg.id for msg in recent_messages]
                        
                        # Get messages newer than the timestamp
                        time_filtered_messages = list(chat_session.messages.filter(timestamp__gt=since_time).order_by('timestamp'))
                        time_filtered_ids = [msg.id for msg in time_filtered_messages]
                        
                        print(f"Messages after timestamp: {len(time_filtered_messages)}")
                        
                        # Combine lists and remove duplicates
                        combined_ids = list(set(recent_message_ids + time_filtered_ids))
                        messages = chat_session.messages.filter(id__in=combined_ids).order_by('timestamp')
                        
                        print(f"Combined messages count: {messages.count()}")
                    else:
                        print(f"Could not parse timestamp '{since}', fetching all messages")
                        # Get base queryset without slicing yet
                        messages = chat_session.messages.order_by('timestamp')
                except Exception as e:
                    import traceback
                    print(f"Error parsing timestamp: {since}, Error: {str(e)}")
                    print(traceback.format_exc())
                    messages = chat_session.messages.order_by('timestamp')
            else:
                # Get the last 50 messages if no timestamp provided
                print("No timestamp provided, fetching latest 50 messages")
                messages = chat_session.messages.order_by('timestamp')
            
            # Limit to 50 messages and convert to list to evaluate the queryset
            messages_list = list(messages[:50])
            
            # Format messages for JSON response
            messages_data = []
            for msg in messages_list:
                try:
                    messages_data.append({
                        'id': msg.id,
                        'content': msg.content,
                        'sender_id': msg.sender.id,
                        'sender_anonymous_id': msg.sender.anonymous_id,
                        'is_current_user': msg.sender == user_profile,
                        'timestamp': msg.timestamp.isoformat(),
                        'is_flagged': msg.is_flagged
                    })
                except Exception as e:
                    print(f"Error formatting message {msg.id}: {str(e)}")
            
            # Mark messages as read if the user is a participant (not a supervisor)
            if is_participant and all_unread_messages is not None:
                # Bulk update unread messages 
                all_unread_messages.update(is_read=True, read_at=timezone.now())
            
            # Get the latest timestamp to send back - consistently use UTC format
            now = timezone.now()
            current_time = now.isoformat()
            
            # Convert timezone format to something JavaScript can parse if needed
            if '+' in current_time:
                current_time = current_time.replace('+00:00', 'Z')
            
            print(f"Returning {len(messages_data)} messages, last_time={current_time}")
            
            return JsonResponse({
                'messages': messages_data,
                'last_time': current_time,
                'server_time': timezone.now().timestamp(),  # Unix timestamp for debugging
                'debug_info': {
                    'since': since,
                    'message_count': len(messages_data),
                    'unread_count': all_unread_messages.count() if all_unread_messages else 0
                }
            })
            
        except ChatSession.DoesNotExist:
            return JsonResponse({'error': f'Chat session with ID {conversation_id} not found'}, status=400)
        
    except Exception as e:
        import traceback
        print(f"Unexpected error in get_messages: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@csrf_exempt
def flag_message(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            message_id = data.get('message_id')
            reason_category = data.get('reason_category', 'other')
            reason_details = data.get('reason_details', '')
            
            if not message_id:
                return JsonResponse({'error': 'Missing message_id'}, status=400)
            
            user_profile = UserProfile.objects.get(user=request.user)
            message = Message.objects.get(id=message_id)
            
            # Flag the message
            message.is_flagged = True
            message.save()
            
            # Create a report
            report = Report.objects.create(
                message=message,
                reported_by=user_profile,
                reason_category=reason_category,
                reason_details=reason_details
            )
            
            return JsonResponse({
                'success': True,
                'report_id': report.id
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@login_required
def find_psych_student(request):
    # Get the current user profile
    user_profile = UserProfile.objects.get(user=request.user)
    
    # Only normal users can access this page
    if user_profile.is_psych_student or user_profile.is_supervisor:
        return redirect('home')
    
    # Get filter parameters from request
    school_year = request.GET.get('school_year')
    expertise_id = request.GET.get('expertise')
    
    # Start with all available psychology students
    psych_students = PsychologyStudentProfile.objects.filter(
        user_profile__is_psych_student=True,
        is_available=True
    )
    
    # Apply filters if provided
    if school_year:
        psych_students = psych_students.filter(school_year=int(school_year))
    
    if expertise_id:
        psych_students = psych_students.filter(expertise_areas__id=int(expertise_id))
    
    # Get all expertise areas for the filter dropdown
    expertise_areas = ExpertiseArea.objects.all()
    
    return render(request, 'chat_app/find_psych_student.html', {
        'psych_students': psych_students,
        'expertise_areas': expertise_areas,
        'selected_year': int(school_year) if school_year else None,
        'selected_expertise': int(expertise_id) if expertise_id else None
    })

@login_required
def start_chat(request, student_id):
    # Get the current user profile (normal user)
    user_profile = UserProfile.objects.get(user=request.user)
    
    # Get the psychology student profile
    psych_student = get_object_or_404(UserProfile, id=student_id, is_psych_student=True)
    
    # Check if a chat session already exists between these users
    existing_chat = ChatSession.objects.filter(
        psych_student=psych_student,
        normal_user=user_profile
    ).first()
    
    if existing_chat:
        # If a chat already exists, redirect to it
        return redirect('chat_with_id', conversation_id=existing_chat.id)
    else:
        # Create a new chat session
        new_chat = ChatSession.objects.create(
            psych_student=psych_student,
            normal_user=user_profile
        )
        
        # Redirect to the new chat
        return redirect('chat_with_id', conversation_id=new_chat.id)

@login_required
def profile(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        context = {
            'user': request.user,
            'profile': user_profile
        }
        
        # If user is a psychology student, add their psychology profile to context
        if user_profile.is_psych_student:
            try:
                psych_profile = PsychologyStudentProfile.objects.get(user_profile=user_profile)
                context['psych_profile'] = psych_profile
                # Add all expertise areas for the dropdown
                context['all_expertise_areas'] = ExpertiseArea.objects.all()
            except PsychologyStudentProfile.DoesNotExist:
                pass
        
        return render(request, 'chat_app/profile.html', context)
    except UserProfile.DoesNotExist:
        # Handle case where user doesn't have a profile
        return redirect('home')

@login_required
def update_profile(request):
    if request.method == 'POST':
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            
            # Handle avatar upload if provided
            if 'avatar' in request.FILES:
                user_profile.avatar = request.FILES['avatar']
                user_profile.save()
            
            # If user is a psychology student, update their psychology profile
            if user_profile.is_psych_student:
                try:
                    psych_profile = PsychologyStudentProfile.objects.get(user_profile=user_profile)
                    
                    # Update school year
                    school_year = request.POST.get('school_year')
                    if school_year:
                        psych_profile.school_year = int(school_year)
                    
                    # Update bio
                    bio = request.POST.get('bio')
                    if bio is not None:
                        psych_profile.bio = bio
                    
                    # Update availability
                    is_available = request.POST.get('is_available') == 'on'
                    psych_profile.is_available = is_available
                    
                    # Update expertise areas
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
                    # Create a new psychology student profile if it doesn't exist
                    psych_profile = PsychologyStudentProfile(
                        user_profile=user_profile,
                        school_year=int(request.POST.get('school_year', 1)),
                        bio=request.POST.get('bio', ''),
                        is_available=request.POST.get('is_available') == 'on'
                    )
                    psych_profile.save()
                    
                    # Add expertise areas
                    expertise_areas = request.POST.getlist('expertise_areas')
                    for area_id in expertise_areas:
                        try:
                            area = ExpertiseArea.objects.get(id=area_id)
                            psych_profile.expertise_areas.add(area)
                        except ExpertiseArea.DoesNotExist:
                            pass
            else:
                # Update regular user profile fields
                area_of_study = request.POST.get('area_of_study')
                semester = request.POST.get('semester')
                academic_interests = request.POST.get('academic_interests')
                about_me = request.POST.get('about_me')
                
                # Update profile fields
                if area_of_study is not None:
                    user_profile.area_of_study = area_of_study
                if semester is not None:
                    user_profile.semester = semester
                if academic_interests is not None:
                    user_profile.academic_interests = academic_interests
                if about_me is not None:
                    user_profile.about_me = about_me
                
                user_profile.save()
            
            # Add success message
            from django.contrib import messages
            messages.success(request, 'Your profile has been updated successfully.')
            
            return redirect('profile')
        except UserProfile.DoesNotExist:
            # Handle case where user doesn't have a profile
            return redirect('home')
    
    # If not POST, redirect to profile page
    return redirect('profile')

@login_required
def send_request(request):
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        issue_description = request.POST.get('issue_description')
        
        if not student_id or not issue_description:
            return redirect('find_psych_student')
        
        try:
            # Get user profiles
            normal_user_profile = UserProfile.objects.get(user=request.user)
            psych_student_profile = UserProfile.objects.get(id=student_id)
            
            # Create the chat request
            chat_request = ChatRequest.objects.create(
                normal_user=normal_user_profile,
                psych_student=psych_student_profile,
                issue_description=issue_description
            )
            
            # Future: Send email notification to psychology student
            
            # Add success message
            from django.contrib import messages
            messages.success(request, "Your request has been sent. You'll be notified when the psychology student accepts.")
            
            return redirect('home')
            
        except UserProfile.DoesNotExist:
            from django.contrib import messages
            messages.error(request, "Could not find the selected psychology student.")
            return redirect('find_psych_student')
    
    return redirect('find_psych_student')

@login_required
def accept_request(request):
    request_id = request.GET.get('request_id')
    
    if not request_id:
        return redirect('psychology_student_home')
        
    try:
        # Get the chat request
        chat_request = ChatRequest.objects.get(id=request_id)
        
        # Make sure the request is for this psychology student
        if chat_request.psych_student.user != request.user:
            return redirect('psychology_student_home')
            
        # Create a new chat session from the request
        chat_session = ChatSession.objects.create(
            psych_student=chat_request.psych_student,
            normal_user=chat_request.normal_user,
            is_active=True
        )
        
        # Add initial system message with the issue description
        initial_message = Message.objects.create(
            chat_session=chat_session,
            sender=chat_request.normal_user,
            content=f"Initial request: {chat_request.issue_description}",
            is_system_message=True
        )
        
        # Mark the request as accepted
        chat_request.status = 'accepted'
        chat_request.save()
        
        # Future: Send notification to normal user
        
        # Redirect to the new chat
        return redirect('chat_with_id', conversation_id=chat_session.id)
        
    except ChatRequest.DoesNotExist:
        return redirect('psychology_student_home')

@login_required
def reject_request(request):
    request_id = request.GET.get('request_id')
    
    if not request_id:
        return redirect('psychology_student_home')
        
    try:
        # Get the chat request
        chat_request = ChatRequest.objects.get(id=request_id)
        
        # Make sure the request is for this psychology student
        if chat_request.psych_student.user != request.user:
            return redirect('psychology_student_home')
            
        # Mark the request as rejected
        chat_request.status = 'rejected'
        chat_request.save()
        
        # Future: Send notification to normal user
        
        # Add success message
        from django.contrib import messages
        messages.success(request, 'The request has been declined.')
        
        # Redirect back to psychology student home
        return redirect('psychology_student_home')
        
    except ChatRequest.DoesNotExist:
        return redirect('psychology_student_home')

@login_required
def psychology_student_home(request):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        
        # Verify the user is a psychology student
        if not user_profile.is_psych_student:
            return redirect('home')
            
        # Get waiting requests
        waiting_requests = ChatRequest.objects.filter(
            psych_student=user_profile,
            status='pending'
        ).order_by('-created_at')
        
        # Get active conversations
        active_conversations = ChatSession.objects.filter(
            psych_student=user_profile,
            is_active=True
        ).order_by('-last_message_time')
        
        # Get ended conversations
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
        # Get the user profile
        user_profile = UserProfile.objects.get(user=request.user)
        
        # Get the chat session
        chat_session = get_object_or_404(ChatSession, id=conversation_id)
        
        # Check if the user is authorized to delete this chat
        is_authorized = (chat_session.psych_student == user_profile or 
                        chat_session.normal_user == user_profile)
        
        if not is_authorized:
            # If not authorized, redirect to home
            return redirect('home')
        
        # Delete all messages first
        Message.objects.filter(chat_session=chat_session).delete()
        
        # Now delete the chat session
        chat_session.delete()
        
        # Redirect based on user role
        if user_profile.is_psych_student:
            return redirect('psychology_student_home')
        else:
            return redirect('home')
            
    except UserProfile.DoesNotExist:
        # Handle case where user doesn't have a profile
        return redirect('home')
    except Exception as e:
        # Log the error
        print(f"Error deleting chat: {str(e)}")
        return redirect('home')