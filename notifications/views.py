from rest_framework import viewsets, status, generics
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from .models import Notification, NotificationPreference
from .serializers import NotificationSerializer, NotificationListSerializer, NotificationPreferenceSerializer


class NotificationPagination(PageNumberPagination):
    """Pagination class for notifications"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user notifications
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination
    
    def get_queryset(self):
        """Return notifications for the current user"""
        return Notification.objects.filter(
            recipient=self.request.user
        ).select_related('sender', 'sender__profile').order_by('-created_at')
    
    def get_serializer_class(self):
        """Use list serializer for list actions"""
        if self.action == 'list':
            return NotificationListSerializer
        return NotificationSerializer
    
    def list(self, request, *args, **kwargs):
        """Get all notifications for current user"""
        queryset = self.get_queryset()

        # Filter by read status if specified
        is_read = request.query_params.get('is_read', None)
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == 'true')

        # Check if using simple limit (for RightSidebar) or pagination
        limit = request.query_params.get('limit', None)
        if limit and not request.query_params.get('page'):
            # Simple limit for RightSidebar - no pagination
            queryset = queryset[:int(limit)]
            serializer = self.get_serializer(queryset, many=True)

            # Get unread count
            unread_count = Notification.objects.filter(
                recipient=request.user,
                is_read=False
            ).count()

            return Response({
                'notifications': serializer.data,
                'unread_count': unread_count,
                'total_count': self.get_queryset().count()
            })

        # Use pagination for full notification list
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)

            # Get unread count
            unread_count = Notification.objects.filter(
                recipient=request.user,
                is_read=False
            ).count()

            # Get paginated response and add extra data
            response = self.get_paginated_response(serializer.data)
            response.data['unread_count'] = unread_count
            response.data['total_count'] = queryset.count()
            return response

        # Fallback (should not reach here)
        serializer = self.get_serializer(queryset, many=True)
        unread_count = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()

        return Response({
            'notifications': serializer.data,
            'unread_count': unread_count,
            'total_count': queryset.count()
        })
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark a specific notification as read"""
        notification = self.get_object()
        notification.mark_as_read()
        return Response({'status': 'notification marked as read'})
    
    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """Mark all notifications as read for current user"""
        count = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(is_read=True)
        return Response({'status': f'{count} notifications marked as read'})
    
    @action(detail=False, methods=['delete'])
    def delete_all_read(self, request):
        """Delete all read notifications for current user"""
        count, _ = Notification.objects.filter(
            recipient=request.user,
            is_read=True
        ).delete()
        return Response({'status': f'{count} notifications deleted'})
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications"""
        count = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()
        return Response({'unread_count': count})

    def destroy(self, request, *args, **kwargs):
        """Delete a specific notification"""
        notification = self.get_object()
        if notification.recipient != request.user:
            return Response(
                {'error': 'You can only delete your own notifications'},
                status=status.HTTP_403_FORBIDDEN
            )
        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'])
    def bulk_action(self, request):
        """Perform bulk actions on notifications"""
        action_type = request.data.get('action')
        notification_ids = request.data.get('notification_ids', [])

        if not action_type or not notification_ids:
            return Response(
                {'error': 'action and notification_ids are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get notifications for current user only
        notifications = Notification.objects.filter(
            id__in=notification_ids,
            recipient=request.user
        )

        if action_type == 'mark_read':
            count = notifications.update(is_read=True)
            return Response({'status': f'{count} notifications marked as read'})
        elif action_type == 'mark_unread':
            count = notifications.update(is_read=False)
            return Response({'status': f'{count} notifications marked as unread'})
        elif action_type == 'delete':
            count, _ = notifications.delete()
            return Response({'status': f'{count} notifications deleted'})
        else:
            return Response(
                {'error': 'Invalid action. Use mark_read, mark_unread, or delete'},
                status=status.HTTP_400_BAD_REQUEST
            )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_follow_suggestions(request):
    """
    Get user suggestions for following based on:
    - Same university
    - Mutual followers
    - Similar interests (same projects, etc.)
    """
    from django.contrib.auth.models import User
    from accounts.models import Follow
    from accounts.serializers import PublicUserProfileSerializer
    
    current_user = request.user
    
    # Get users already following
    following_ids = Follow.objects.filter(
        follower=current_user
    ).values_list('following_id', flat=True)
    
    # Exclude current user and already following
    exclude_ids = list(following_ids) + [current_user.id]
    
    # Get user's university
    user_university = None
    if hasattr(current_user, 'profile'):
        user_university = current_user.profile.university
    
    # Build suggestions query
    suggestions = User.objects.exclude(id__in=exclude_ids)
    
    # Prioritize same university
    if user_university:
        suggestions = suggestions.filter(
            Q(profile__university=user_university)
        )
    
    # Limit to 5-10 suggestions
    limit = int(request.query_params.get('limit', 5))
    suggestions = suggestions.select_related('profile').order_by('?')[:limit]
    
    # Get the profiles to serialize
    profiles = [user.profile for user in suggestions if hasattr(user, 'profile')]
    
    # Serialize the suggestions
    serializer = PublicUserProfileSerializer(profiles, many=True, context={'request': request})
    
    return Response({
        'suggestions': serializer.data,
        'count': len(serializer.data)
    })


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    """
    Get and update notification preferences for the current user
    """
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        """Get or create notification preferences for current user"""
        obj, created = NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        return obj
