from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from .forms import UserRegisterForm
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth.models import User
from .models import UserProfile, Message, ChatSession, PsychologyStudentProfile, ExpertiseArea, Report, ChatRequest, Notification, SupervisorStudentChatSession, SuperVisorStudentMessage
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q, Prefetch, Count
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
                    return redirect('home')
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
        unread_notifications = Notification.objects.filter(
            receiver=user_profile,
            is_read=False
        ).order_by('-created_at')
        all_notifications = Notification.objects.filter(
            receiver=user_profile
        ).order_by('-created_at')

        supervised_students = []
        total_active_cases = 0
        flagged_cases = []
        flagged_cases_count = 0
        supervised_students_count = 0
        weekly_reviews_count = 0
        active_conversations = []
        ended_conversations = []
        pending_requests = []

        
        if user_profile.is_psych_student:
            return psychology_student_home(request)

        # Supervisor
        if user_profile.is_supervisor:
            # 1) Sorumlu olduğunuz öğrenciler
            supervised_students = UserProfile.objects.filter(
                supervisor=user_profile,
                is_psych_student=True
            )

            # 1a) Her öğrenci için aktif case sayısı ve flag durumu
            for student in supervised_students:
                student.active_cases_count = ChatSession.objects.filter(
                    is_active=True,
                    psych_student=student
                ).count()
                student.has_flagged_cases = Report.objects.filter(
                    chat_session__psych_student=student,
                    is_resolved=False
                ).exists()

            supervised_students_count = supervised_students.count()

            # 2) Flagged
            flagged_cases_qs = ChatSession.objects.filter(
                psych_student__supervisor=user_profile,
                is_active=True,
                reports__is_resolved=False  # Ensure we only get cases with at least one unresolved report
            ).distinct().select_related(
                'psych_student__user'  
            ).prefetch_related( 
                Prefetch(
                    'reports', # 
                    queryset=Report.objects.filter(is_resolved=False).order_by('created_at'), # Only unresolved, ordered by creation
                    to_attr='list_of_unresolved_reports'  
                )
            )
            
            flagged_cases = [] 
            for case in flagged_cases_qs: # 'case' bir ChatSession nesnesidir
                if hasattr(case, 'list_of_unresolved_reports') and case.list_of_unresolved_reports:
                    earliest_report_for_this_case = case.list_of_unresolved_reports[0]
                    # 'flag_reason' yerine 'flag_reason_display' kullanarak daha açıklayıcı hale getirelim
                    case.flag_reason_display = earliest_report_for_this_case.get_reason_category_display() 
                    # YENİ EKLENEN DETAYLAR:
                    case.report_details_preview = (earliest_report_for_this_case.reason_details[:75] + '...' 
                                                   if earliest_report_for_this_case.reason_details and len(earliest_report_for_this_case.reason_details) > 75 
                                                   else earliest_report_for_this_case.reason_details)
                    case.reported_at_display = earliest_report_for_this_case.created_at # Şablonda formatlanacak
                    case.reported_by_anon_id = earliest_report_for_this_case.reported_by.anonymous_id
                    case.reported_by_display_name = earliest_report_for_this_case.reported_by.user.get_full_name() # Supervisor için geçerli değil, ama şablonda kullanılabilir
                else:
                    case.flag_reason_display = 'Çözülmemiş rapor bulunmuyor' # Veya 'No unresolved reports'
                    # YENİ EKLENEN DETAYLAR (rapor yoksa boş veya N/A):
                    case.report_details_preview = ''
                    case.reported_at_display = None
                    case.reported_by_anon_id = 'N/A'
                    case.reported_by_display_name = 'N/A'  # Supervisor için geçerli değil, ama şablonda kullanılabilir
                flagged_cases.append(case)
            flagged_cases_count = len(flagged_cases)

            
            # 3) General
            total_active_cases = ChatSession.objects.filter(
                is_active=True,
                psych_student__supervisor=user_profile
            ).count()
            week_start = timezone.now().date() - timezone.timedelta(days=7)
            weekly_reviews_count = Report.objects.filter(
                resolved_at__date__gte=week_start,
                resolved_by=user_profile
            ).count()

        # Normal kullanıcı
        else:
            active_conversations = ChatSession.objects.filter(
                normal_user=user_profile,
                is_active=True
            ).order_by('-last_message_time')
            ended_conversations = ChatSession.objects.filter(
                normal_user=user_profile,
                is_active=False
            ).order_by('-last_message_time')
            pending_requests = ChatRequest.objects.filter(
                normal_user=user_profile,
                status='pending'
            ).order_by('-created_at')

        # Her aktif oturum için okunmamış sayısı ekle
        for session in active_conversations:
            session.unread_count = session.get_unread_count(user_profile)

        return render(request, 'chat_app/supervisor_home.html' if user_profile.is_supervisor else 'chat_app/home.html', {
            'user_profile': user_profile,
            'notifications': all_notifications,
            'unread_notifications': unread_notifications,
            'unread_notification_count': unread_notifications.count(),

            # Supervisor’a özel
            'supervised_students': supervised_students,
            'user_profile': user_profile,
            'supervised_students_count': supervised_students_count,
            'total_active_cases': total_active_cases,
            'flagged_cases': flagged_cases,
            'flagged_cases_count': flagged_cases_count,
            'weekly_reviews_count': weekly_reviews_count,
            'flagged_cases_details': [
                {
                    'chat_session': case,
                    'flag_reason': case.flag_reason if hasattr(case, 'flag_reason') else 'No unresolved reports'
                } for case in flagged_cases
            ],

            # Tüm kullanıcılar için
            'active_conversations': active_conversations,
            'ended_conversations': ended_conversations,
            'pending_requests': pending_requests,
        })

    except UserProfile.DoesNotExist:
        return render(request, 'chat_app/home.html', {
            'error': 'User profile not found'
        })

@login_required
def chat(request, conversation_id=None):
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        
        if not conversation_id: # Ensure conversation_id is present early
            return redirect('home') # Or handle error

        chat_session = get_object_or_404(ChatSession, id=conversation_id)
        
        is_participant = (chat_session.psych_student == user_profile or 
                         chat_session.normal_user == user_profile)
        
        is_supervisor_with_access = (user_profile.is_supervisor and (
            chat_session.psych_student.supervisor == user_profile or
            chat_session.supervisor_access.filter(id=user_profile.id).exists()
        ))
        
        if not (is_participant or is_supervisor_with_access):
            messages.error(request, "You are not authorized to view this chat.")
            return redirect('home')
            
        if is_participant:
            chat_session.mark_all_read(user_profile)
        
        messages_qs = chat_session.messages.order_by('timestamp') # Renamed from 'messages' to avoid conflict
        
        is_psych_student_role = (user_profile == chat_session.psych_student) # Renamed to avoid conflict
        is_normal_user_role = (user_profile == chat_session.normal_user) # Renamed to avoid conflict
        is_supervisor_role = user_profile.is_supervisor # Renamed to avoid conflict

        # Check if the current user has an active report for this session
        user_has_active_report = False
        if is_participant: # Only participants can report/unreport their own reports
            user_has_active_report = Report.objects.filter(
                chat_session=chat_session,
                reported_by=user_profile,
                is_resolved=False
            ).exists()
        
        context = {
            'chat_session': chat_session,
            'messages': messages_qs, 
            'user_profile': user_profile,
            'is_psych_student': is_psych_student_role, # 
            'is_normal_user': is_normal_user_role, # 
            'is_supervisor': is_supervisor_role, # 
            'conversation_id': conversation_id,
            'report_reasons': Report.REPORT_REASONS,
            'user_has_active_report': user_has_active_report, #
        }
        return render(request, 'chat_app/chat.html', context)
        
    except UserProfile.DoesNotExist:
        messages.error(request, "User profile not found.")
        return redirect('home')
    except ChatSession.DoesNotExist:
        messages.error(request, "Chat session not found.")
        return redirect('home')


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
def flag_chat_session(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            chat_session_id = data.get('chat_session_id')
            reason_category = data.get('reason') 
            details = data.get('details', '')

            chat_session = get_object_or_404(ChatSession, id=chat_session_id)
            user_profile = request.user.profile
            if user_profile.is_supervisor:
                return JsonResponse({'error': 'Supervisors cannot report chat sessions directly.'}, status=403)

            if Report.objects.filter(chat_session=chat_session, reported_by=user_profile, is_resolved=False).exists():
                return JsonResponse({'error': 'You have already reported this chat session and it is pending review.'}, status=400)
            
            Report.objects.create(
                chat_session=chat_session,
                reported_by=user_profile,
                reason_category=reason_category,
                reason_details=details
            )

            if chat_session.psych_student and chat_session.psych_student.supervisor:
                supervisor_profile = chat_session.psych_student.supervisor
                Notification.objects.create(
                    receiver=supervisor_profile,
                    message=f"Chat session {chat_session.id} (Student: {chat_session.psych_student.anonymous_id}, User: {chat_session.normal_user.anonymous_id}) has been reported by {user_profile.anonymous_id}.",
                    notification_type='report'
                )
            # If supervisors can be directly assigned via chat_session.supervisor_access
            for supervisor_profile in chat_session.supervisor_access.all():
                 Notification.objects.create(
                    receiver=supervisor_profile,
                    message=f"Chat session {chat_session.id} involving student {chat_session.psych_student.anonymous_id} has been reported by {user_profile.anonymous_id}.",
                    notification_type='report'
                )

            return JsonResponse({'success': True, 'message': 'Chat session reported successfully.'})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)
        except ChatSession.DoesNotExist:
            return JsonResponse({'error': 'Chat session not found'}, status=404)
        except UserProfile.DoesNotExist:
            return JsonResponse({'error': 'User profile not found.'}, status=403)
        except Exception as e:
            return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)

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
            Notification.objects.create(
                receiver= psych_student_profile,
                message=f"You have a new chat request from {normal_user_profile.anonymous_id}.",
                notification_type='request'
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
        Notification.objects.create(
            receiver=chat_request.normal_user,
            message=f"Your request to chat with {chat_request.psych_student.anonymous_id} has been accepted.",
            notification_type='request'
        )
        
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
        unread_notifications = Notification.objects.filter(receiver=user_profile, is_read=False).order_by('-created_at')
        all_notifications = Notification.objects.filter(receiver=user_profile).order_by('-created_at')

        
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
            'notifications': all_notifications,
            'unread_notifications': unread_notifications,
            'unread_notification_count': unread_notifications.count()
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
                    user_profile = UserProfile.objects.get(user=request.user)
                    psych_profile = PsychologyStudentProfile.objects.get_or_create(user_profile=user_profile,
                                                                                   defaults={'is_available': True})[0]
                    
                
                    is_available = request.POST.get('is_available') == 'on'
                    psych_profile.is_available = is_available
                    psych_profile.save()
                    
                    messages.success(request, 'Your availability status has been updated to ' + ('Available' if is_available else 'Not Available') + '.')
                    
                except PsychologyStudentProfile.DoesNotExist:
                    messages.error(request, 'Psychology student profile not found.')
            else:
                messages.error(request, 'Only psychology students can update availability.')
            
            return redirect('home')
        except UserProfile.DoesNotExist:
            messages.error(request, 'User profile not found.')
            return redirect('home')
    
    return redirect('home')
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
@login_required
@csrf_exempt    
def assign_students(request):
    supervisor_profile = request.user.profile
    if not supervisor_profile.is_supervisor:
        return redirect('home')

    if request.method == 'POST':
        # formdan gelen student_id, aslında UserProfile.id
        student_id = request.POST.get('student_id')
        student_profile = get_object_or_404(
            UserProfile,
            pk=student_id,
            is_psych_student=True,
            supervisor__isnull=True
        )
        # atamayı yap
        student_profile.supervisor = supervisor_profile
        student_profile.save()
        messages.success(
            request,
            f"{student_profile.user.get_full_name() or student_profile.user.username} başarıyla atandı."
        )
        return redirect('home')

    # 2) GET: halen atanmamış psikoloji öğrencilerini getir
    available_students = UserProfile.objects.filter(
        is_psych_student=True,
        supervisor__isnull=True
    ).order_by('user__last_name', 'user__first_name')

    return render(request, 'chat_app/assign_new_students.html', {
        'available_students': available_students
    })
def unassign_student(request):
    if request.method == 'POST':
        try:
            supervisor_profile = UserProfile.objects.get(user=request.user, is_supervisor=True)
            student_id = request.POST.get('student_id')

            if not student_id:
                messages.error(request, "Student ID is missing.")
                return redirect('home')

            student_profile = get_object_or_404(UserProfile, id=student_id, is_psych_student=True)

            if student_profile.supervisor != supervisor_profile:
                messages.error(request, "You are not authorized to unassign this student.")
                return redirect('home')

            student_profile.supervisor = None
            student_profile.save()
            messages.success(request, f"{student_profile.user.username} has been unassigned successfully.")
            return redirect('home')

        except UserProfile.DoesNotExist:
            messages.error(request, "Supervisor profile not found or you are not a supervisor.")
            return redirect('home')
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")
            return redirect('home')
    return redirect('home')
@login_required
def supervisor_init_or_open_chat(request,student_id):
    supervisor_profile = request.user.profile
    if not supervisor_profile.is_supervisor:
        messages.error(request, "You are not authorized to perform this action.")
        return redirect('home')
    try:
        student_profile = UserProfile.objects.get(id=student_id, is_psych_student=True)
    except:
        messages.error(request, "Psychology student not found.")
        return redirect('home')
    
    chat_session, created = SupervisorStudentChatSession.objects.get_or_create(
        supervisor=supervisor_profile,
        student=student_profile,
        defaults={'is_active': True, 'last_message_time': timezone.now()}
    )
    if created:
        messages.success(request, f"Chat session with {student_profile.user.username} has been created.")
        Notification.objects.create(
            receiver=student_profile,
            message=f"You have a new chat session initiated by {supervisor_profile.user.username}.",
            notification_type='request'
        )
    else:
        chat_session.is_active = True
        chat_session.save(update_fields=['is_active'])

    return redirect('supervisor_student_chat_interface', session_id=chat_session.id)
@login_required
def supervisor_student_chat_interface(request, session_id):
    # Current user profilini al
    user_profile = get_object_or_404(UserProfile, user=request.user)

    # Supervisor mı, öğrenci mi kontrol et
    if user_profile.is_supervisor:
        # supervisor rolündeyse session.supervisor’a bak
        chat_session = get_object_or_404(
            SupervisorStudentChatSession,
            id=session_id,
            supervisor=user_profile
        )
        supervisor_profile = user_profile
        student_profile = chat_session.student

    elif user_profile.is_psych_student:
        # öğrenci rolündeyse session.student’a bak
        chat_session = get_object_or_404(
            SupervisorStudentChatSession,
            id=session_id,
            student=user_profile
        )
        supervisor_profile = chat_session.supervisor
        student_profile = user_profile

    else:
        # ne öğrenci ne supervisor
        return redirect('home')

    # Mesajları alıp okunmamışları işaretle
    messages_for_supervisor_chat = chat_session.messages.order_by('timestamp').all()
    unread = chat_session.messages.filter(
        sender=student_profile,
        is_read=False
    )
    for msg in unread:
        msg.is_read = True
        msg.read_at = timezone.now()
        msg.save(update_fields=['is_read', 'read_at'])

    return render(request, 'chat_app/supervisor_student_chat.html', {
        'chat_session': chat_session,
        'messages_for_supervisor_chat': messages_for_supervisor_chat,
        'user_profile': user_profile,
        'supervisor_profile': supervisor_profile,
        'student_profile': student_profile,
    })
def send_supervisor_message(request):
    # Sadece POST kabul et
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        # Oturum ve içerik verisini al
        data = json.loads(request.body)
        session_id = data.get('session_id')
        content = data.get('content')

        # Zorunlu parametre kontrolü
        if not session_id:
            return JsonResponse({'error': 'Missing session_id'}, status=400)
        if not content:
            return JsonResponse({'error': 'Missing content'}, status=400)

        # Kullanıcı profili
        user_profile = get_object_or_404(UserProfile, user=request.user)

        # Sohbet oturumunu al
        chat_session = get_object_or_404(SupervisorStudentChatSession, id=session_id)

        # Yalnızca supervisor veya ilgili öğrenci izinli
        if not (user_profile.is_supervisor or user_profile == chat_session.student):
            return JsonResponse({'error': 'Not authorized for this session'}, status=403)

        # Mesajı kaydet
        new_message = SuperVisorStudentMessage.objects.create(
            chat_session=chat_session,
            sender=user_profile,
            content=content
        )

        # Son mesaj zamanını güncelle
        chat_session.last_message_time = new_message.timestamp
        chat_session.save(update_fields=['last_message_time'])

        # Başarılı yanıt
        return JsonResponse({
            'success': True,
            'message_id': new_message.id,
            'sender_id': user_profile.id,
            'sender_username': user_profile.user.get_full_name() or user_profile.user.username,
            'content': new_message.content,
            'timestamp': new_message.timestamp.isoformat(),
            'is_current_user': True
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_supervisor_messages(request):
    try:
        requesting_user_profile = get_object_or_404(UserProfile, user=request.user)
        session_id = request.GET.get('session_id')
        since_id = request.GET.get('since_id', '0')

        if not session_id:
            return JsonResponse({'error': 'Missing session_id'}, status=400)

        chat_session = get_object_or_404(SupervisorStudentChatSession, id=session_id)

        # Authorization: Ensure the requesting user is part of this chat session
        if not (requesting_user_profile == chat_session.supervisor or requesting_user_profile == chat_session.student):
            return JsonResponse({'error': 'Not authorized to view these messages.'}, status=403)

        messages_query = chat_session.messages.order_by('timestamp')
        
        if since_id.isdigit() and int(since_id) > 0:
            messages_query = messages_query.filter(id__gt=int(since_id))
        
        new_messages = messages_query.all()
        messages_data = []
        last_message_id_fetched = int(since_id) if since_id.isdigit() else 0

        for msg in new_messages:
            # If the current user is the supervisor and is fetching messages,
            # mark messages from the student as read.
            if requesting_user_profile.is_supervisor and msg.sender == chat_session.student and not msg.is_read:
                msg.is_read = True
                msg.read_at = timezone.now()
                msg.save(update_fields=['is_read', 'read_at'])
            
            messages_data.append({
                'id': msg.id,
                'content': msg.content,
                'sender_id': msg.sender.id, # UserProfile ID
                'sender_username': msg.sender.user.username, # or get_full_name()
                'timestamp': msg.timestamp.isoformat(),
                'is_current_user': msg.sender == requesting_user_profile,
                # 'is_read': msg.is_read # you can include this if needed by client
            })
            if msg.id > last_message_id_fetched:
                last_message_id_fetched = msg.id
        
        return JsonResponse({
            'messages': messages_data,
            'last_message_id_fetched': last_message_id_fetched
        })
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'User profile not found.'}, status=403)
    except SupervisorStudentChatSession.DoesNotExist:
        return JsonResponse({'error': 'Chat session not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
def student_initiate_chat_with_supervisor(request):
    student_profile = get_object_or_404(UserProfile, user=request.user, is_psych_student=True)

    if not student_profile.supervisor:
        messages.error(request, "You are not currently assigned to a supervisor.")
        return redirect('home') # Or wherever is appropriate

    supervisor_profile = student_profile.supervisor

    chat_session, created = SupervisorStudentChatSession.objects.get_or_create(
        supervisor=supervisor_profile,
        student=student_profile,
        defaults={'is_active': True, 'last_message_time': timezone.now()}
    )

    if created:
        messages.success(request, f"Chat session with your supervisor {supervisor_profile.user.username} has been created.")
        # Optionally, notify the supervisor
        Notification.objects.create(
            receiver=supervisor_profile,
            message=f"Your student {student_profile.user.username} has initiated a chat with you.",
            notification_type='request' # Or a new type like 'supervisor_chat'
        )
    else:
        # Ensure the session is active if it already existed
        if not chat_session.is_active:
            chat_session.is_active = True
            chat_session.save(update_fields=['is_active'])

    # Redirect to the chat interface, which should be flexible enough
    # to handle both student's and supervisor's perspective
    return redirect('supervisor_student_chat_interface', session_id=chat_session.id)
@login_required
@csrf_exempt
def unreport_chat_session(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            chat_session_id = data.get('chat_session_id')

            if not chat_session_id:
                return JsonResponse({'error': 'Chat session ID is required.'}, status=400)

            chat_session = get_object_or_404(ChatSession, id=chat_session_id)
            user_profile = request.user.profile

            # Find unresolved reports for this session by this user
            reports_to_unreport = Report.objects.filter(
                chat_session=chat_session,
                reported_by=user_profile,
                is_resolved=False
            )

            if not reports_to_unreport.exists():
                return JsonResponse({'error': 'No active report by you found for this chat session.'}, status=404)

            for report_item in reports_to_unreport:
                report_item.is_resolved = True
                # The user themselves is resolving their own report by un-reporting it.
                report_item.resolved_by = user_profile
                report_item.resolved_at = timezone.now()
                report_item.action_taken = "User un-reported the session." # Specific action
                report_item.save()

            return JsonResponse({'success': True, 'message': 'Chat session un-reported successfully.'})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format.'}, status=400)
        except ChatSession.DoesNotExist:
            return JsonResponse({'error': 'Chat session not found.'}, status=404)
        except UserProfile.DoesNotExist: # Should be handled by @login_required
            return JsonResponse({'error': 'User profile not found.'}, status=403)
        except Exception as e:
            return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)
    return JsonResponse({'error': 'Invalid request method.'}, status=405)