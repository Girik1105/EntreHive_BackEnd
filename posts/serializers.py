from rest_framework import serializers
from django.contrib.auth.models import User
from django.db import models
from .models import Post, Comment, Like, PostShare
from projects.models import Project
from utils.image_compression import ImageCompressor
import logging

logger = logging.getLogger(__name__)


class AuthorSerializer(serializers.ModelSerializer):
    """
    Simplified user serializer for post authors
    """
    full_name = serializers.CharField(source='profile.get_full_name', read_only=True)
    profile_picture = serializers.SerializerMethodField()
    user_role = serializers.CharField(source='profile.user_role', read_only=True)
    university_name = serializers.SerializerMethodField()
    university_id = serializers.CharField(source='profile.university.id', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'profile_picture', 'user_role', 'university_name', 'university_id']
    
    def get_profile_picture(self, obj):
        if hasattr(obj, 'profile') and obj.profile.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile.profile_picture.url)
        return None
    
    def get_university_name(self, obj):
        if hasattr(obj, 'profile') and obj.profile.university:
            return obj.profile.university.name
        return None


class ProjectTagSerializer(serializers.ModelSerializer):
    """
    Simplified project serializer for tagged projects in posts
    """
    
    class Meta:
        model = Project
        fields = ['id', 'title', 'project_type', 'status']


class CommentSerializer(serializers.ModelSerializer):
    """
    Serializer for comments with nested replies
    """
    author = AuthorSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    replies_count = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    
    class Meta:
        model = Comment
        fields = [
            'id', 'author', 'content', 'parent', 'is_edited',
            'created_at', 'updated_at', 'replies', 'replies_count',
            'can_edit', 'can_delete'
        ]
        read_only_fields = ['id', 'author', 'is_edited', 'created_at', 'updated_at']
    
    def get_replies(self, obj):
        if obj.parent is None:  # Only get replies for top-level comments
            replies = obj.replies.all().order_by('created_at')  # Sort replies by creation time
            return CommentSerializer(replies, many=True, context=self.context).data
        return []  # Always return an empty array for reply comments
    
    def get_replies_count(self, obj):
        return obj.get_replies_count()
    
    def get_can_edit(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.can_edit(request.user)
        return False
    
    def get_can_delete(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.can_delete(request.user)
        return False


class PostSerializer(serializers.ModelSerializer):
    """
    Main post serializer with all related data.
    Includes automatic image compression for post images.
    """
    author = AuthorSerializer(read_only=True)
    tagged_projects = ProjectTagSerializer(many=True, read_only=True)
    tagged_project_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        allow_empty=True
    )
    image = serializers.ImageField(required=False, allow_null=True)

    # Interaction counts and status
    likes_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    # Comments (for detailed view) - only top-level comments with nested replies
    comments = serializers.SerializerMethodField()

    # Permissions
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    # Image URL
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'id', 'author', 'content', 'image', 'image_url', 'visibility',
            'tagged_projects', 'tagged_project_ids', 'is_edited',
            'likes_count', 'comments_count', 'is_liked', 'comments',
            'can_edit', 'can_delete', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'author', 'is_edited', 'created_at', 'updated_at']

    def validate_image(self, value):
        """Validate and prepare image for compression."""
        if value:
            try:
                is_valid, error = ImageCompressor.validate_image(value)
                if not is_valid:
                    raise serializers.ValidationError(error)
            except Exception as e:
                logger.warning(f"Post image validation failed: {e}")
                raise serializers.ValidationError(f"Invalid image: {str(e)}")
        return value

    def _compress_image(self, validated_data):
        """Compress post image if present."""
        if 'image' in validated_data and validated_data['image']:
            try:
                validated_data['image'] = ImageCompressor.compress_post_image(
                    validated_data['image']
                )
                logger.info("Post image compressed successfully")
            except Exception as e:
                logger.error(f"Post image compression failed: {e}")
                raise serializers.ValidationError(f"Failed to process image: {str(e)}")
        return validated_data
    
    def get_likes_count(self, obj):
        return obj.get_likes_count()
    
    def get_comments_count(self, obj):
        return obj.get_comments_count()
    
    def get_comments(self, obj):
        """Get only top-level comments with their nested replies"""
        top_level_comments = obj.comments.filter(parent__isnull=True).order_by('created_at')
        return CommentSerializer(top_level_comments, many=True, context=self.context).data
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.is_liked_by(request.user)
        return False
    
    def get_can_edit(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.can_edit(request.user)
        return False
    
    def get_can_delete(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.can_delete(request.user)
        return False
    
    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
        return None
    
    def create(self, validated_data):
        # Extract tagged project IDs
        tagged_project_ids = validated_data.pop('tagged_project_ids', [])

        # Compress image before saving
        validated_data = self._compress_image(validated_data)

        # Create the post
        post = Post.objects.create(**validated_data)

        # Add tagged projects
        if tagged_project_ids:
            # Filter projects that the user can tag (public projects or projects they're part of)
            user = self.context['request'].user
            accessible_projects = Project.objects.filter(
                id__in=tagged_project_ids
            ).filter(
                models.Q(visibility='public') |
                models.Q(owner=user) |
                models.Q(team_members=user)
            ).distinct()

            post.tagged_projects.set(accessible_projects)

        return post

    def update(self, instance, validated_data):
        # Extract tagged project IDs
        tagged_project_ids = validated_data.pop('tagged_project_ids', None)

        # Mark as edited if content changed
        if 'content' in validated_data and validated_data['content'] != instance.content:
            validated_data['is_edited'] = True

        # Compress image before saving
        validated_data = self._compress_image(validated_data)

        # Update the post
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update tagged projects if provided
        if tagged_project_ids is not None:
            user = self.context['request'].user
            accessible_projects = Project.objects.filter(
                id__in=tagged_project_ids
            ).filter(
                models.Q(visibility='public') |
                models.Q(owner=user) |
                models.Q(team_members=user)
            ).distinct()

            instance.tagged_projects.set(accessible_projects)

        return instance


class PostListSerializer(serializers.ModelSerializer):
    """
    Simplified post serializer for list views (without comments)
    """
    author = AuthorSerializer(read_only=True)
    tagged_projects = ProjectTagSerializer(many=True, read_only=True)
    
    # Interaction counts and status
    likes_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    
    # Permissions
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    
    # Image URL
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Post
        fields = [
            'id', 'author', 'content', 'image_url', 'visibility',
            'tagged_projects', 'is_edited', 'likes_count', 'comments_count',
            'is_liked', 'can_edit', 'can_delete', 'created_at', 'updated_at'
        ]
    
    def get_likes_count(self, obj):
        return obj.get_likes_count()
    
    def get_comments_count(self, obj):
        return obj.get_comments_count()
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.is_liked_by(request.user)
        return False
    
    def get_can_edit(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.can_edit(request.user)
        return False
    
    def get_can_delete(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.can_delete(request.user)
        return False
    
    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
        return None


class CommentCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating comments
    """
    
    class Meta:
        model = Comment
        fields = ['content', 'parent']
    
    def validate_parent(self, value):
        """Ensure parent comment belongs to the same post"""
        if value:
            post_id = self.context.get('post_id')
            if post_id:
                # Convert post_id to UUID if it's a string
                import uuid
                if isinstance(post_id, str):
                    try:
                        post_id = uuid.UUID(post_id)
                    except ValueError:
                        raise serializers.ValidationError(
                            "Invalid post ID format"
                        )
                
                if value.post.id != post_id:
                    raise serializers.ValidationError(
                        "Parent comment must belong to the same post"
                    )
        return value


class LikeSerializer(serializers.ModelSerializer):
    """
    Serializer for likes
    """
    user = AuthorSerializer(read_only=True)
    
    class Meta:
        model = Like
        fields = ['id', 'user', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']
