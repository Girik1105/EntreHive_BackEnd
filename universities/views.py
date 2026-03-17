from rest_framework import generics, status, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.viewsets import ModelViewSet
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
import re

from .models import University
from .serializers import (
    UniversitySerializer, 
    UniversityListSerializer, 
    UniversityCreateSerializer,
    UniversityStatsSerializer
)


class UniversityViewSet(ModelViewSet):
    """
    ViewSet for University CRUD operations
    """
    queryset = University.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['university_type', 'country', 'state_province']
    search_fields = ['name', 'short_name', 'city', 'email_domain']
    ordering_fields = ['name', 'student_count', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return UniversityListSerializer
        elif self.action == 'create':
            return UniversityCreateSerializer
        elif self.action == 'stats':
            return UniversityStatsSerializer
        return UniversitySerializer
    
    def get_permissions(self):
        """Set permissions based on action"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            # Only admin users can create/modify universities
            permission_classes = [IsAuthenticated, IsAdminUser]
        else:
            # Anyone can view universities
            permission_classes = []
        return [permission() for permission in permission_classes]
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    def update_stats(self, request, pk=None):
        """Update statistics for a specific university"""
        university = self.get_object()
        university.update_statistics()
        serializer = UniversityStatsSerializer(university)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsAdminUser])
    def update_all_stats(self, request):
        """Update statistics for all universities"""
        universities = University.objects.all()
        for university in universities:
            university.update_statistics()
        return Response({'message': f'Statistics updated for {universities.count()} universities'})
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get statistics for all universities"""
        universities = University.objects.all()
        serializer = UniversityStatsSerializer(universities, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Advanced search for universities"""
        query = request.query_params.get('q', '')
        country = request.query_params.get('country', '')
        university_type = request.query_params.get('type', '')
        
        queryset = University.objects.all()
        
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) |
                Q(short_name__icontains=query) |
                Q(city__icontains=query) |
                Q(email_domain__icontains=query)
            )
        
        if country:
            queryset = queryset.filter(country__icontains=country)
        
        if university_type:
            queryset = queryset.filter(university_type=university_type)
        
        serializer = UniversityListSerializer(queryset, many=True)
        return Response(serializer.data)


class UniversityListView(generics.ListAPIView):
    """
    Simple list view for universities
    """
    queryset = University.objects.all()
    serializer_class = UniversityListSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['university_type', 'country']
    search_fields = ['name', 'short_name', 'city']
    ordering = ['name']


class UniversityDetailView(generics.RetrieveAPIView):
    """
    Detail view for a single university
    """
    queryset = University.objects.all()
    serializer_class = UniversitySerializer
    lookup_field = 'pk'


class UniversityByCountryView(generics.ListAPIView):
    """
    List universities by country
    """
    serializer_class = UniversityListSerializer
    
    def get_queryset(self):
        country = self.kwargs.get('country')
        return University.objects.filter(country__iexact=country)


class UniversityTypesView(generics.GenericAPIView):
    """
    Get available university types
    """
    def get(self, request):
        types = [{'value': choice[0], 'label': choice[1]} for choice in University.UNIVERSITY_TYPE_CHOICES]
        return Response({'university_types': types})


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email_domain(request):
    """
    Verify if an email domain belongs to a registered university
    """
    email = request.data.get('email', '').lower().strip()
    user_role = request.data.get('user_role', 'student').lower()
    
    if not email:
        return Response(
            {'error': 'Email is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate email format
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return Response(
            {'error': 'Invalid email format'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Extract domain from email
    try:
        domain = email.split('@')[1]
    except IndexError:
        return Response(
            {'error': 'Invalid email format'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Investors and mentors can bypass university verification
    if user_role in ['investor', 'mentor']:
        return Response({
            'verified': True,
            'university': None,
            'message': 'Investors and mentors can register without university affiliation',
            'bypass_reason': user_role
        })
    
    # Check if domain matches any university
    # Look for universities with email_domain that matches
    university = None
    
    # Try exact domain match first
    university = University.objects.filter(email_domain__iexact=domain).first()
    
    # If no exact match, try with @ prefix (in case stored with @)
    if not university:
        university = University.objects.filter(email_domain__iexact=f'@{domain}').first()
    
    # If still no match, try without @ prefix (in case stored without @)
    if not university:
        university = University.objects.filter(email_domain__iexact=domain.replace('@', '')).first()
    
    if university:
        return Response({
            'verified': True,
            'university': {
                'id': str(university.id),
                'name': university.name,
                'short_name': university.short_name,
                'city': university.city,
                'country': university.country
            },
            'message': f'Email domain verified for {university.name}'
        })
    else:
        return Response({
            'verified': False,
            'university': None,
            'message': f'Email domain "{domain}" is not associated with any registered university. Please contact your university administrator or use a different email.',
            'domain': domain
        }, status=status.HTTP_403_FORBIDDEN)


@api_view(['GET'])
@permission_classes([AllowAny])
def search_universities_by_domain(request):
    """
    Search universities by partial domain match (for suggestions)
    """
    query = request.query_params.get('domain', '').lower().strip()
    
    if not query or len(query) < 3:
        return Response(
            {'error': 'Domain query must be at least 3 characters'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Search for universities with similar domains
    universities = University.objects.filter(
        Q(email_domain__icontains=query) |
        Q(name__icontains=query) |
        Q(short_name__icontains=query)
    ).values('id', 'name', 'short_name', 'email_domain', 'city', 'country')[:10]
    
    return Response({
        'suggestions': list(universities),
        'count': len(universities)
    })
