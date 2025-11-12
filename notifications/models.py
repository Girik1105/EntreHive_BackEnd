from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid


class Notification(models.Model):
    """
    Notification model to store user notifications
    """
    
    NOTIFICATION_TYPES = [
        ('follow', 'New Follower'),
        ('like', 'Post Like'),
        ('comment', 'Post Comment'),
        ('project_invite', 'Project Invitation'),
        ('project_join', 'Project Join Request'),
        ('mention', 'Mention'),
        ('message', 'New Message'),
        ('announcement', 'Announcement'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='notifications'
    )
    sender = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='sent_notifications',
        null=True,
        blank=True
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Optional reference to related objects
    post_id = models.UUIDField(null=True, blank=True)
    project_id = models.UUIDField(null=True, blank=True)
    comment_id = models.UUIDField(null=True, blank=True)
    conversation_id = models.UUIDField(null=True, blank=True)
    message_id = models.UUIDField(null=True, blank=True)

    # Link for notification action
    action_url = models.CharField(max_length=500, blank=True, null=True)

    # Notification grouping
    notification_group_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    is_grouped = models.BooleanField(default=False)
    group_count = models.IntegerField(default=1)

    # Rich media support
    image_url = models.CharField(max_length=500, null=True, blank=True)
    thumbnail_url = models.CharField(max_length=500, null=True, blank=True)

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.notification_type} for {self.recipient.username}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])
    
    @classmethod
    def create_follow_notification(cls, follower, following):
        """Create a notification when someone follows a user"""
        # Check user preferences
        try:
            recipient_prefs = NotificationPreference.objects.get(user=following)
            if not recipient_prefs.follow_enabled:
                return None
        except NotificationPreference.DoesNotExist:
            # If no preferences exist, create with defaults (enabled)
            NotificationPreference.objects.create(user=following)

        return cls.objects.create(
            recipient=following,
            sender=follower,
            notification_type='follow',
            title='New Follower',
            message=f'{follower.get_full_name() or follower.username} started following you',
            action_url=f'/profiles/{follower.username}'
        )
    
    @classmethod
    def create_like_notification(cls, liker, post):
        """Create a notification when someone likes a post"""
        # Don't notify users when they like their own post
        if liker == post.author:
            return None

        # Check user preferences
        try:
            recipient_prefs = NotificationPreference.objects.get(user=post.author)
            if not recipient_prefs.like_enabled:
                return None
        except NotificationPreference.DoesNotExist:
            # If no preferences exist, create with defaults (enabled)
            NotificationPreference.objects.create(user=post.author)

        return cls.objects.create(
            recipient=post.author,
            sender=liker,
            notification_type='like',
            title='New Like',
            message=f'{liker.get_full_name() or liker.username} liked your post',
            post_id=post.id,
            action_url=f'/posts/{post.id}'
        )
    
    @classmethod
    def create_comment_notification(cls, commenter, post, comment, is_reply=False):
        """Create a notification when someone comments on a post or replies to a comment"""
        if is_reply:
            recipient = comment.parent.author
            title = 'New Reply'
            message = f'{commenter.get_full_name() or commenter.username} replied to your comment'
        else:
            recipient = post.author
            title = 'New Comment'
            message = f'{commenter.get_full_name() or commenter.username} commented on your post'

        # Don't notify users when they comment on their own post
        if commenter == recipient:
            return None

        # Check user preferences
        try:
            recipient_prefs = NotificationPreference.objects.get(user=recipient)
            if not recipient_prefs.comment_enabled:
                return None
        except NotificationPreference.DoesNotExist:
            # If no preferences exist, create with defaults (enabled)
            NotificationPreference.objects.create(user=recipient)

        return cls.objects.create(
            recipient=recipient,
            sender=commenter,
            notification_type='comment',
            title=title,
            message=message,
            post_id=post.id,
            comment_id=comment.id,
            action_url=f'/posts/{post.id}'
        )
    
    @classmethod
    def create_mention_notification(cls, mentioner, mentioned_user, post, comment=None):
        """Create a notification when someone mentions a user in a post or comment"""
        # Don't notify users when they mention themselves
        if mentioner == mentioned_user:
            return None

        # Check user preferences
        try:
            recipient_prefs = NotificationPreference.objects.get(user=mentioned_user)
            if not recipient_prefs.mention_enabled:
                return None
        except NotificationPreference.DoesNotExist:
            # If no preferences exist, create with defaults (enabled)
            NotificationPreference.objects.create(user=mentioned_user)

        if comment:
            title = 'Mentioned in Comment'
            message = f'{mentioner.get_full_name() or mentioner.username} mentioned you in a comment'
            comment_id = comment.id
        else:
            title = 'Mentioned in Post'
            message = f'{mentioner.get_full_name() or mentioner.username} mentioned you in a post'
            comment_id = None

        return cls.objects.create(
            recipient=mentioned_user,
            sender=mentioner,
            notification_type='mention',
            title=title,
            message=message,
            post_id=post.id,
            comment_id=comment_id,
            action_url=f'/posts/{post.id}'
        )

    @classmethod
    def create_project_invite_notification(cls, inviter, invitee, project_id, project_title):
        """Create a notification when someone invites a user to a project"""
        # Check user preferences
        try:
            recipient_prefs = NotificationPreference.objects.get(user=invitee)
            if not recipient_prefs.project_invite_enabled:
                return None
        except NotificationPreference.DoesNotExist:
            # If no preferences exist, create with defaults (enabled)
            NotificationPreference.objects.create(user=invitee)

        return cls.objects.create(
            recipient=invitee,
            sender=inviter,
            notification_type='project_invite',
            title='Project Invitation',
            message=f'{inviter.get_full_name() or inviter.username} invited you to join {project_title}',
            project_id=project_id,
            action_url=f'/projects/{project_id}'
        )

    @classmethod
    def create_project_join_notification(cls, joiner, project_owner, project_id, project_title):
        """Create a notification when someone joins a project"""
        if joiner == project_owner:
            return None  # Don't notify owner when they join their own project

        # Check user preferences
        try:
            recipient_prefs = NotificationPreference.objects.get(user=project_owner)
            if not recipient_prefs.project_join_enabled:
                return None
        except NotificationPreference.DoesNotExist:
            # If no preferences exist, create with defaults (enabled)
            NotificationPreference.objects.create(user=project_owner)

        return cls.objects.create(
            recipient=project_owner,
            sender=joiner,
            notification_type='project_join',
            title='New Team Member',
            message=f'{joiner.get_full_name() or joiner.username} joined your project: {project_title}',
            project_id=project_id,
            action_url=f'/projects/{project_id}'
        )

    @classmethod
    def create_message_notification(cls, sender, recipient, message, conversation):
        """Create a notification when someone sends a direct message"""
        # Don't notify if sender and recipient are the same
        if sender == recipient:
            return None

        # Check user preferences
        try:
            recipient_prefs = NotificationPreference.objects.get(user=recipient)
            if not recipient_prefs.message_enabled:
                return None
        except NotificationPreference.DoesNotExist:
            # If no preferences exist, create with defaults (enabled)
            NotificationPreference.objects.create(user=recipient)

        # Preview of the message (first 50 characters)
        message_preview = message.content[:50] + '...' if len(message.content) > 50 else message.content

        return cls.objects.create(
            recipient=recipient,
            sender=sender,
            notification_type='message',
            title='New Message',
            message=f'{sender.get_full_name() or sender.username} sent you a message: "{message_preview}"',
            conversation_id=conversation.id,
            message_id=message.id,
            action_url=f'/inbox/direct/{conversation.id}'
        )

    @classmethod
    def create_group_message_notification(cls, sender, recipient, message, group_conversation):
        """Create a notification when someone sends a message in a group conversation"""
        # Don't notify if sender and recipient are the same
        if sender == recipient:
            return None

        # Check user preferences
        try:
            recipient_prefs = NotificationPreference.objects.get(user=recipient)
            if not recipient_prefs.message_enabled:
                return None
        except NotificationPreference.DoesNotExist:
            # If no preferences exist, create with defaults (enabled)
            NotificationPreference.objects.create(user=recipient)

        # Preview of the message (first 50 characters)
        message_preview = message.content[:50] + '...' if len(message.content) > 50 else message.content

        # Get the project title if available
        project_title = group_conversation.project.title if group_conversation.project else 'Group'

        return cls.objects.create(
            recipient=recipient,
            sender=sender,
            notification_type='message',
            title=f'New Message in {project_title}',
            message=f'{sender.get_full_name() or sender.username}: "{message_preview}"',
            conversation_id=group_conversation.id,
            message_id=message.id,
            action_url=f'/inbox/group/{group_conversation.id}'
        )


class NotificationPreference(models.Model):
    """
    User preferences for in-app notifications
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )

    # In-app notification preferences
    follow_enabled = models.BooleanField(default=True)
    like_enabled = models.BooleanField(default=True)
    comment_enabled = models.BooleanField(default=True)
    mention_enabled = models.BooleanField(default=True)
    message_enabled = models.BooleanField(default=True)
    project_invite_enabled = models.BooleanField(default=True)
    project_join_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"

    def __str__(self):
        return f"Notification preferences for {self.user.username}"


@receiver(post_save, sender=User)
def create_notification_preferences(sender, instance, created, **kwargs):
    """Create notification preferences when a new user is created"""
    if created:
        NotificationPreference.objects.create(user=instance)
