"""
Investor-specific project views
Separate from student/professor views to provide restricted access
"""

from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Project
from .serializers import ProjectSerializer


def is_investor(user):
    """Check if user has investor role"""
    return hasattr(user, 'profile') and user.profile.user_role == 'investor'


class InvestorProjectDetailView(generics.RetrieveAPIView):
    """
    Investor-specific project detail view
    Investors can only view public and university projects
    They cannot edit or see private projects unless explicitly granted access
    
    GET /api/projects/investor/<project_id>/
    """
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        """Restrict to approved public and university projects only"""
        user = self.request.user

        # Only allow investors to use this endpoint
        if not is_investor(user):
            return Project.objects.none()

        # Investors can view:
        # 1. Approved public projects
        # 2. Approved university projects (if they have a university set)
        queryset = Project.objects.filter(
            visibility='public',
            approval_status='approved'
        ).select_related(
            'owner__profile', 'university'
        ).prefetch_related(
            'team_members__profile'
        )

        # Add university projects if investor has university set
        if hasattr(user, 'profile') and user.profile.university:
            from django.db.models import Q
            queryset = Project.objects.filter(
                Q(visibility='public') |
                Q(visibility='university', university=user.profile.university)
            ).filter(
                approval_status='approved'
            ).select_related(
                'owner__profile', 'university'
            ).prefetch_related(
                'team_members__profile'
            )

        return queryset
    
    def retrieve(self, request, *args, **kwargs):
        """
        Override to provide investor-specific project data
        Excludes sensitive information that students/professors might see
        """
        try:
            instance = self.get_object()
        except:
            return Response(
                {
                    'error': 'Project not found or you do not have permission to view this project.',
                    'detail': 'Investors can only view public and university projects.'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        # Add investor-specific context
        data['is_investor_view'] = True
        data['can_send_request'] = True  # Investors can always message students
        
        return Response(data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def check_investor_access(request):
    """
    Check if current user is an investor
    GET /api/projects/investor/check-access/
    """
    if is_investor(request.user):
        return Response({
            'is_investor': True,
            'message': 'Access granted'
        })
    
    return Response({
        'is_investor': False,
        'message': 'Access denied. This feature is only available to investors.'
    }, status=status.HTTP_403_FORBIDDEN)

