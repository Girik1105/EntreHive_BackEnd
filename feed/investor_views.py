from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.contrib.auth.models import User
from projects.models import Project
from posts.models import Post
from projects.serializers import ProjectSerializer
from posts.serializers import PostSerializer


def is_investor(user):
    """Check if user has investor role"""
    return hasattr(user, 'profile') and user.profile.user_role == 'investor'


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def investor_feed(request):
    """
    Investor feed endpoint with topic filtering, university filtering, and search
    GET /api/feed/investor/
    
    Query Parameters:
    - feed_type: 'public' or 'university' (default: 'public')
    - university_id: Filter by university (only for university feed)
    - topics: Comma-separated list of topics (e.g., 'AI,Web Dev,Fintech')
    - search: Search query for title/keywords
    - quick_filter: 'funding', 'prototype', 'hiring'
    - sort: 'best_match', 'recent', 'saved' (default: 'best_match')
    - cursor: Pagination cursor (created_at timestamp)
    - limit: Number of results (default: 12, max: 50)
    """
    
    # Check if user is investor
    if not is_investor(request.user):
        return Response(
            {'error': 'Access denied. This feature is only available to investors.'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get query parameters
    feed_type = request.GET.get('feed_type', 'public')
    university_id = request.GET.get('university_id', None)
    topics_str = request.GET.get('topics', '')
    search_query = request.GET.get('search', '')
    quick_filter = request.GET.get('quick_filter', None)
    sort_by = request.GET.get('sort', 'best_match')
    cursor = request.GET.get('cursor', None)
    limit = min(int(request.GET.get('limit', 12)), 50)
    
    # Parse topics
    topics = [t.strip() for t in topics_str.split(',') if t.strip()] if topics_str else []
    
    # If no topics specified, use investor's interests
    user_interests = []
    if not topics and hasattr(request.user, 'profile'):
        user_interests = request.user.profile.interests if request.user.profile.interests else []
        topics = user_interests
    
    # Base project query (without JSONField filters for SQLite compatibility)
    # Only show approved projects to investors
    project_query = Q(visibility__in=['public', 'university']) & Q(approval_status='approved')

    # University filtering
    if feed_type == 'university' and university_id:
        project_query &= Q(university_id=university_id)

    # Search filtering (text fields only)
    if search_query:
        project_query &= (
            Q(title__icontains=search_query) |
            Q(summary__icontains=search_query)
        )

    # Quick filter for status (non-JSON field)
    if quick_filter == 'prototype':
        project_query &= Q(status__in=['mvp', 'launched'])

    # Cursor pagination
    if cursor:
        project_query &= Q(created_at__lt=cursor)

    # Get all matching approved projects (we'll filter by topics in Python)
    all_projects = Project.objects.filter(project_query).select_related(
        'owner', 'owner__profile', 'university'
    ).prefetch_related('team_members', 'team_members__profile').order_by('-created_at')
    
    # Filter by topics and calculate match scores in Python (SQLite-compatible)
    # RELAXED FILTERING: Show projects even with partial matches
    filtered_projects = []
    for project in all_projects:
        # Check quick filters that use JSONFields
        if quick_filter == 'funding':
            if not (isinstance(project.needs, list) and 'funding' in project.needs):
                continue
        elif quick_filter == 'hiring':
            if not (isinstance(project.needs, list) and 
                   any(need in project.needs for need in ['dev', 'design', 'marketing'])):
                continue
        
        # Check topic filtering - strict filtering for both manual and saved interests
        categories = project.categories if isinstance(project.categories, list) else []

        if topics and topics_str:  # Manual topic selection - strict filtering
            matches = [topic for topic in topics if topic in categories]
            if not matches:
                continue
            match_score = len(matches)
        elif user_interests:  # Using saved interests - strict filtering (only show matching projects)
            matches = [topic for topic in topics if topic in categories]
            if not matches:
                continue  # Skip projects that don't match any saved interests
            match_score = len(matches) * 2  # Boost matches
        else:  # No filtering - show all
            match_score = 0
        
        # Check search in tags (JSONField)
        if search_query:
            tags = project.tags if isinstance(project.tags, list) else []
            if not any(search_query.lower() in str(tag).lower() for tag in tags):
                # Already filtered by title/summary, so if tags don't match, skip
                pass
        
        # Add project with match score
        project.match_score = match_score
        filtered_projects.append(project)
    
    # Sort by match score and recency
    if sort_by == 'best_match' and topics:
        filtered_projects.sort(key=lambda x: (x.match_score, x.created_at), reverse=True)
    elif sort_by == 'recent':
        filtered_projects.sort(key=lambda x: x.created_at, reverse=True)
    elif sort_by == 'saved':
        # TODO: Implement saved/starred functionality
        filtered_projects.sort(key=lambda x: x.created_at, reverse=True)
    else:
        filtered_projects.sort(key=lambda x: (x.match_score if hasattr(x, 'match_score') else 0, x.created_at), reverse=True)
    
    # Limit projects (prioritize them in feed)
    project_limit = int(limit * 0.83)  # ~10 out of 12
    projects = filtered_projects[:project_limit]
    
    # Base post query (posts with visibility public or university)
    post_query = Q(visibility__in=['public', 'university'])
    
    # University filtering for posts
    if feed_type == 'university' and university_id:
        post_query &= Q(author__profile__university_id=university_id)
    
    # Search filtering for posts
    if search_query:
        post_query &= Q(content__icontains=search_query)
    
    # Cursor pagination for posts
    if cursor:
        post_query &= Q(created_at__lt=cursor)
    
    # Get posts (filter by topics in Python for SQLite compatibility)
    all_posts = Post.objects.filter(post_query).select_related(
        'author', 'author__profile', 'university'
    ).prefetch_related('tagged_projects', 'likes').order_by('-created_at')
    
    # Filter posts by topic if needed
    filtered_posts = []
    post_limit = limit - len(projects)  # Fill remaining slots with posts
    
    if topics:
        for post in all_posts:
            if len(filtered_posts) >= post_limit:
                break
            # Check if any tagged project has matching categories
            for tagged_project in post.tagged_projects.all():
                categories = tagged_project.categories if isinstance(tagged_project.categories, list) else []
                if any(topic in categories for topic in topics):
                    filtered_posts.append(post)
                    break
    else:
        filtered_posts = list(all_posts[:post_limit])
    
    posts = filtered_posts
    
    # Serialize data
    project_data = ProjectSerializer(projects, many=True, context={'request': request}).data
    post_data = PostSerializer(posts, many=True, context={'request': request}).data
    
    # Combine and sort by priority (projects first, then posts)
    combined_feed = []
    
    # Add projects with priority marker
    for project in project_data:
        project['item_type'] = 'project'
        project['priority'] = 1
        combined_feed.append(project)
    
    # Add posts with lower priority
    for post in post_data:
        post['item_type'] = 'post'
        post['priority'] = 2
        # Add computed fields
        post['likes_count'] = post.get('likes_count', 0)
        post['comments_count'] = post.get('comments_count', 0)
        combined_feed.append(post)
    
    # Sort by priority, then by date
    combined_feed.sort(key=lambda x: (x['priority'], x.get('created_at', '')), reverse=True)
    
    # Determine next cursor
    next_cursor = None
    if combined_feed:
        last_item = combined_feed[-1]
        next_cursor = last_item.get('created_at')
    
    return Response({
        'results': combined_feed,
        'next_cursor': next_cursor,
        'count': len(combined_feed),
        'has_more': len(combined_feed) == limit,
        'using_interests': bool(user_interests),  # Indicate if interests were used
        'active_topics': topics  # Show which topics are being used for filtering
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def investor_topics(request):
    """
    Get available topics for filtering
    GET /api/feed/investor/topics/
    """
    if not is_investor(request.user):
        return Response(
            {'error': 'Access denied. This feature is only available to investors.'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Define available topics
    topics = [
        {'id': 'AI', 'label': 'AI', 'icon': '🤖'},
        {'id': 'Web Dev', 'label': 'Web Dev', 'icon': '💻'},
        {'id': 'Fintech', 'label': 'Fintech', 'icon': '💰'},
        {'id': 'Robotics', 'label': 'Robotics', 'icon': '🤖'},
        {'id': 'Biotech', 'label': 'Biotech', 'icon': '🧬'},
        {'id': 'Climate', 'label': 'Climate', 'icon': '🌍'},
        {'id': 'Hardware', 'label': 'Hardware', 'icon': '⚙️'},
        {'id': 'SaaS', 'label': 'SaaS', 'icon': '☁️'},
        {'id': 'EdTech', 'label': 'EdTech', 'icon': '📚'},
        {'id': 'HealthTech', 'label': 'HealthTech', 'icon': '🏥'},
        {'id': 'Social Impact', 'label': 'Social Impact', 'icon': '💝'},
        {'id': 'Gaming', 'label': 'Gaming', 'icon': '🎮'},
    ]
    
    return Response({'topics': topics})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def investor_stats(request):
    """
    Get investor-specific statistics
    GET /api/feed/investor/stats/
    """
    if not is_investor(request.user):
        return Response(
            {'error': 'Access denied. This feature is only available to investors.'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get counts
    all_projects = Project.objects.filter(visibility__in=['public', 'university'])
    total_projects = all_projects.count()
    
    # For SQLite compatibility, filter funding projects in Python
    # (SQLite doesn't support JSON contains lookup)
    raising_funding = sum(
        1 for project in all_projects 
        if isinstance(project.needs, list) and 'funding' in project.needs
    )
    
    prototypes_ready = Project.objects.filter(
        visibility__in=['public', 'university'],
        status__in=['mvp', 'launched']
    ).count()
    
    return Response({
        'total_projects': total_projects,
        'raising_funding': raising_funding,
        'prototypes_ready': prototypes_ready,
    })

