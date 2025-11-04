from rest_framework import generics, status, permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Q, Max
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from .models import Conversation, Message, ProjectViewRequest, MessagePermission, GroupConversation, GroupMessage
from .serializers import (
    ConversationListSerializer, ConversationDetailSerializer,
    MessageSerializer, ProjectViewRequestSerializer,
    CreateConversationSerializer, ProjectViewRequestResponseSerializer,
    GroupConversationListSerializer, GroupConversationDetailSerializer,
    GroupMessageSerializer, CreateGroupConversationSerializer
)


class ConversationListView(generics.ListAPIView):
    """
    List all conversations for the current user (inbox)
    GET /api/messaging/conversations/
    """
    serializer_class = ConversationListSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Get all conversations where user is a participant
        queryset = Conversation.objects.filter(
            Q(participant_1=user) | Q(participant_2=user)
        ).select_related(
            'participant_1', 'participant_1__profile',
            'participant_2', 'participant_2__profile',
            'related_project', 'related_project__owner'
        ).prefetch_related(
            'messages'
        )
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status', None)
        if status_filter == 'archived':
            # Show archived conversations
            queryset = queryset.filter(
                Q(participant_1=user, archived_by_p1=True) |
                Q(participant_2=user, archived_by_p2=True)
            )
        else:
            # Show active conversations (not archived by user)
            queryset = queryset.exclude(
                Q(participant_1=user, archived_by_p1=True) |
                Q(participant_2=user, archived_by_p2=True)
            )
        
        return queryset.order_by('-last_message_at', '-created_at')


class ConversationDetailView(generics.RetrieveAPIView):
    """
    Get detailed conversation with all messages
    GET /api/messaging/conversations/<conversation_id>/
    """
    serializer_class = ConversationDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        user = self.request.user
        return Conversation.objects.filter(
            Q(participant_1=user) | Q(participant_2=user)
        ).select_related(
            'participant_1', 'participant_1__profile',
            'participant_2', 'participant_2__profile',
            'related_project'
        ).prefetch_related(
            'messages', 'messages__sender', 'messages__sender__profile'
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Override to mark messages as read"""
        instance = self.get_object()
        
        # Mark all messages as read for current user
        Message.objects.filter(
            conversation=instance
        ).exclude(
            sender=request.user
        ).filter(
            read=False
        ).update(read=True)
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class CreateConversationView(generics.CreateAPIView):
    """
    Create a new conversation and send initial message
    POST /api/messaging/conversations/
    Body: {
        "recipient_id": 123,
        "message": "Hello!",
        "project_id": "uuid" (optional)
    }
    """
    serializer_class = CreateConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = serializer.save()
        
        # Return detailed conversation
        output_serializer = ConversationDetailSerializer(
            conversation,
            context={'request': request}
        )
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def archive_conversation(request, conversation_id):
    """
    Archive a conversation
    POST /api/messaging/conversations/<conversation_id>/archive/
    """
    try:
        conversation = Conversation.objects.get(id=conversation_id)
    except Conversation.DoesNotExist:
        return Response(
            {'error': 'Conversation not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user is participant
    if not conversation.is_participant(request.user):
        return Response(
            {'error': 'You are not a participant in this conversation'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Archive for the current user
    if conversation.participant_1 == request.user:
        conversation.archived_by_p1 = True
    else:
        conversation.archived_by_p2 = True
    
    conversation.save()
    
    return Response(
        {'message': 'Conversation archived successfully'},
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def unarchive_conversation(request, conversation_id):
    """
    Unarchive a conversation
    POST /api/messaging/conversations/<conversation_id>/unarchive/
    """
    try:
        conversation = Conversation.objects.get(id=conversation_id)
    except Conversation.DoesNotExist:
        return Response(
            {'error': 'Conversation not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Check if user is participant
    if not conversation.is_participant(request.user):
        return Response(
            {'error': 'You are not a participant in this conversation'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Unarchive for the current user
    if conversation.participant_1 == request.user:
        conversation.archived_by_p1 = False
    else:
        conversation.archived_by_p2 = False
    
    conversation.save()
    
    return Response(
        {'message': 'Conversation unarchived successfully'},
        status=status.HTTP_200_OK
    )


class MessageListCreateView(generics.ListCreateAPIView):
    """
    List messages in a conversation or send a new message
    GET/POST /api/messaging/conversations/<conversation_id>/messages/
    """
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        conversation_id = self.kwargs.get('conversation_id')
        user = self.request.user
        
        # Verify user is participant
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if not conversation.is_participant(user):
            return Message.objects.none()
        
        return Message.objects.filter(
            conversation_id=conversation_id
        ).select_related(
            'sender', 'sender__profile'
        ).order_by('created_at')
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['conversation_id'] = self.kwargs.get('conversation_id')
        return context
    
    def create(self, request, *args, **kwargs):
        """Send a message in the conversation"""
        conversation_id = self.kwargs.get('conversation_id')
        
        # Get conversation and verify participant
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if not conversation.is_participant(request.user):
            return Response(
                {'error': 'You are not a participant in this conversation'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Add conversation to data
        data = request.data.copy()
        data['conversation'] = str(conversation_id)
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        
        return Response(
            MessageSerializer(message, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_message_read(request, message_id):
    """
    Mark a message as read
    POST /api/messaging/messages/<message_id>/read/
    """
    try:
        message = Message.objects.get(id=message_id)
    except Message.DoesNotExist:
        return Response(
            {'error': 'Message not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Verify user is recipient (not sender)
    if message.sender == request.user:
        return Response(
            {'error': 'Cannot mark your own message as read'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Verify user is participant in conversation
    if not message.conversation.is_participant(request.user):
        return Response(
            {'error': 'You are not a participant in this conversation'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    message.mark_as_read()
    
    return Response(
        {'message': 'Message marked as read'},
        status=status.HTTP_200_OK
    )


class ProjectViewRequestListCreateView(generics.ListCreateAPIView):
    """
    List project view requests or create new request
    GET/POST /api/messaging/project-requests/
    """
    serializer_class = ProjectViewRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Get filter type from query params
        filter_type = self.request.query_params.get('filter', 'received')
        
        if filter_type == 'sent':
            # Requests sent by current user
            queryset = ProjectViewRequest.objects.filter(
                requester=user
            )
        else:
            # Requests received by current user (default)
            queryset = ProjectViewRequest.objects.filter(
                recipient=user
            )
        
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.select_related(
            'project', 'project__owner', 'requester', 'requester__profile',
            'recipient', 'recipient__profile', 'conversation'
        ).order_by('-created_at')


class ProjectViewRequestDetailView(generics.RetrieveAPIView):
    """
    Get detailed project view request
    GET /api/messaging/project-requests/<request_id>/
    """
    serializer_class = ProjectViewRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        user = self.request.user
        return ProjectViewRequest.objects.filter(
            Q(requester=user) | Q(recipient=user)
        ).select_related(
            'project', 'requester', 'requester__profile',
            'recipient', 'recipient__profile', 'conversation'
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def respond_to_project_request(request, request_id):
    """
    Accept or decline a project view request
    POST /api/messaging/project-requests/<request_id>/respond/
    Body: {"action": "accept" or "decline"}
    """
    try:
        view_request = ProjectViewRequest.objects.get(id=request_id)
    except ProjectViewRequest.DoesNotExist:
        return Response(
            {'error': 'Project view request not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Verify user is the recipient
    if view_request.recipient != request.user:
        return Response(
            {'error': 'You are not the recipient of this request'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Validate action
    serializer = ProjectViewRequestResponseSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    action = serializer.validated_data['action']
    
    if action == 'accept':
        success = view_request.accept()
        if success:
            # Grant messaging permission to student
            if view_request.conversation:
                MessagePermission.grant_permission(
                    from_user=view_request.requester,
                    to_user=view_request.recipient,
                    conversation=view_request.conversation,
                    grant_type='request_accepted'
                )
            
            return Response(
                {
                    'message': 'Project view request accepted',
                    'conversation_id': str(view_request.conversation.id) if view_request.conversation else None
                },
                status=status.HTTP_200_OK
            )
    elif action == 'decline':
        success = view_request.decline()
        if success:
            return Response(
                {'message': 'Project view request declined'},
                status=status.HTTP_200_OK
            )
    
    return Response(
        {'error': 'Invalid action or request cannot be processed'},
        status=status.HTTP_400_BAD_REQUEST
    )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancel_project_request(request, request_id):
    """
    Cancel a project view request (by requester)
    POST /api/messaging/project-requests/<request_id>/cancel/
    """
    try:
        view_request = ProjectViewRequest.objects.get(id=request_id)
    except ProjectViewRequest.DoesNotExist:
        return Response(
            {'error': 'Project view request not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Verify user is the requester
    if view_request.requester != request.user:
        return Response(
            {'error': 'You are not the requester of this request'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    success = view_request.cancel()
    if success:
        return Response(
            {'message': 'Project view request cancelled'},
            status=status.HTTP_200_OK
        )
    
    return Response(
        {'error': 'Request cannot be cancelled (already responded to)'},
        status=status.HTTP_400_BAD_REQUEST
    )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def inbox_stats(request):
    """
    Get inbox statistics for current user
    GET /api/messaging/stats/
    """
    user = request.user
    
    # Count unread messages
    unread_messages = Message.objects.filter(
        conversation__in=Conversation.objects.filter(
            Q(participant_1=user) | Q(participant_2=user)
        )
    ).exclude(sender=user).filter(read=False).count()
    
    # Count pending requests
    pending_requests = ProjectViewRequest.objects.filter(
        recipient=user,
        status='pending'
    ).count()
    
    # Count active conversations
    active_conversations = Conversation.objects.filter(
        Q(participant_1=user) | Q(participant_2=user)
    ).exclude(
        Q(participant_1=user, archived_by_p1=True) |
        Q(participant_2=user, archived_by_p2=True)
    ).count()
    
    return Response({
        'unread_messages': unread_messages,
        'pending_requests': pending_requests,
        'active_conversations': active_conversations,
    })


# ==================== GROUP CONVERSATION VIEWS ====================

class GroupConversationListView(generics.ListAPIView):
    """
    List all group conversations for the current user
    GET /api/messaging/group-conversations/
    """
    serializer_class = GroupConversationListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return GroupConversation.objects.filter(
            participants=user
        ).select_related(
            'project', 'project__owner', 'created_by', 'created_by__profile'
        ).prefetch_related(
            'participants', 'participants__profile', 'group_messages'
        ).order_by('-last_message_at', '-created_at')


class GroupConversationDetailView(generics.RetrieveAPIView):
    """
    Get details of a specific group conversation
    GET /api/messaging/group-conversations/<id>/
    """
    serializer_class = GroupConversationDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return GroupConversation.objects.filter(
            participants=user
        ).select_related(
            'project', 'project__owner', 'created_by', 'created_by__profile'
        ).prefetch_related(
            'participants', 'participants__profile', 'group_messages'
        )


class CreateGroupConversationView(generics.CreateAPIView):
    """
    Create a new group conversation with a project team
    POST /api/messaging/group-conversations/
    Body: {
        "project_id": "uuid",
        "initial_message": "message text"
    }
    """
    serializer_class = CreateGroupConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
            group_conversation = serializer.save()

            # Return the created group conversation
            output_serializer = GroupConversationDetailSerializer(
                group_conversation,
                context={'request': request}
            )
            return Response(output_serializer.data, status=status.HTTP_201_CREATED)

        except serializers.ValidationError as e:
            # Check if it's an existing conversation error
            if hasattr(e, 'detail') and isinstance(e.detail, dict):
                if 'existing_conversation_id' in str(e.detail):
                    # Extract the existing conversation ID
                    existing_id = e.detail.get('non_field_errors', [{}])[0].get('existing_conversation_id')
                    return Response({
                        'existing_conversation_id': existing_id,
                        'message': 'You already have a group conversation for this project'
                    }, status=status.HTTP_200_OK)
            raise


class GroupMessageListView(generics.ListAPIView):
    """
    List messages in a group conversation
    GET /api/messaging/group-conversations/<group_id>/messages/
    """
    serializer_class = GroupMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        group_id = self.kwargs.get('group_id')

        # Get group conversation and check user is participant
        group_conv = get_object_or_404(GroupConversation, id=group_id)
        if not group_conv.is_participant(user):
            return GroupMessage.objects.none()

        return GroupMessage.objects.filter(
            group_conversation=group_conv
        ).select_related(
            'sender', 'sender__profile'
        ).prefetch_related(
            'read_by'
        ).order_by('created_at')


class CreateGroupMessageView(generics.CreateAPIView):
    """
    Send a message in a group conversation
    POST /api/messaging/group-conversations/<group_id>/messages/
    Body: {
        "content": "message text"
    }
    """
    serializer_class = GroupMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        group_id = self.kwargs.get('group_id')
        group_conv = get_object_or_404(GroupConversation, id=group_id)

        # Check user is participant
        if not group_conv.is_participant(request.user):
            return Response(
                {'detail': 'You are not a participant in this group conversation'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create message
        message = GroupMessage.objects.create(
            group_conversation=group_conv,
            sender=request.user,
            content=serializer.validated_data['content'],
            attachment=serializer.validated_data.get('attachment')
        )

        # Mark as read by sender
        message.read_by.add(request.user)

        output_serializer = GroupMessageSerializer(message, context={'request': request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)
