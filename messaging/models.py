from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import uuid


class Conversation(models.Model):
    """
    Conversation between two users
    Email-like inbox system where conversations can be initiated based on roles
    """
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Participants (exactly 2 users)
    participant_1 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='conversations_as_p1'
    )
    participant_2 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='conversations_as_p2'
    )
    
    # Track who initiated the conversation
    initiated_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='initiated_conversations'
    )
    
    # Related project (if conversation is about a project)
    related_project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversations'
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Track if participants have archived
    archived_by_p1 = models.BooleanField(default=False)
    archived_by_p2 = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"
        ordering = ['-last_message_at', '-created_at']
        # Ensure no duplicate conversations
        unique_together = [['participant_1', 'participant_2']]
    
    def __str__(self):
        return f"Conversation: {self.participant_1.username} & {self.participant_2.username}"
    
    def clean(self):
        """Prevent users from creating conversation with themselves"""
        if self.participant_1 == self.participant_2:
            raise ValidationError("Cannot create conversation with yourself")
    
    def save(self, *args, **kwargs):
        # Ensure participant_1 has lower ID to maintain consistent ordering
        if self.participant_1.id > self.participant_2.id:
            self.participant_1, self.participant_2 = self.participant_2, self.participant_1
        
        self.clean()
        super().save(*args, **kwargs)
    
    def get_other_participant(self, user):
        """Get the other participant in the conversation"""
        if user == self.participant_1:
            return self.participant_2
        return self.participant_1
    
    def is_participant(self, user):
        """Check if user is a participant in this conversation"""
        return user == self.participant_1 or user == self.participant_2
    
    def get_unread_count(self, user):
        """Get unread message count for a user"""
        return self.messages.exclude(sender=user).filter(read=False).count()

    def mark_as_read(self, user):
        """Mark all messages as read for a user"""
        self.messages.exclude(sender=user).filter(read=False).update(read=True)


class Message(models.Model):
    """
    Individual message in a conversation
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    
    content = models.TextField(max_length=5000, help_text="Message content")
    
    # Message metadata
    read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Optional: attach files/images
    attachment = models.FileField(
        upload_to='message_attachments/',
        null=True,
        blank=True,
        help_text="Optional file attachment"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ['created_at']
    
    def __str__(self):
        return f"Message from {self.sender.username} at {self.created_at}"
    
    def save(self, *args, **kwargs):
        # Update conversation's last_message_at
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            self.conversation.last_message_at = self.created_at
            self.conversation.save(update_fields=['last_message_at', 'updated_at'])
    
    def mark_as_read(self):
        """Mark message as read"""
        if not self.read:
            from django.utils import timezone
            self.read = True
            self.read_at = timezone.now()
            self.save(update_fields=['read', 'read_at'])


class ProjectViewRequest(models.Model):
    """
    Request from a student to allow a professor or investor to view their project
    Students cannot directly message, but can send project view requests
    Once accepted, creates a conversation where direct messaging is allowed
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='view_requests'
    )
    
    # Student sending the request
    requester = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_project_requests'
    )
    
    # Professor or Investor receiving the request
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_project_requests'
    )
    
    message = models.TextField(
        max_length=1000,
        help_text="Message to the professor/investor about why you want them to view your project"
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Once accepted, link to the created conversation
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='originated_from_request'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Project View Request"
        verbose_name_plural = "Project View Requests"
        ordering = ['-created_at']
        # Prevent duplicate requests for same project to same person
        unique_together = [['project', 'recipient']]
    
    def __str__(self):
        return f"{self.requester.username} → {self.recipient.username}: {self.project.title}"
    
    def clean(self):
        """Validate that requester is student and recipient is professor/investor"""
        if not hasattr(self.requester, 'profile'):
            raise ValidationError("Requester must have a profile")
        
        if self.requester.profile.user_role != 'student':
            raise ValidationError("Only students can send project view requests")
        
        if not hasattr(self.recipient, 'profile'):
            raise ValidationError("Recipient must have a profile")
        
        if self.recipient.profile.user_role not in ['professor', 'investor']:
            raise ValidationError("Project view requests can only be sent to professors or investors")
        
        # Ensure requester is owner or team member of the project
        if not self.project.is_team_member(self.requester):
            raise ValidationError("You must be a member of the project to send view requests")
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def accept(self):
        """Accept the request and create a conversation"""
        if self.status != 'pending':
            return False
        
        from django.utils import timezone
        
        # Update status
        self.status = 'accepted'
        self.responded_at = timezone.now()
        
        # Create conversation if it doesn't exist
        if not self.conversation:
            # Check if conversation already exists between these users
            existing_conv = Conversation.objects.filter(
                models.Q(participant_1=self.requester, participant_2=self.recipient) |
                models.Q(participant_1=self.recipient, participant_2=self.requester)
            ).first()
            
            if existing_conv:
                self.conversation = existing_conv
            else:
                # Create new conversation
                self.conversation = Conversation.objects.create(
                    participant_1=self.requester,
                    participant_2=self.recipient,
                    initiated_by=self.requester,
                    related_project=self.project
                )
                
                # Create initial system message in the conversation
                Message.objects.create(
                    conversation=self.conversation,
                    sender=self.recipient,
                    content=f"I've accepted your request to view your project: {self.project.title}. Feel free to share more details!"
                )
        
        self.save()
        return True
    
    def decline(self):
        """Decline the request"""
        if self.status != 'pending':
            return False
        
        from django.utils import timezone
        self.status = 'declined'
        self.responded_at = timezone.now()
        self.save()
        return True
    
    def cancel(self):
        """Cancel the request (by requester)"""
        if self.status != 'pending':
            return False
        
        from django.utils import timezone
        self.status = 'cancelled'
        self.responded_at = timezone.now()
        self.save()
        return True


class MessagePermission(models.Model):
    """
    Track messaging permissions between users
    Professors and investors can message students directly
    Students can only message back after receiving a message or having request accepted
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Who can message whom
    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='messaging_permissions_from'
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='messaging_permissions_to'
    )
    
    # How permission was granted
    GRANT_TYPE_CHOICES = [
        ('role_based', 'Role Based'),  # Professor/Investor can message students
        ('request_accepted', 'Request Accepted'),  # Student's request was accepted
        ('replied', 'Replied'),  # User replied to a message
    ]
    
    grant_type = models.CharField(max_length=20, choices=GRANT_TYPE_CHOICES)
    
    # Related conversation
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='permissions',
        null=True,
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Message Permission"
        verbose_name_plural = "Message Permissions"
        unique_together = [['from_user', 'to_user', 'conversation']]
    
    def __str__(self):
        return f"{self.from_user.username} can message {self.to_user.username}"
    
    @staticmethod
    def can_message(from_user, to_user, conversation=None):
        """
        Check if from_user can send message to to_user
        Rules:
        1. Same roles can message each other freely (student-to-student, professor-to-professor, investor-to-investor)
        2. Professors and investors can always message students
        3. Students can message professors/investors if they have permission:
           - They've received a message in the conversation
           - Their project view request was accepted
        """
        if not hasattr(from_user, 'profile') or not hasattr(to_user, 'profile'):
            return False

        from_role = from_user.profile.user_role
        to_role = to_user.profile.user_role

        # Rule 1: Same roles can message each other freely
        if from_role == to_role:
            return True

        # Rule 2: Professors and investors can message students
        if from_role in ['professor', 'investor'] and to_role == 'student':
            return True

        # Rule 3: Students can message professors/investors if they have permission
        if from_role == 'student' and to_role in ['professor', 'investor']:
            # Check if there's an existing permission
            has_permission = MessagePermission.objects.filter(
                from_user=from_user,
                to_user=to_user
            ).exists()

            if has_permission:
                return True

            # Check if student received any messages from this professor/investor
            if conversation:
                received_message = Message.objects.filter(
                    conversation=conversation,
                    sender=to_user
                ).exists()

                if received_message:
                    # Grant permission for future
                    MessagePermission.objects.get_or_create(
                        from_user=from_user,
                        to_user=to_user,
                        conversation=conversation,
                        defaults={'grant_type': 'replied'}
                    )
                    return True

            return False

        # Default: deny
        return False
    
    @staticmethod
    def grant_permission(from_user, to_user, conversation, grant_type='request_accepted'):
        """Grant messaging permission"""
        permission, created = MessagePermission.objects.get_or_create(
            from_user=from_user,
            to_user=to_user,
            conversation=conversation,
            defaults={'grant_type': grant_type}
        )
        return permission


class GroupConversation(models.Model):
    """
    Group conversation for team messaging
    Allows professors/investors to contact entire project teams
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Related project (required for group conversations)
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='group_conversations'
    )

    # Creator of the group conversation
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_group_conversations'
    )

    # Participants (project team members + creator)
    participants = models.ManyToManyField(
        User,
        related_name='group_conversations',
        help_text="All participants in the group conversation"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Group Conversation"
        verbose_name_plural = "Group Conversations"
        ordering = ['-last_message_at', '-created_at']

    def __str__(self):
        return f"Group: {self.project.title} ({self.participants.count()} members)"

    def is_participant(self, user):
        """Check if user is a participant"""
        return self.participants.filter(id=user.id).exists()

    def get_unread_count(self, user):
        """Get unread message count for a user"""
        return self.group_messages.exclude(sender=user).exclude(
            read_by=user
        ).count()


class GroupMessage(models.Model):
    """
    Message in a group conversation
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    group_conversation = models.ForeignKey(
        GroupConversation,
        on_delete=models.CASCADE,
        related_name='group_messages'
    )

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_group_messages'
    )

    content = models.TextField(max_length=5000, help_text="Message content")

    # Track who has read the message (ManyToMany)
    read_by = models.ManyToManyField(
        User,
        related_name='read_group_messages',
        blank=True
    )

    # Optional: attach files/images
    attachment = models.FileField(
        upload_to='group_message_attachments/',
        null=True,
        blank=True,
        help_text="Optional file attachment"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Group Message"
        verbose_name_plural = "Group Messages"
        ordering = ['created_at']

    def __str__(self):
        return f"Group Message from {self.sender.username} at {self.created_at}"

    def save(self, *args, **kwargs):
        # Update group conversation's last_message_at
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new:
            self.group_conversation.last_message_at = self.created_at
            self.group_conversation.save(update_fields=['last_message_at', 'updated_at'])

    def mark_as_read_by(self, user):
        """Mark message as read by a specific user"""
        if user not in self.read_by.all():
            self.read_by.add(user)
