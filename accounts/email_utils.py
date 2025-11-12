"""
Email utility functions for sending beautiful HTML emails
"""
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from datetime import datetime


def send_welcome_email(user, request=None):
    """
    Send a welcome email to a newly registered user
    
    Args:
        user: User object
        request: HttpRequest object (optional, for getting IP address)
    """
    try:
        # Get user profile
        profile = user.profile
        user_name = profile.get_full_name() or user.username
        
        # Prepare context for template
        context = {
            'user_name': user_name,
            'user_email': user.email,
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'http://localhost:3000'),
        }
        
        # Render HTML and plain text emails
        html_message = render_to_string('accounts/emails/welcome.html', context)
        plain_message = render_to_string('accounts/emails/welcome.txt', context)
        
        # Send email
        send_mail(
            subject='Welcome to Entrehive',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )

        return True
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False


def send_password_reset_email(user, reset_url):
    """
    Send a password reset email with a beautiful HTML template
    
    Args:
        user: User object
        reset_url: Password reset URL with token
    """
    try:
        # Get user profile
        profile = user.profile
        user_name = profile.get_full_name() or user.username
        
        # Prepare context for template
        context = {
            'user_name': user_name,
            'user_email': user.email,
            'reset_url': reset_url,
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'http://localhost:3000'),
        }
        
        # Render HTML and plain text emails
        html_message = render_to_string('accounts/emails/password_reset.html', context)
        plain_message = render_to_string('accounts/emails/password_reset.txt', context)
        
        # Send email
        send_mail(
            subject='Reset Your Entrehive Password',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        return True
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False


def send_password_changed_email(user, request=None):
    """
    Send a confirmation email when password is successfully changed
    
    Args:
        user: User object
        request: HttpRequest object (optional, for getting IP address)
    """
    try:
        # Get user profile
        profile = user.profile
        user_name = profile.get_full_name() or user.username
        
        # Get IP address if request is available
        user_ip = 'Unknown'
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                user_ip = x_forwarded_for.split(',')[0]
            else:
                user_ip = request.META.get('REMOTE_ADDR', 'Unknown')
        
        # Get current date and time
        change_date = datetime.now().strftime('%B %d, %Y at %I:%M %p UTC')
        
        # Prepare context for template
        context = {
            'user_name': user_name,
            'user_email': user.email,
            'change_date': change_date,
            'user_ip': user_ip,
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'http://localhost:3000'),
        }
        
        # Render HTML and plain text emails
        html_message = render_to_string('accounts/emails/password_changed.html', context)
        plain_message = render_to_string('accounts/emails/password_changed.txt', context)
        
        # Send email
        send_mail(
            subject='Your Entrehive Password Was Changed',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        return True
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False


def send_verification_email(user, verification_url):
    """
    Send an email verification link to the user
    
    Args:
        user: User object
        verification_url: Email verification URL with token
    """
    try:
        # Get user profile
        profile = user.profile
        user_name = profile.get_full_name() or user.username
        
        # Prepare context for template
        context = {
            'user_name': user_name,
            'user_email': user.email,
            'verification_url': verification_url,
            'frontend_url': getattr(settings, 'FRONTEND_URL', 'http://localhost:3000'),
        }
        
        # Render HTML and plain text emails
        html_message = render_to_string('accounts/emails/email_verification.html', context)
        plain_message = render_to_string('accounts/emails/email_verification.txt', context)
        
        # Send email
        send_mail(
            subject='Verify Your Entrehive Email Address',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        return True
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False

