import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()
logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
def custom_password_reset_confirm(request):
    """
    Custom password reset confirm view that properly handles uid decoding
    """
    uid = request.data.get('uid')
    token = request.data.get('token')
    new_password1 = request.data.get('new_password1')
    new_password2 = request.data.get('new_password2')
    
    # Validate required fields
    if not all([uid, token, new_password1, new_password2]):
        return Response(
            {'error': 'All fields are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if passwords match
    if new_password1 != new_password2:
        return Response(
            {'new_password2': ['Passwords do not match']},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Decode uid to get user_id
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist) as e:
        logger.error(f"Password reset: Error decoding uid or finding user - UID: {uid}, Error: {e}", exc_info=True)
        return Response(
            {'uid': ['Invalid value']},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate token
    if not default_token_generator.check_token(user, token):
        return Response(
            {'token': ['Invalid or expired token']},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate password
    try:
        validate_password(new_password1, user=user)
    except ValidationError as e:
        return Response(
            {'new_password1': list(e.messages)},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Set new password
    user.set_password(new_password1)
    user.save()
    
    # Send password changed confirmation email
    try:
        from .email_utils import send_password_changed_email
        send_password_changed_email(user, request)
    except Exception as e:
        # Log the error but don't fail the password reset
        logger.error(f"Failed to send password changed email to user {user.id}: {e}", exc_info=True)
    
    return Response(
        {'detail': 'Password has been reset successfully'},
        status=status.HTTP_200_OK
    )

