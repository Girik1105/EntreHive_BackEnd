from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
import re
from .models import Post, Comment, Like, PostShare
from .serializers import (
    PostSerializer, PostListSerializer, CommentSerializer,
    CommentCreateSerializer, LikeSerializer
)
from notifications.models import Notification


class PostViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing posts with CRUD operations
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['visibility', 'author__profile__user_role']
    search_fields = ['content', 'author__username', 'author__profile__first_name', 'author__profile__last_name']
    ordering_fields = ['created_at', 'updated_at', 'likes_count']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Get posts that the user can view based on visibility settings
        """
        user = self.request.user
        queryset = Post.objects.select_related('author', 'author__profile').prefetch_related(
            'tagged_projects', 'likes', 
            'comments__author', 'comments__author__profile',
            'comments__replies__author', 'comments__replies__author__profile'
        ).annotate(
            likes_count=Count('likes', distinct=True),
            comments_count=Count('comments', distinct=True)
        )
        
        if user.is_authenticated:
            # Show public posts, user's own posts, and university posts if same university
            user_university = getattr(user.profile, 'university', None) if hasattr(user, 'profile') else None
            
            queryset = queryset.filter(
                Q(visibility='public') |
                Q(author=user) |
                (Q(visibility='university') & Q(author__profile__university=user_university) if user_university else Q(pk=None))
            )
        else:
            # Only show public posts for unauthenticated users
            queryset = queryset.filter(visibility='public')
        
        return queryset.distinct()
    
    def get_serializer_class(self):
        """
        Use different serializers for list vs detail views
        """
        if self.action == 'list':
            return PostListSerializer
        return PostSerializer
    
    def perform_create(self, serializer):
        """
        Set the author to the current user when creating a post
        """
        post = serializer.save(author=self.request.user)

        # Check for mentions in post content
        mentions = re.findall(r'@(\w+)', post.content)
        for username in mentions:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                mentioned_user = User.objects.get(username=username)
                if mentioned_user != self.request.user:
                    Notification.create_mention_notification(
                        mentioner=self.request.user,
                        mentioned_user=mentioned_user,
                        post=post
                    )
            except User.DoesNotExist:
                pass
            except Exception as e:
                print(f"Error creating mention notification in post: {e}")
    
    def perform_update(self, serializer):
        """
        Only allow authors to update their own posts
        """
        post = self.get_object()
        if post.author != self.request.user:
            return Response(
                {'error': 'You can only edit your own posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer.save()
    
    def perform_destroy(self, instance):
        """
        Only allow authors to delete their own posts
        """
        if instance.author != self.request.user:
            return Response(
                {'error': 'You can only delete your own posts'},
                status=status.HTTP_403_FORBIDDEN
            )
        instance.delete()
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def like(self, request, pk=None):
        """
        Like or unlike a post
        """
        post = self.get_object()
        user = request.user
        
        # Check if user can view this post
        if not post.can_view(user):
            return Response(
                {'error': 'You do not have permission to view this post'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        like, created = Like.objects.get_or_create(post=post, user=user)

        if created:
            # Create notification for post author (don't notify if user likes their own post)
            if post.author != user:
                try:
                    Notification.create_like_notification(
                        liker=user,
                        post=post
                    )
                except Exception as e:
                    print(f"Error creating like notification: {e}")

            return Response(
                {'message': 'Post liked', 'liked': True, 'likes_count': post.get_likes_count()},
                status=status.HTTP_201_CREATED
            )
        else:
            like.delete()
            return Response(
                {'message': 'Post unliked', 'liked': False, 'likes_count': post.get_likes_count()},
                status=status.HTTP_200_OK
            )
    
    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
    def likes(self, request, pk=None):
        """
        Get list of users who liked this post
        """
        post = self.get_object()
        user = request.user
        
        # Check if user can view this post
        if user.is_authenticated and not post.can_view(user):
            return Response(
                {'error': 'You do not have permission to view this post'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        likes = post.likes.select_related('user', 'user__profile').all()
        serializer = LikeSerializer(likes, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def share(self, request, pk=None):
        """
        Share a post (track share action)
        """
        post = self.get_object()
        user = request.user
        
        # Check if user can view this post
        if not post.can_view(user):
            return Response(
                {'error': 'You do not have permission to view this post'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create share record
        PostShare.objects.create(post=post, user=user)
        
        # Generate share URL
        share_url = request.build_absolute_uri(f'/posts/{post.id}/')
        
        return Response(
            {'message': 'Post shared', 'share_url': share_url},
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def feed(self, request):
        """
        Get personalized feed for authenticated user
        """
        user = request.user
        user_university = getattr(user.profile, 'university', None) if hasattr(user, 'profile') else None
        
        # Get posts from followed users, same university, and public posts
        queryset = self.get_queryset().filter(
            Q(visibility='public') |
            Q(author=user) |
            (Q(visibility='university') & Q(author__profile__university=user_university) if user_university else Q(pk=None))
        ).distinct()
        
        # Apply filtering and pagination
        queryset = self.filter_queryset(queryset)
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def my_posts(self, request):
        """
        Get current user's posts
        """
        queryset = Post.objects.filter(author=request.user).select_related(
            'author', 'author__profile'
        ).prefetch_related('tagged_projects', 'likes', 'comments').annotate(
            likes_count=Count('likes', distinct=True),
            comments_count=Count('comments', distinct=True)
        ).order_by('-created_at')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class CommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing comments on posts
    """
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        """
        Get comments for a specific post - only top-level comments with their replies
        """
        post_id = self.kwargs.get('post_pk')
        if post_id:
            return Comment.objects.filter(
                post_id=post_id,
                parent__isnull=True  # Only get top-level comments
            ).select_related('author', 'author__profile').prefetch_related(
                'replies__author', 'replies__author__profile'
            ).order_by('created_at')
        return Comment.objects.none()
    
    def get_serializer_class(self):
        """
        Use different serializers for create vs other actions
        """
        if self.action == 'create':
            return CommentCreateSerializer
        return CommentSerializer
    
    def create(self, request, *args, **kwargs):
        """
        Override create to return the full comment with author data
        """
        post_id = self.kwargs.get('post_pk')
        post = get_object_or_404(Post, id=post_id)

        # Check if user can view the post
        if not post.can_view(request.user):
            return Response(
                {'error': 'You do not have permission to comment on this post'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(
            author=request.user,
            post=post
        )

        # Create notification for post author or parent comment author
        if comment.parent:
            # Reply to a comment - notify the comment author
            if comment.parent.author != request.user:
                try:
                    Notification.create_comment_notification(
                        commenter=request.user,
                        post=post,
                        comment=comment,
                        is_reply=True
                    )
                except Exception as e:
                    print(f"Error creating comment reply notification: {e}")
        else:
            # Comment on a post - notify the post author
            if post.author != request.user:
                try:
                    Notification.create_comment_notification(
                        commenter=request.user,
                        post=post,
                        comment=comment,
                        is_reply=False
                    )
                except Exception as e:
                    print(f"Error creating comment notification: {e}")

        # Check for mentions in comment content
        mentions = re.findall(r'@(\w+)', comment.content)
        for username in mentions:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                mentioned_user = User.objects.get(username=username)
                if mentioned_user != request.user:
                    Notification.create_mention_notification(
                        mentioner=request.user,
                        mentioned_user=mentioned_user,
                        post=post,
                        comment=comment
                    )
            except User.DoesNotExist:
                pass
            except Exception as e:
                print(f"Error creating mention notification: {e}")

        # Return the comment using the full CommentSerializer with author data
        output_serializer = CommentSerializer(comment, context={'request': request})
        headers = self.get_success_headers(output_serializer.data)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def get_serializer_context(self):
        """
        Add post_id to serializer context for validation
        """
        context = super().get_serializer_context()
        post_id = self.kwargs.get('post_pk')
        if post_id:
            context['post_id'] = post_id
        return context
    
    def update(self, request, *args, **kwargs):
        """
        Override update to return the full comment with author data
        """
        comment = self.get_object()
        if comment.author != request.user:
            return Response(
                {'error': 'You can only edit your own comments'},
                status=status.HTTP_403_FORBIDDEN
            )

        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(comment, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # Mark as edited if content changed
        if 'content' in serializer.validated_data and serializer.validated_data['content'] != comment.content:
            updated_comment = serializer.save(is_edited=True)
        else:
            updated_comment = serializer.save()

        # Return the comment using the full CommentSerializer with author data
        output_serializer = CommentSerializer(updated_comment, context={'request': request})
        return Response(output_serializer.data)
    
    def perform_destroy(self, instance):
        """
        Allow authors and post authors to delete comments
        """
        if not instance.can_delete(self.request.user):
            return Response(
                {'error': 'You do not have permission to delete this comment'},
                status=status.HTTP_403_FORBIDDEN
            )
        instance.delete()


class LikeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing likes (read-only)
    """
    serializer_class = LikeSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        """
        Get likes for a specific post
        """
        post_id = self.kwargs.get('post_pk')
        if post_id:
            return Like.objects.filter(
                post_id=post_id
            ).select_related('user', 'user__profile')
        return Like.objects.none()


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticatedOrReadOnly])
def post_search(request):
    """
    Search for posts by content, author, or hashtags
    """
    search_query = request.GET.get('q', '').strip()
    
    if not search_query:
        return Response(
            {'results': [], 'message': 'Please provide a search query'}, 
            status=status.HTTP_200_OK
        )
    
    user = request.user
    
    # Base queryset with proper permissions
    queryset = Post.objects.select_related('author', 'author__profile').prefetch_related(
        'tagged_projects', 'likes', 'comments'
    ).annotate(
        likes_count=Count('likes', distinct=True),
        comments_count=Count('comments', distinct=True)
    )
    
    # Apply visibility filtering
    if user.is_authenticated:
        user_university = getattr(user.profile, 'university', None) if hasattr(user, 'profile') else None
        
        queryset = queryset.filter(
            Q(visibility='public') |
            Q(author=user) |
            (Q(visibility='university') & Q(author__profile__university=user_university) if user_university else Q(pk=None))
        )
    else:
        queryset = queryset.filter(visibility='public')
    
    # Search functionality
    search_filters = Q()
    
    # Check if it's a hashtag search
    if search_query.startswith('#'):
        hashtag = search_query[1:]
        search_filters |= Q(content__icontains=f'#{hashtag}')
    else:
        # General search across content, author info, and tagged projects
        search_filters |= (
            Q(content__icontains=search_query) |
            Q(author__username__icontains=search_query) |
            Q(author__profile__first_name__icontains=search_query) |
            Q(author__profile__last_name__icontains=search_query) |
            Q(tagged_projects__title__icontains=search_query) |
            Q(tagged_projects__categories__icontains=search_query) |
            Q(tagged_projects__tags__icontains=search_query)
        )
    
    queryset = queryset.filter(search_filters).distinct().order_by('-created_at')[:50]  # Limit to 50 results
    
    serializer = PostListSerializer(queryset, many=True, context={'request': request})
    return Response(
        {'results': serializer.data, 'count': len(serializer.data)}, 
        status=status.HTTP_200_OK
    )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticatedOrReadOnly])
def hashtag_search(request):
    """
    Extract and search for hashtags from posts
    """
    search_query = request.GET.get('q', '').strip()
    
    if not search_query:
        return Response(
            {'results': [], 'message': 'Please provide a search query'}, 
            status=status.HTTP_200_OK
        )
    
    user = request.user
    
    # Base queryset with proper permissions
    queryset = Post.objects.select_related('author', 'author__profile')
    
    # Apply visibility filtering
    if user.is_authenticated:
        user_university = getattr(user.profile, 'university', None) if hasattr(user, 'profile') else None
        
        queryset = queryset.filter(
            Q(visibility='public') |
            Q(author=user) |
            (Q(visibility='university') & Q(author__profile__university=user_university) if user_university else Q(pk=None))
        )
    else:
        queryset = queryset.filter(visibility='public')
    
    # Extract hashtags from all posts
    all_hashtags = set()
    for post in queryset:
        # Extract hashtags from post content
        hashtags_in_content = re.findall(r'#(\w+)', post.content)
        all_hashtags.update(hashtags_in_content)
    
    # Filter hashtags based on search query
    matching_hashtags = [tag for tag in all_hashtags if search_query.lower() in tag.lower()]
    matching_hashtags = sorted(matching_hashtags, key=lambda x: x.lower())[:20]  # Limit to 20 results
    
    return Response(
        {'results': matching_hashtags, 'count': len(matching_hashtags)}, 
        status=status.HTTP_200_OK
    )