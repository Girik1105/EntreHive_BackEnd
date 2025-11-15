from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Count, F, Case, When, IntegerField, FloatField
from django.db import connection
from django.utils import timezone
from datetime import timedelta
import random
import uuid

from .models import (
    ContentScore, UserInteraction, FeedConfiguration, 
    TrendingTopic, TimelineFeedCache
)
from .serializers import (
    TimelineItemSerializer, FeedConfigurationSerializer,
    TrendingTopicSerializer, UserInteractionSerializer
)
from posts.models import Post
from projects.models import Project


class FeedPagination(PageNumberPagination):
    """Custom pagination for feed"""
    page_size = 15
    page_size_query_param = 'page_size'
    max_page_size = 50


class TimelineFeedViewSet(viewsets.ViewSet):
    """
    Timeline-based feed system - generates feeds on-demand
    No pre-computed FeedItem records needed!
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = FeedPagination
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.paginator = self.pagination_class()
    
    @action(detail=False, methods=['get'])
    def home(self, request):
        """Get personalized home timeline"""
        user = request.user
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        timeline_items, total_count = self._get_timeline_feed(user, 'home', page, page_size)
        return self._paginate_response(timeline_items, request, page, page_size, total_count)
    
    @action(detail=False, methods=['get'])
    def university(self, request):
        """Get university-specific timeline"""
        user = request.user
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        timeline_items, total_count = self._get_timeline_feed(user, 'university', page, page_size)
        return self._paginate_response(timeline_items, request, page, page_size, total_count)
    
    @action(detail=False, methods=['get'])
    def public(self, request):
        """Get public timeline with content from all universities"""
        user = request.user
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        timeline_items, total_count = self._get_timeline_feed(user, 'public', page, page_size)
        return self._paginate_response(timeline_items, request, page, page_size, total_count)
    
    @action(detail=False, methods=['post'])
    def track_interaction(self, request):
        """Track user interaction with content"""
        try:
            content_type = request.data.get('content_type')
            content_id = request.data.get('content_id')
            action = request.data.get('action')
            view_time = request.data.get('view_time')
            feed_type = request.data.get('feed_type')
            
            if not content_type or not content_id or not action:
                return Response(
                    {'error': 'content_type, content_id, and action are required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create interaction record
            interaction = UserInteraction.objects.create(
                user=request.user,
                content_type=content_type,
                content_id=content_id,
                action=action,
                view_time=view_time,
                feed_type=feed_type
            )
            
            # Update content scores based on interaction
            self._update_content_engagement(content_type, content_id, action)
            
            return Response({'message': 'Interaction tracked successfully'})
            
        except Exception as e:
            return Response(
                {'error': f'Failed to track interaction: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_timeline_feed(self, user, feed_type, page=1, page_size=20):
        """Generate timeline feed on-demand"""
        config, _ = FeedConfiguration.objects.get_or_create(user=user)
        user_university = getattr(user.profile, 'university', None) if hasattr(user, 'profile') else None
        
        # Check cache first
        try:
            cache = TimelineFeedCache.objects.get(user=user, feed_type=feed_type)
            if not cache.is_expired():
                cached_page = cache.get_page(page, page_size)
                if cached_page:
                    hydrated_items = self._hydrate_timeline_items(cached_page, user)
                    # Return both items and total count for pagination
                    return hydrated_items, cache.total_count
        except TimelineFeedCache.DoesNotExist:
            pass
        
        # Generate fresh timeline
        if feed_type == 'home':
            timeline_items = self._generate_home_timeline(user, config, user_university)
        elif feed_type == 'university':
            timeline_items = self._generate_university_timeline(user, config, user_university)
        elif feed_type == 'public':
            timeline_items = self._generate_public_timeline(user, config)
        else:
            timeline_items = []
        
        # Cache the results
        self._cache_timeline(user, feed_type, timeline_items)
        
        # Return requested page
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = timeline_items[start_idx:end_idx]
        
        hydrated_items = self._hydrate_timeline_items(page_items, user)
        return hydrated_items, len(timeline_items)
    
    def _hydrate_timeline_items(self, timeline_items, user):
        """Convert timeline item data to full objects"""
        result = []
        
        # Group by content type for efficient querying
        posts_ids = [item['content_id'] for item in timeline_items if item['content_type'] == 'post']
        projects_ids = [item['content_id'] for item in timeline_items if item['content_type'] == 'project']
        
        # Fetch all content in bulk
        posts = {p.id: p for p in Post.objects.filter(id__in=posts_ids).select_related('author', 'university')}
        projects = {p.id: p for p in Project.objects.filter(id__in=projects_ids).select_related('owner', 'university')}
        
        # Get user interactions for this content
        content_refs = [(item['content_type'], item['content_id']) for item in timeline_items]
        interactions = UserInteraction.objects.filter(
            user=user,
            content_type__in=[ref[0] for ref in content_refs],
            content_id__in=[ref[1] for ref in content_refs]
        ).values('content_type', 'content_id', 'action').distinct()
        
        interaction_map = {}
        for interaction in interactions:
            key = f"{interaction['content_type']}_{interaction['content_id']}"
            if key not in interaction_map:
                interaction_map[key] = []
            interaction_map[key].append(interaction['action'])
        
        # Build timeline items
        for item_data in timeline_items:
            content_type = item_data['content_type']
            content_id = item_data['content_id']
            
            # Convert content_id to UUID if it's a string (from cache)
            import uuid
            if isinstance(content_id, str):
                try:
                    content_id_uuid = uuid.UUID(content_id)
                except ValueError:
                    content_id_uuid = content_id
            else:
                content_id_uuid = content_id
            
            content_obj = None
            if content_type == 'post' and content_id_uuid in posts:
                content_obj = posts[content_id_uuid]
            elif content_type == 'project' and content_id_uuid in projects:
                content_obj = projects[content_id_uuid]
            
            if content_obj:
                interaction_key = f"{content_type}_{content_id}"
                user_interactions = interaction_map.get(interaction_key, [])
                
                result.append({
                    'content_type': content_type,
                    'content_id': content_id,
                    'score': item_data['score'],
                    'content': content_obj,
                    'user_interactions': user_interactions,
                    'viewed': 'view' in user_interactions,
                    'clicked': 'click' in user_interactions,
                    'liked': 'like' in user_interactions,
                })
        
        return result
    
    def _generate_home_timeline(self, user, config, user_university):
        """Generate personalized home timeline efficiently"""
        recent_cutoff = timezone.now() - timedelta(days=30)  # Only recent content
        content_items = []
        
        # Get followed users' posts with high priority
        from accounts.models import Follow
        followed_user_ids = list(user.following.values_list('following_id', flat=True))
        
        if followed_user_ids:
            followed_posts = Post.objects.filter(
                author_id__in=followed_user_ids,
                created_at__gte=recent_cutoff
            ).exclude(author=user).select_related('author', 'university').annotate(
                likes_count=Count('likes', distinct=True),
                comments_count=Count('comments', distinct=True)
            )[:40]  # Get posts from followed users
            
            for post in followed_posts:
                # Boost score for followed users
                score = self._calculate_content_score(post, user, config, post.university == user_university)
                score += 20  # Significant boost for followed users
                content_items.append({
                    'content_type': 'post',
                    'content_id': post.id,
                    'score': score
                })
        
        # Get university posts if enabled
        if config.show_university_posts and user_university:
            university_posts = Post.objects.filter(
                Q(visibility='university', university=user_university) |
                Q(visibility='public', university=user_university),
                created_at__gte=recent_cutoff
            ).exclude(author=user).exclude(author_id__in=followed_user_ids).select_related('author', 'university').annotate(
                likes_count=Count('likes', distinct=True),
                comments_count=Count('comments', distinct=True)
            )[:60]  # Limit source content
            
            for post in university_posts:
                score = self._calculate_content_score(post, user, config, True)
                content_items.append({
                    'content_type': 'post',
                    'content_id': post.id,
                    'score': score
                })
        
        # Get public posts from other universities
        if config.show_public_posts:
            public_posts = Post.objects.filter(
                visibility='public',
                created_at__gte=recent_cutoff
            ).exclude(university=user_university).exclude(author=user).exclude(author_id__in=followed_user_ids).select_related(
                'author', 'university'
            ).annotate(
                likes_count=Count('likes', distinct=True),
                comments_count=Count('comments', distinct=True)
            )[:50]  # Limit source content
            
            for post in public_posts:
                score = self._calculate_content_score(post, user, config, False)
                content_items.append({
                    'content_type': 'post',
                    'content_id': post.id,
                    'score': score
                })
        
        # Get relevant approved projects only
        if config.show_project_updates:
            if user_university:
                projects = Project.objects.filter(
                    Q(visibility='university', university=user_university) |
                    Q(visibility='public'),
                    created_at__gte=recent_cutoff,
                    approval_status='approved'
                ).exclude(owner=user).select_related('owner', 'university')[:30]
            else:
                projects = Project.objects.filter(
                    visibility='public',
                    created_at__gte=recent_cutoff,
                    approval_status='approved'
                ).exclude(owner=user).select_related('owner', 'university')[:30]

            for project in projects:
                score = self._calculate_content_score(project, user, config,
                                                   project.university == user_university)
                content_items.append({
                    'content_type': 'project',
                    'content_id': project.id,
                    'score': score
                })
        
        # Sort by score and ensure balanced content mix
        content_items.sort(key=lambda x: x['score'], reverse=True)
        balanced_items = self._balance_content_mix(content_items)
        return balanced_items[:200]  # Limit total timeline items
    
    def _generate_university_timeline(self, user, config, user_university):
        """Generate university-specific timeline"""
        if not user_university:
            return []
        
        recent_cutoff = timezone.now() - timedelta(days=30)
        content_items = []
        
        # Get university posts only
        university_posts = Post.objects.filter(
            Q(visibility='university', university=user_university) |
            Q(visibility='public', university=user_university),
            created_at__gte=recent_cutoff
        ).exclude(author=user).select_related('author', 'university').annotate(
            likes_count=Count('likes', distinct=True),
            comments_count=Count('comments', distinct=True)
        )[:40]
        
        for post in university_posts:
            score = self._calculate_content_score(post, user, config, True)
            content_items.append({
                'content_type': 'post',
                'content_id': post.id,
                'score': score
            })
        
        # Get approved university projects only
        university_projects = Project.objects.filter(
            Q(visibility='university', university=user_university) |
            Q(visibility='public', university=user_university),
            created_at__gte=recent_cutoff,
            approval_status='approved'
        ).exclude(owner=user).select_related('owner', 'university')[:20]

        for project in university_projects:
            score = self._calculate_content_score(project, user, config, True)
            content_items.append({
                'content_type': 'project',
                'content_id': project.id,
                'score': score
            })
        
        content_items.sort(key=lambda x: x['score'], reverse=True)
        balanced_items = self._balance_content_mix(content_items)
        return balanced_items[:150]  # Limit total timeline items
    
    def _generate_public_timeline(self, user, config):
        """Generate public timeline with content from all universities"""
        recent_cutoff = timezone.now() - timedelta(days=30)
        content_items = []
        
        # Get public posts
        public_posts = Post.objects.filter(
            visibility='public',
            created_at__gte=recent_cutoff
        ).exclude(author=user).select_related('author', 'university').annotate(
            likes_count=Count('likes', distinct=True),
            comments_count=Count('comments', distinct=True)
        )[:50]
        
        for post in public_posts:
            score = self._calculate_content_score(post, user, config, False)
            content_items.append({
                'content_type': 'post',
                'content_id': post.id,
                'score': score
            })
        
        # Get approved public projects only
        public_projects = Project.objects.filter(
            visibility='public',
            created_at__gte=recent_cutoff,
            approval_status='approved'
        ).exclude(owner=user).select_related('owner', 'university')[:30]

        for project in public_projects:
            score = self._calculate_content_score(project, user, config, False)
            content_items.append({
                'content_type': 'project',
                'content_id': project.id,
                'score': score
            })
        
        content_items.sort(key=lambda x: x['score'], reverse=True)
        balanced_items = self._balance_content_mix(content_items)
        return balanced_items[:200]  # Limit total timeline items
    
    def _calculate_content_score(self, content_obj, user, config, is_same_university):
        """Calculate relevance score for any content (post or project)"""
        score = 0.0
        
        # Recency score (0-25 points)
        hours_old = (timezone.now() - content_obj.created_at).total_seconds() / 3600
        recency_score = max(0, 25 - (hours_old / 24) * 25)
        score += recency_score * config.recency_weight * 4
        
        # Engagement score (0-25 points)
        if hasattr(content_obj, 'likes_count'):  # Post
            likes_count = getattr(content_obj, 'likes_count', 0)
            comments_count = getattr(content_obj, 'comments_count', 0)
            engagement_score = min(25, (likes_count * 2 + comments_count * 3))
        else:  # Project
            attractiveness_score = 15
            if hasattr(content_obj, 'needs') and content_obj.needs:
                attractiveness_score += len(content_obj.needs) * 2
            engagement_score = min(25, attractiveness_score)
        
        score += engagement_score * config.engagement_weight * 4
        
        # University bonus (0-25 points)
        university_score = 25 if is_same_university else 5
        score += university_score * config.university_weight * 4
        
        # Relevance score (0-25 points)
        relevance_score = 15  # Base relevance
        score += relevance_score * config.relevance_weight * 4
        
        # Add slight randomization to prevent staleness
        score += random.uniform(-1, 1)
        
        return max(0, min(100, score))
    
    def _balance_content_mix(self, content_items, target_post_ratio=0.6):
        """Ensure a balanced mix of posts and projects in the feed"""
        if not content_items:
            return content_items
        
        posts = [item for item in content_items if item['content_type'] == 'post']
        projects = [item for item in content_items if item['content_type'] == 'project']
        
        # If one type is severely limited, adjust the ratio
        total_posts = len(posts)
        total_projects = len(projects)
        total_content = total_posts + total_projects
        
        if total_content == 0:
            return []
        
        # Adjust ratio based on available content
        if total_posts < total_content * 0.3:  # If less than 30% posts available
            target_post_ratio = max(0.4, total_posts / total_content)  # Use at least 40% of available posts
        elif total_projects < total_content * 0.3:  # If less than 30% projects available
            target_post_ratio = min(0.8, 1 - (total_projects / total_content))  # Leave room for projects
        
        # Sort both by score
        posts.sort(key=lambda x: x['score'], reverse=True)
        projects.sort(key=lambda x: x['score'], reverse=True)
        
        balanced_items = []
        post_idx = project_idx = 0
        total_slots = min(len(content_items), 200)
        target_posts = int(total_slots * target_post_ratio)
        target_projects = total_slots - target_posts
        
        # Simple alternating pattern with ratio enforcement
        posts_per_cycle = max(1, int(target_post_ratio * 3))  # Posts per 3-item cycle
        projects_per_cycle = 3 - posts_per_cycle  # Projects per 3-item cycle
        
        cycle_position = 0
        while len(balanced_items) < total_slots and (post_idx < len(posts) or project_idx < len(projects)):
            posts_added = len([item for item in balanced_items if item['content_type'] == 'post'])
            projects_added = len([item for item in balanced_items if item['content_type'] == 'project'])
            
            # Determine if we should add a post based on cycle position and availability
            in_post_part_of_cycle = cycle_position < posts_per_cycle
            
            should_add_post = (
                post_idx < len(posts) and 
                posts_added < target_posts and
                (in_post_part_of_cycle or projects_added >= target_projects or project_idx >= len(projects))
            )
            
            if should_add_post:
                balanced_items.append(posts[post_idx])
                post_idx += 1
            elif project_idx < len(projects) and projects_added < target_projects:
                balanced_items.append(projects[project_idx])
                project_idx += 1
            elif post_idx < len(posts):
                # Fill remaining with posts if projects are exhausted
                balanced_items.append(posts[post_idx])
                post_idx += 1
            elif project_idx < len(projects):
                # Fill remaining with projects if posts are exhausted
                balanced_items.append(projects[project_idx])
                project_idx += 1
            
            cycle_position = (cycle_position + 1) % 3
        
        return balanced_items
    
    def _cache_timeline(self, user, feed_type, timeline_items):
        """Cache timeline items for performance"""
        try:
            cache = TimelineFeedCache.objects.get(user=user, feed_type=feed_type)
            cache.refresh_cache(timeline_items, expiry_hours=1)
        except TimelineFeedCache.DoesNotExist:
            # Create new cache
            cache = TimelineFeedCache.objects.create(
                user=user,
                feed_type=feed_type,
                expires_at=timezone.now() + timedelta(hours=1)
            )
            cache.refresh_cache(timeline_items, expiry_hours=1)
    
    def _update_content_engagement(self, content_type, content_id, action):
        """Update content scores based on user interactions"""
        try:
            score, created = ContentScore.objects.get_or_create(
                content_type=content_type,
                content_id=content_id,
                defaults={
                    'base_score': 50.0,
                    'engagement_score': 0.0,
                    'recency_score': 0.0,
                    'trending_score': 0.0,
                    'expires_at': timezone.now() + timedelta(hours=24)
                }
            )
            
            # Boost engagement score based on action
            if action == 'like':
                score.engagement_score += 2.0
            elif action == 'share':
                score.engagement_score += 3.0
            elif action == 'comment':
                score.engagement_score += 1.5
            elif action == 'click':
                score.engagement_score += 0.5
            
            score.base_score = min(100.0, score.base_score + (score.engagement_score * 0.1))
            score.save()
            
        except Exception:
            # Fail silently to not break feed functionality
            pass
    
    def _paginate_response(self, timeline_items, request, page, page_size, total_count):
        """Create paginated response for timeline items"""
        
        # Calculate pagination info
        has_next = page * page_size < total_count
        has_previous = page > 1
        
        # Build response
        response_data = {
            'results': TimelineItemSerializer(timeline_items, many=True, context={'request': request}).data,
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'has_next': has_next,
            'has_previous': has_previous,
        }
        
        if has_next:
            response_data['next'] = f"{request.build_absolute_uri()}?page={page + 1}&page_size={page_size}"
        else:
            response_data['next'] = None
            
        if has_previous:
            response_data['previous'] = f"{request.build_absolute_uri()}?page={page - 1}&page_size={page_size}"
        else:
            response_data['previous'] = None
        
        return Response(response_data)


class FeedConfigurationViewSet(viewsets.ModelViewSet):
    """ViewSet for user feed configuration"""
    serializer_class = FeedConfigurationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return FeedConfiguration.objects.filter(user=self.request.user)
    
    def get_object(self):
        config, created = FeedConfiguration.objects.get_or_create(user=self.request.user)
        return config
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save()
        # Clear timeline caches when user updates preferences
        TimelineFeedCache.objects.filter(user=self.request.user).delete()


class TrendingTopicViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for trending topics"""
    serializer_class = TrendingTopicSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    queryset = TrendingTopic.objects.all()
    
    def get_queryset(self):
        queryset = TrendingTopic.objects.all()
        university_id = self.request.query_params.get('university')
        if university_id:
            queryset = queryset.filter(universities__id=university_id)
        return queryset.order_by('-mention_count')[:20]