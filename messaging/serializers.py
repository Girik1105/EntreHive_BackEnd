from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Conversation, Message, ProjectViewRequest, MessagePermission, GroupConversation, GroupMessage
from accounts.serializers import UserProfileSerializer
from projects.serializers import ProjectSerializer


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for messages"""

    sender = serializers.SerializerMethodField()
    sender_id = serializers.IntegerField(write_only=True, required=False)
    
    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender', 'sender_id', 'content',
            'read', 'read_at', 'attachment', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'sender', 'read', 'read_at', 'created_at', 'updated_at']
    
    def get_sender(self, obj):
        """Get sender profile"""
        if hasattr(obj.sender, 'profile'):
            return UserProfileSerializer(obj.sender.profile, context=self.context).data
        return None

    def validate(self, data):
        """Validate message sending permissions"""
        request = self.context.get('request')
        conversation_id = data.get('conversation')

        if request and conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id.id if hasattr(conversation_id, 'id') else conversation_id)

                # Check if user is participant
                if not conversation.is_participant(request.user):
                    raise serializers.ValidationError("You are not a participant in this conversation")

                # Check messaging permissions
                other_participant = conversation.get_other_participant(request.user)
                if not MessagePermission.can_message(request.user, other_participant, conversation):
                    raise serializers.ValidationError(
                        "You don't have permission to send messages in this conversation. "
                        "Students can only reply after receiving a message or having their project view request accepted."
                    )

            except Conversation.DoesNotExist:
                raise serializers.ValidationError("Conversation not found")

        return data
    
    def create(self, validated_data):
        """Create message with sender from request"""
        request = self.context.get('request')
        validated_data['sender'] = request.user
        return super().create(validated_data)


class ConversationListSerializer(serializers.ModelSerializer):
    """Serializer for listing conversations (inbox view)"""

    participant_1 = serializers.SerializerMethodField()
    participant_2 = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    related_project = ProjectSerializer(read_only=True)
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'participant_1', 'participant_2', 'other_participant',
            'initiated_by', 'related_project', 'status', 'created_at',
            'updated_at', 'last_message_at', 'last_message', 'unread_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_message_at']

    def get_participant_1(self, obj):
        """Get participant 1 profile"""
        if hasattr(obj.participant_1, 'profile'):
            return UserProfileSerializer(obj.participant_1.profile, context=self.context).data
        return None

    def get_participant_2(self, obj):
        """Get participant 2 profile"""
        if hasattr(obj.participant_2, 'profile'):
            return UserProfileSerializer(obj.participant_2.profile, context=self.context).data
        return None

    def get_other_participant(self, obj):
        """Get the other participant from current user's perspective"""
        request = self.context.get('request')
        if request and request.user:
            other = obj.get_other_participant(request.user)
            if hasattr(other, 'profile'):
                return UserProfileSerializer(other.profile, context=self.context).data
        return None

    def get_last_message(self, obj):
        """Get the last message in the conversation"""
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return {
                'id': str(last_msg.id),
                'content': last_msg.content[:100],  # Preview only
                'sender_id': last_msg.sender.id,
                'created_at': last_msg.created_at,
                'read': last_msg.read
            }
        return None
    
    def get_unread_count(self, obj):
        """Get unread message count for current user"""
        request = self.context.get('request')
        if request and request.user:
            return obj.messages.exclude(sender=request.user).filter(read=False).count()
        return 0


class ConversationDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed conversation view with messages"""

    participant_1 = serializers.SerializerMethodField()
    participant_2 = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    messages = MessageSerializer(many=True, read_only=True)
    related_project = ProjectSerializer(read_only=True)
    can_send_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'participant_1', 'participant_2', 'other_participant',
            'initiated_by', 'related_project', 'status', 'messages',
            'created_at', 'updated_at', 'last_message_at', 'can_send_message'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_message_at']

    def get_participant_1(self, obj):
        """Get participant 1 profile"""
        if hasattr(obj.participant_1, 'profile'):
            return UserProfileSerializer(obj.participant_1.profile, context=self.context).data
        return None

    def get_participant_2(self, obj):
        """Get participant 2 profile"""
        if hasattr(obj.participant_2, 'profile'):
            return UserProfileSerializer(obj.participant_2.profile, context=self.context).data
        return None

    def get_other_participant(self, obj):
        """Get the other participant from current user's perspective"""
        request = self.context.get('request')
        if request and request.user:
            other = obj.get_other_participant(request.user)
            if hasattr(other, 'profile'):
                return UserProfileSerializer(other.profile, context=self.context).data
        return None

    def get_can_send_message(self, obj):
        """Check if current user can send messages in this conversation"""
        request = self.context.get('request')
        if request and request.user:
            other = obj.get_other_participant(request.user)
            return MessagePermission.can_message(request.user, other, obj)
        return False


class CreateConversationSerializer(serializers.Serializer):
    """Serializer for creating a new conversation"""
    
    recipient_id = serializers.IntegerField(required=True)
    message = serializers.CharField(max_length=5000, required=True)
    project_id = serializers.UUIDField(required=False, allow_null=True)
    
    def validate_recipient_id(self, value):
        """Validate recipient exists and is not the sender"""
        request = self.context.get('request')
        
        try:
            recipient = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Recipient not found")
        
        if request.user == recipient:
            raise serializers.ValidationError("Cannot create conversation with yourself")
        
        return value
    
    def validate(self, data):
        """Validate messaging permissions"""
        import logging
        logger = logging.getLogger(__name__)

        request = self.context.get('request')
        recipient = User.objects.get(id=data['recipient_id'])

        # Check if both users have profiles
        try:
            from_profile = request.user.profile
            to_profile = recipient.profile
        except Exception as e:
            logger.error(f"Profile error: {str(e)}")
            raise serializers.ValidationError(f"Both users must have profiles: {str(e)}")

        from_role = from_profile.user_role
        to_role = to_profile.user_role

        logger.info(f"Message permission check: {request.user.username} ({from_role}) -> {recipient.username} ({to_role})")

        # Allow same roles to message each other
        if from_role == to_role:
            logger.info("Same role messaging - ALLOWED")
            return data

        # Allow professors/investors/mentors to message students
        if from_role in ['professor', 'investor', 'mentor'] and to_role == 'student':
            logger.info("Prof/Investor/Mentor to student - ALLOWED")
            return data

        # For students messaging professors/investors/mentors, check if they have permission
        if from_role == 'student' and to_role in ['professor', 'investor', 'mentor']:
            # Check if there's an existing permission
            has_permission = MessagePermission.objects.filter(
                from_user=request.user,
                to_user=recipient
            ).exists()

            if not has_permission:
                logger.warning("Student to prof/investor/mentor without permission - DENIED")
                raise serializers.ValidationError(
                    "You don't have permission to message this user. "
                    "Students must first send a project view request to professors/investors/mentors."
                )
            logger.info("Student to prof/investor/mentor with permission - ALLOWED")

        return data
    
    def create(self, validated_data):
        """Create conversation and initial message"""
        request = self.context.get('request')
        recipient = User.objects.get(id=validated_data['recipient_id'])
        
        # Check if conversation already exists
        from django.db.models import Q
        existing_conv = Conversation.objects.filter(
            Q(participant_1=request.user, participant_2=recipient) |
            Q(participant_1=recipient, participant_2=request.user)
        ).first()
        
        if existing_conv:
            # Add message to existing conversation
            message = Message.objects.create(
                conversation=existing_conv,
                sender=request.user,
                content=validated_data['message']
            )
            return existing_conv
        
        # Create new conversation
        conversation = Conversation.objects.create(
            participant_1=request.user,
            participant_2=recipient,
            initiated_by=request.user,
            related_project_id=validated_data.get('project_id')
        )
        
        # Create initial message
        Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=validated_data['message']
        )
        
        return conversation


class ProjectViewRequestSerializer(serializers.ModelSerializer):
    """Serializer for project view requests"""

    requester = serializers.SerializerMethodField()
    recipient = serializers.SerializerMethodField()
    recipient_id = serializers.IntegerField(write_only=True, required=True)
    project = ProjectSerializer(read_only=True)
    project_id = serializers.UUIDField(write_only=True, required=True)
    conversation = ConversationListSerializer(read_only=True)
    
    class Meta:
        model = ProjectViewRequest
        fields = [
            'id', 'project', 'project_id', 'requester', 'recipient',
            'recipient_id', 'message', 'status', 'conversation',
            'created_at', 'updated_at', 'responded_at'
        ]
        read_only_fields = ['id', 'requester', 'status', 'conversation', 'created_at', 'updated_at', 'responded_at']

    def get_requester(self, obj):
        """Get requester profile"""
        if hasattr(obj.requester, 'profile'):
            return UserProfileSerializer(obj.requester.profile, context=self.context).data
        return None

    def get_recipient(self, obj):
        """Get recipient profile"""
        if hasattr(obj.recipient, 'profile'):
            return UserProfileSerializer(obj.recipient.profile, context=self.context).data
        return None

    def validate_recipient_id(self, value):
        """Validate recipient exists and has correct role"""
        try:
            recipient = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Recipient not found")

        if not hasattr(recipient, 'profile'):
            raise serializers.ValidationError("Recipient must have a profile")

        if recipient.profile.user_role not in ['professor', 'investor', 'mentor']:
            raise serializers.ValidationError(
                f"Can only send project view requests to professors, investors, or mentors. "
                f"Selected user '{recipient.username}' is a {recipient.profile.user_role}."
            )

        return value
    
    def validate_project_id(self, value):
        """Validate project exists and user is a member"""
        from projects.models import Project
        request = self.context.get('request')

        try:
            project = Project.objects.get(id=value)
        except Project.DoesNotExist:
            raise serializers.ValidationError("Project not found")

        if not project.is_team_member(request.user):
            raise serializers.ValidationError("You must be a member of the project to send view requests")

        return value
    
    def validate(self, data):
        """Validate project view request"""
        request = self.context.get('request')

        if not hasattr(request.user, 'profile'):
            raise serializers.ValidationError("User must have a profile")

        # Allow students and professors to send project view requests
        # (Professors may work on projects and want to share them with investors)
        allowed_roles = ['student', 'professor']
        if request.user.profile.user_role not in allowed_roles:
            raise serializers.ValidationError("Only students and professors can send project view requests")

        # Check for duplicate request
        from projects.models import Project
        project = Project.objects.get(id=data['project_id'])
        recipient = User.objects.get(id=data['recipient_id'])

        existing_request = ProjectViewRequest.objects.filter(
            project=project,
            recipient=recipient,
            status='pending'
        ).exists()

        if existing_request:
            raise serializers.ValidationError("You already have a pending request to this user for this project")

        return data
    
    def create(self, validated_data):
        """Create project view request"""
        from projects.models import Project
        request = self.context.get('request')
        
        project = Project.objects.get(id=validated_data['project_id'])
        recipient = User.objects.get(id=validated_data['recipient_id'])
        
        return ProjectViewRequest.objects.create(
            project=project,
            requester=request.user,
            recipient=recipient,
            message=validated_data['message']
        )


class ProjectViewRequestResponseSerializer(serializers.Serializer):
    """Serializer for responding to project view requests"""

    action = serializers.ChoiceField(choices=['accept', 'decline'], required=True)

    def validate_action(self, value):
        """Validate action"""
        if value not in ['accept', 'decline']:
            raise serializers.ValidationError("Action must be 'accept' or 'decline'")
        return value


class GroupMessageSerializer(serializers.ModelSerializer):
    """Serializer for group messages"""

    sender = serializers.SerializerMethodField()
    read_by = serializers.SerializerMethodField()
    is_read_by_me = serializers.SerializerMethodField()

    class Meta:
        model = GroupMessage
        fields = [
            'id', 'group_conversation', 'sender', 'content',
            'read_by', 'is_read_by_me', 'attachment', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'group_conversation', 'sender', 'read_by', 'created_at', 'updated_at']

    def get_sender(self, obj):
        """Get sender profile"""
        if hasattr(obj.sender, 'profile'):
            return UserProfileSerializer(obj.sender.profile, context=self.context).data
        return None

    def get_read_by(self, obj):
        """Get list of users who have read this message"""
        users = obj.read_by.all()
        return [
            UserProfileSerializer(user.profile, context=self.context).data
            for user in users if hasattr(user, 'profile')
        ]

    def get_is_read_by_me(self, obj):
        """Check if current user has read this message"""
        request = self.context.get('request')
        if request and request.user:
            return obj.read_by.filter(id=request.user.id).exists()
        return False

    def create(self, validated_data):
        """Create group message with sender from request"""
        request = self.context.get('request')
        validated_data['sender'] = request.user
        return super().create(validated_data)


class GroupConversationListSerializer(serializers.ModelSerializer):
    """Serializer for listing group conversations"""

    participants = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    project = ProjectSerializer(read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()

    class Meta:
        model = GroupConversation
        fields = [
            'id', 'project', 'created_by', 'participants', 'participant_count',
            'created_at', 'updated_at', 'last_message_at', 'last_message', 'unread_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_message_at']

    def get_participants(self, obj):
        """Get list of participants"""
        users = obj.participants.all()
        return [
            UserProfileSerializer(user.profile, context=self.context).data
            for user in users if hasattr(user, 'profile')
        ]

    def get_created_by(self, obj):
        """Get creator profile"""
        if hasattr(obj.created_by, 'profile'):
            return UserProfileSerializer(obj.created_by.profile, context=self.context).data
        return None

    def get_last_message(self, obj):
        """Get the last message in the group conversation"""
        last_msg = obj.group_messages.order_by('-created_at').first()
        if last_msg:
            return {
                'id': str(last_msg.id),
                'content': last_msg.content[:100],  # Preview only
                'sender': {
                    'id': last_msg.sender.id,
                    'username': last_msg.sender.username,
                },
                'created_at': last_msg.created_at,
            }
        return None

    def get_unread_count(self, obj):
        """Get unread message count for current user"""
        request = self.context.get('request')
        if request and request.user:
            return obj.get_unread_count(request.user)
        return 0

    def get_participant_count(self, obj):
        """Get total participant count"""
        return obj.participants.count()


class GroupConversationDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed group conversation view with messages"""

    participants = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    project = ProjectSerializer(read_only=True)
    group_messages = GroupMessageSerializer(many=True, read_only=True)
    is_participant = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()

    class Meta:
        model = GroupConversation
        fields = [
            'id', 'project', 'created_by', 'participants', 'participant_count', 'group_messages',
            'created_at', 'updated_at', 'last_message_at', 'is_participant'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_message_at']

    def get_participants(self, obj):
        """Get list of participants"""
        users = obj.participants.all()
        return [
            UserProfileSerializer(user.profile, context=self.context).data
            for user in users if hasattr(user, 'profile')
        ]

    def get_created_by(self, obj):
        """Get creator profile"""
        if hasattr(obj.created_by, 'profile'):
            return UserProfileSerializer(obj.created_by.profile, context=self.context).data
        return None

    def get_is_participant(self, obj):
        """Check if current user is a participant"""
        request = self.context.get('request')
        if request and request.user:
            return obj.is_participant(request.user)
        return False

    def get_participant_count(self, obj):
        """Get total participant count"""
        return obj.participants.count()


class CreateGroupConversationSerializer(serializers.Serializer):
    """Serializer for creating a group conversation for a project team"""

    project_id = serializers.UUIDField(required=True)
    initial_message = serializers.CharField(max_length=5000, required=True)

    def validate_project_id(self, value):
        """Validate project exists"""
        from projects.models import Project
        try:
            project = Project.objects.get(id=value)
        except Project.DoesNotExist:
            raise serializers.ValidationError("Project not found")
        return value

    def validate(self, data):
        """Validate user can create group conversation"""
        from projects.models import Project
        request = self.context.get('request')
        project = Project.objects.get(id=data['project_id'])

        # Check if user has permission (professor/investor/mentor)
        if not hasattr(request.user, 'profile'):
            raise serializers.ValidationError("User must have a profile")

        if request.user.profile.user_role not in ['professor', 'investor', 'mentor']:
            raise serializers.ValidationError("Only professors, investors, and mentors can create group conversations")

        # Check if group conversation already exists for this project by this user
        existing_group = GroupConversation.objects.filter(
            project=project,
            created_by=request.user
        ).first()

        if existing_group:
            raise serializers.ValidationError({
                "existing_conversation_id": str(existing_group.id),
                "message": "You already have a group conversation for this project"
            })

        return data

    def create(self, validated_data):
        """Create group conversation with project team members"""
        from projects.models import Project
        from django.db import transaction

        request = self.context.get('request')
        project = Project.objects.get(id=validated_data['project_id'])

        with transaction.atomic():
            # Create group conversation
            group_conv = GroupConversation.objects.create(
                project=project,
                created_by=request.user
            )

            # Add all team members as participants (owner + team members)
            all_members = list(project.all_team_members)

            print(f"DEBUG: Adding {len(all_members)} team members to group conversation")
            print(f"DEBUG: Team members: {[m.username for m in all_members]}")

            # Add creator (investor/professor)
            group_conv.participants.add(request.user)

            # Add all team members
            group_conv.participants.add(*all_members)

            # Verify participants were added
            participant_count = group_conv.participants.count()
            print(f"DEBUG: Group conversation now has {participant_count} participants")

            # Create initial message (without triggering read_by in save)
            message = GroupMessage(
                group_conversation=group_conv,
                sender=request.user,
                content=validated_data['initial_message']
            )
            message.save()

            # Now add sender to read_by after the message is saved
            message.read_by.add(request.user)

            print(f"DEBUG: Created initial message with ID: {message.id}")

        return group_conv

