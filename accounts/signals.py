"""
Signal handlers for accounts app
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .email_utils import send_welcome_email, send_verification_email

User = get_user_model()
logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def send_welcome_and_verification_emails(sender, instance, created, **kwargs):
    """
    Send welcome and verification emails when a new user is created
    
    Args:
        sender: The User model
        instance: The newly created User instance
        created: Boolean indicating if this is a new user
        **kwargs: Additional keyword arguments
    """
    if created:
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        from django.conf import settings
        from django.utils import timezone
        from .models import UserProfile
        
        try:
            # Ensure profile exists (get or create)
            profile, profile_created = UserProfile.objects.get_or_create(user=instance)
            
            # Send welcome email
            request = kwargs.get('request', None)
            send_welcome_email(instance, request)
            
            # Generate verification token and URL
            uid = urlsafe_base64_encode(force_bytes(str(instance.pk)))
            if isinstance(uid, bytes):
                uid = uid.decode('utf-8')
            
            token = default_token_generator.make_token(instance)
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            verification_url = f"{frontend_url}/verify-email/{uid}/{token}/"
            
            # Send verification email
            send_verification_email(instance, verification_url)
            
            # Update verification_sent_at timestamp
            profile.verification_sent_at = timezone.now()
            profile.save()
            
        except Exception as e:
            # Log error but don't fail registration
            logger.error(f"Failed to send emails to {instance.email}: {e}", exc_info=True)

