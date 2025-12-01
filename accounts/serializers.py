from rest_framework import serializers
from dj_rest_auth.registration.serializers import RegisterSerializer
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import UserProfile
from utils.image_compression import ImageCompressor
import re
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


class CustomRegisterSerializer(RegisterSerializer):
    """
    Custom registration serializer that requires both username and email
    """
    username = serializers.CharField(
        max_length=150,
        min_length=1,
        required=True
    )
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True
    )
    last_name = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True
    )

    def validate_username(self, username):
        """
        Check if username is unique
        """
        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError(
                "A user with that username already exists."
            )
        return username

    def validate_email(self, email):
        """
        Check if email is unique
        """
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                "A user with that email already exists."
            )
        return email

    def get_cleaned_data(self):
        """
        Return cleaned data for user creation
        """
        return {
            'username': self.validated_data.get('username', ''),
            'password1': self.validated_data.get('password1', ''),
            'password2': self.validated_data.get('password2', ''),
            'email': self.validated_data.get('email', ''),
            'first_name': self.validated_data.get('first_name', ''),
            'last_name': self.validated_data.get('last_name', ''),
        }

    def save(self, request):
        """
        Create and return a new user instance
        """
        adapter = get_adapter()
        user = adapter.new_user(request)
        self.cleaned_data = self.get_cleaned_data()
        adapter.save_user(request, user, self)
        return user


# Import this here to avoid circular imports
from allauth.account import app_settings
from allauth.account.adapter import get_adapter


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for UserProfile model with all fields
    """
    full_name = serializers.SerializerMethodField()
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    university_name = serializers.SerializerMethodField()
    role_specific_info = serializers.ReadOnlyField()
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    is_followed_by = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    banner_image = serializers.SerializerMethodField()
    is_staff = serializers.BooleanField(source='user.is_staff', read_only=True)
    is_superuser = serializers.BooleanField(source='user.is_superuser', read_only=True)
    days_until_disabled = serializers.SerializerMethodField()
    should_show_verification_warning = serializers.SerializerMethodField()
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'username', 'email', 'full_name',
            'first_name', 'last_name', 'user_role',
            'profile_picture', 'bio', 'location', 'university', 'university_name',
            'major', 'graduation_year',  # Student fields
            'department', 'research_interests',  # Professor fields
            'investment_focus', 'company', 'interests',  # Investor fields
            'linkedin_url', 'website_url', 'github_url',
            'banner_style', 'banner_gradient', 'banner_image',  # Banner fields
            'is_profile_public', 'show_email',
            'email_verified', 'verification_sent_at', 'days_until_disabled', 'should_show_verification_warning',  # Email verification
            'role_specific_info', 'created_at', 'updated_at',
            'followers_count', 'following_count', 'is_following', 'is_followed_by',
            'is_staff', 'is_superuser'  # Django admin fields
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_staff', 'is_superuser', 'email_verified', 'verification_sent_at']
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    
    def get_university_name(self, obj):
        """Return university name instead of UUID"""
        return obj.university.name if obj.university else None
    
    def get_followers_count(self, obj):
        """Return followers count"""
        return obj.get_followers_count()
    
    def get_following_count(self, obj):
        """Return following count"""
        return obj.get_following_count()
    
    def get_is_following(self, obj):
        """Check if current user is following this user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated and request.user != obj.user:
            return obj.is_followed_by(request.user)
        return False
    
    def get_is_followed_by(self, obj):
        """Check if this user is followed by current user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated and request.user != obj.user:
            return obj.is_following(request.user)
        return False
    
    def get_profile_picture(self, obj):
        """Return absolute URL for profile picture"""
        if obj.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None
    
    def get_banner_image(self, obj):
        """Return absolute URL for banner image"""
        if obj.banner_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.banner_image.url)
            return obj.banner_image.url
        return None
    
    def get_days_until_disabled(self, obj):
        """Return days remaining until account is disabled"""
        if obj.email_verified:
            return None
        days_since = obj.days_since_verification_sent()
        if days_since is None:
            return 30
        return max(0, 30 - days_since)
    
    def get_should_show_verification_warning(self, obj):
        """Return whether to show verification warning"""
        return not obj.email_verified
    
    def validate_user_role(self, value):
        """Validate user role"""
        valid_roles = ['student', 'professor', 'investor']
        if value not in valid_roles:
            raise serializers.ValidationError(f"Role must be one of: {', '.join(valid_roles)}")
        return value
    
    def validate_graduation_year(self, value):
        """Validate graduation year"""
        if value is not None:
            import datetime
            current_year = datetime.datetime.now().year
            if value < 1950 or value > current_year + 10:
                raise serializers.ValidationError("Graduation year must be between 1950 and 10 years from now")
        return value


class UserProfileCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating/updating user profiles with role-specific validation
    Includes automatic image compression for profile pictures and banner images.
    """
    banner_image = serializers.ImageField(required=False, allow_null=True)
    profile_picture = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = UserProfile
        fields = [
            'first_name', 'last_name', 'user_role',
            'profile_picture', 'bio', 'location', 'university',
            'major', 'graduation_year',  # Student fields
            'department', 'research_interests',  # Professor fields
            'investment_focus', 'company', 'interests',  # Investor fields
            'linkedin_url', 'website_url', 'github_url',
            'banner_style', 'banner_gradient', 'banner_image',  # Banner fields
            'is_profile_public', 'show_email'
        ]
        read_only_fields = ['user_role']  # Role should not be editable after account creation

    def validate_profile_picture(self, value):
        """Validate and compress profile picture."""
        if value:
            try:
                is_valid, error = ImageCompressor.validate_image(value)
                if not is_valid:
                    raise serializers.ValidationError(error)
            except Exception as e:
                logger.warning(f"Profile picture validation failed: {e}")
                raise serializers.ValidationError(f"Invalid image: {str(e)}")
        return value

    def validate_banner_image(self, value):
        """Validate and compress banner image."""
        if value:
            try:
                is_valid, error = ImageCompressor.validate_image(value)
                if not is_valid:
                    raise serializers.ValidationError(error)
            except Exception as e:
                logger.warning(f"Banner image validation failed: {e}")
                raise serializers.ValidationError(f"Invalid image: {str(e)}")
        return value

    def _compress_images(self, validated_data):
        """Compress profile picture and banner image if present."""
        # Compress profile picture
        if 'profile_picture' in validated_data and validated_data['profile_picture']:
            try:
                validated_data['profile_picture'] = ImageCompressor.compress_profile_picture(
                    validated_data['profile_picture']
                )
                logger.info("Profile picture compressed successfully")
            except Exception as e:
                logger.error(f"Profile picture compression failed: {e}")
                raise serializers.ValidationError(f"Failed to process profile picture: {str(e)}")

        # Compress banner image
        if 'banner_image' in validated_data and validated_data['banner_image']:
            try:
                validated_data['banner_image'] = ImageCompressor.compress_banner_image(
                    validated_data['banner_image']
                )
                logger.info("Banner image compressed successfully")
            except Exception as e:
                logger.error(f"Banner image compression failed: {e}")
                raise serializers.ValidationError(f"Failed to process banner image: {str(e)}")

        return validated_data

    def create(self, validated_data):
        """Create profile with compressed images."""
        validated_data = self._compress_images(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Update profile with compressed images."""
        validated_data = self._compress_images(validated_data)
        return super().update(instance, validated_data)

    def validate(self, data):
        """Cross-field validation based on user role"""
        # Skip validation if we're only updating banner fields
        banner_only_fields = {'banner_style', 'banner_gradient', 'banner_image'}
        if set(data.keys()).issubset(banner_only_fields):
            return data

        user_role = data.get('user_role', self.instance.user_role if self.instance else 'student')

        # Helper function to check if a field has a meaningful value
        def has_meaningful_value(field_name):
            value = data.get(field_name)
            if value and str(value).strip():
                return True
            # Check instance if no meaningful value in data
            if self.instance:
                instance_value = getattr(self.instance, field_name, None)
                if instance_value and str(instance_value).strip():
                    return True
            return False

        # Helper function to check if university exists
        def has_university():
            return (has_meaningful_value('university') or
                   (self.instance and self.instance.university))

        # Role-specific validation - only validate if we're updating relevant fields AND they have meaningful values
        if user_role == 'student':
            if 'major' in data:
                if has_meaningful_value('major'):
                    if not has_university():
                        raise serializers.ValidationError("University is required when major is specified")

        elif user_role == 'professor':
            if 'department' in data:
                if has_meaningful_value('department'):
                    if not has_university():
                        raise serializers.ValidationError("University is required when department is specified")

        elif user_role == 'investor':
            # Investor validation - company is recommended but not required
            pass

        return data


class PublicUserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for public user profiles (limited fields based on privacy settings)
    """
    id = serializers.IntegerField(source='user.id', read_only=True)  # Return User ID, not Profile ID
    full_name = serializers.SerializerMethodField()
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.SerializerMethodField()
    university_name = serializers.SerializerMethodField()
    role_specific_info = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    is_followed_by = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    banner_image = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()  # Add profile object with nested data

    class Meta:
        model = UserProfile
        fields = [
            'id', 'username', 'email', 'full_name',
            'user_role', 'profile_picture', 'bio',
            'location', 'university', 'university_name',
            'linkedin_url', 'website_url', 'github_url',
            'banner_style', 'banner_gradient', 'banner_image',  # Banner fields
            'role_specific_info', 'created_at',
            'followers_count', 'following_count', 'is_following', 'is_followed_by',
            'profile'  # Add profile to fields
        ]

    def get_profile(self, obj):
        """Return profile data matching SendProjectRequest.tsx interface"""
        return {
            'first_name': obj.first_name,
            'last_name': obj.last_name,
            'user_role': obj.user_role,
            'profile_picture': self.get_profile_picture(obj)
        }
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    
    def get_email(self, obj):
        """Only show email if user allows it"""
        if obj.show_email:
            return obj.user.email
        return None
    
    def get_university_name(self, obj):
        """Return university name instead of UUID"""
        return obj.university.name if obj.university else None
    
    def get_role_specific_info(self, obj):
        """Return role-specific info for public viewing"""
        info = obj.role_specific_info
        # Filter out sensitive information if needed
        return info
    
    def get_followers_count(self, obj):
        """Return followers count"""
        return obj.get_followers_count()
    
    def get_following_count(self, obj):
        """Return following count"""
        return obj.get_following_count()
    
    def get_is_following(self, obj):
        """Check if current user is following this user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated and request.user != obj.user:
            return obj.is_followed_by(request.user)
        return False
    
    def get_is_followed_by(self, obj):
        """Check if this user is followed by current user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated and request.user != obj.user:
            return obj.is_following(request.user)
        return False
    
    def get_profile_picture(self, obj):
        """Return absolute URL for profile picture"""
        if obj.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            return obj.profile_picture.url
        return None
    
    def get_banner_image(self, obj):
        """Return absolute URL for banner image"""
        if obj.banner_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.banner_image.url)
            return obj.banner_image.url
        return None


class ExtendedRegisterSerializer(CustomRegisterSerializer):
    """
    Extended registration serializer that includes basic profile fields and university verification
    """
    user_role = serializers.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        default='student',
        required=False
    )
    bio = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    location = serializers.CharField(max_length=100, required=False, allow_blank=True)
    university_id = serializers.UUIDField(required=False, allow_null=True)
    verified_university = serializers.BooleanField(default=False, required=False)
    interests = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        allow_empty=True,
        help_text="Investor interests/categories"
    )
    
    def validate(self, data):
        """
        Validate university verification for non-investors
        """
        data = super().validate(data)
        
        user_role = data.get('user_role', 'student')
        email = data.get('email', '').lower()
        university_id = data.get('university_id')
        verified_university = data.get('verified_university', False)
        
        # Investors can bypass university verification
        if user_role == 'investor':
            return data
        
        # For students and professors, university verification is required
        if user_role in ['student', 'professor']:
            if not verified_university or not university_id:
                # Extract domain for error message
                domain = email.split('@')[1] if '@' in email else 'unknown'
                raise serializers.ValidationError({
                    'email': f'Email domain "{domain}" must be verified with a registered university. Please use your institutional email address.'
                })
            
            # Verify the university exists
            from universities.models import University
            try:
                university = University.objects.get(id=university_id)
                
                # Double-check domain verification
                domain = email.split('@')[1] if '@' in email else ''
                if not self._verify_domain_matches_university(domain, university):
                    raise serializers.ValidationError({
                        'email': f'Email domain does not match the selected university ({university.name})'
                    })
                    
            except University.DoesNotExist:
                raise serializers.ValidationError({
                    'university_id': 'Selected university does not exist'
                })
        
        return data
    
    def _verify_domain_matches_university(self, domain, university):
        """Helper method to verify domain matches university"""
        if not university.email_domain:
            return False
        
        university_domain = university.email_domain.lower().replace('@', '')
        return domain.lower() == university_domain
    
    def get_cleaned_data(self):
        """
        Return cleaned data including profile fields
        """
        data = super().get_cleaned_data()
        data.update({
            'user_role': self.validated_data.get('user_role', 'student'),
            'bio': self.validated_data.get('bio', ''),
            'location': self.validated_data.get('location', ''),
            'university_id': self.validated_data.get('university_id'),
            'interests': self.validated_data.get('interests', []),
        })
        return data
    
    def save(self, request):
        """
        Create user and update profile with additional fields
        """
        user = super().save(request)
        
        # Update the automatically created profile with additional data
        profile = user.profile
        profile.user_role = self.cleaned_data.get('user_role', 'student')
        profile.bio = self.cleaned_data.get('bio', '')
        profile.location = self.cleaned_data.get('location', '')
        profile.first_name = self.cleaned_data.get('first_name', '')
        profile.last_name = self.cleaned_data.get('last_name', '')
        profile.interests = self.cleaned_data.get('interests', [])
        
        # Set university if provided and verified
        university_id = self.cleaned_data.get('university_id')
        if university_id:
            from universities.models import University
            try:
                university = University.objects.get(id=university_id)
                profile.university = university
            except University.DoesNotExist:
                pass  # This should have been caught in validation
        
        profile.save()
        
        return user


# Enhanced serializers with posts and projects
class ProjectSummarySerializer(serializers.Serializer):
    """
    Simplified project serializer for profile inclusion
    """
    id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(read_only=True)
    project_type = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    visibility = serializers.CharField(read_only=True)
    preview_image = serializers.URLField(read_only=True)
    banner_style = serializers.CharField(read_only=True)
    banner_gradient = serializers.CharField(read_only=True)
    banner_image = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    team_count = serializers.SerializerMethodField()
    
    def get_team_count(self, obj):
        return obj.get_team_count()

    def get_banner_image(self, obj):
        if obj.banner_image:
            request = self.context.get('request')
            image_url = obj.banner_image.url
            if request:
                return request.build_absolute_uri(image_url)
            return image_url
        return None


class PostSummarySerializer(serializers.Serializer):
    """
    Simplified post serializer for profile inclusion
    """
    id = serializers.UUIDField(read_only=True)
    content = serializers.CharField(read_only=True)
    image_url = serializers.SerializerMethodField()
    visibility = serializers.CharField(read_only=True)
    is_edited = serializers.BooleanField(read_only=True)
    likes_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    
    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
        return None
    
    def get_likes_count(self, obj):
        return obj.get_likes_count()
    
    def get_comments_count(self, obj):
        return obj.get_comments_count()


class EnhancedUserProfileSerializer(UserProfileSerializer):
    """
    Enhanced profile serializer with posts and projects
    """
    user_posts = serializers.SerializerMethodField()
    owned_projects = serializers.SerializerMethodField()
    member_projects = serializers.SerializerMethodField()
    posts_count = serializers.SerializerMethodField()
    projects_count = serializers.SerializerMethodField()
    
    class Meta(UserProfileSerializer.Meta):
        fields = UserProfileSerializer.Meta.fields + [
            'user_posts', 'owned_projects', 'member_projects', 
            'posts_count', 'projects_count'
        ]
    
    def get_user_posts(self, obj):
        """Get user's recent posts (limited to 10 most recent)"""
        from posts.models import Post
        
        # Check if viewing own profile or if posts should be visible
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if request_user == obj.user:
            # Own profile - show all posts
            posts = Post.objects.filter(author=obj.user)
        else:
            # Other's profile - apply visibility rules
            if request_user and request_user.is_authenticated:
                user_university = getattr(request_user.profile, 'university', None) if hasattr(request_user, 'profile') else None
                posts = Post.objects.filter(
                    author=obj.user
                ).filter(
                    Q(visibility='public') |
                    (Q(visibility='university') & Q(author__profile__university=user_university) if user_university else Q(pk=None))
                )
            else:
                # Unauthenticated - only public posts
                posts = Post.objects.filter(author=obj.user, visibility='public')
        
        posts = posts.order_by('-created_at')[:10]
        return PostSummarySerializer(posts, many=True, context=self.context).data
    
    def get_owned_projects(self, obj):
        """Get projects owned by the user"""
        from projects.models import Project
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if request_user == obj.user:
            # Own profile - show all owned projects
            projects = Project.objects.filter(owner=obj.user)
        else:
            # Other's profile - apply visibility rules
            if request_user and request_user.is_authenticated:
                user_university = getattr(request_user.profile, 'university', None) if hasattr(request_user, 'profile') else None
                projects = Project.objects.filter(
                    owner=obj.user
                ).filter(
                    Q(visibility='public') |
                    Q(visibility='cross_university') |
                    (Q(visibility='university') & Q(owner__profile__university=user_university) if user_university else Q(pk=None))
                )
            else:
                # Unauthenticated - only public projects
                projects = Project.objects.filter(owner=obj.user, visibility='public')
        
        projects = projects.order_by('-created_at')[:10]
        return ProjectSummarySerializer(projects, many=True, context=self.context).data
    
    def get_member_projects(self, obj):
        """Get projects where user is a team member"""
        from projects.models import Project
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if request_user == obj.user:
            # Own profile - show all member projects
            projects = Project.objects.filter(team_members=obj.user)
        else:
            # Other's profile - apply visibility rules
            if request_user and request_user.is_authenticated:
                user_university = getattr(request_user.profile, 'university', None) if hasattr(request_user, 'profile') else None
                projects = Project.objects.filter(
                    team_members=obj.user
                ).filter(
                    Q(visibility='public') |
                    Q(visibility='cross_university') |
                    (Q(visibility='university') & Q(owner__profile__university=user_university) if user_university else Q(pk=None))
                )
            else:
                # Unauthenticated - only public projects
                projects = Project.objects.filter(team_members=obj.user, visibility='public')
        
        projects = projects.order_by('-created_at')[:10]
        return ProjectSummarySerializer(projects, many=True, context=self.context).data
    
    def get_posts_count(self, obj):
        """Get total count of user's visible posts"""
        from posts.models import Post
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if request_user == obj.user:
            return Post.objects.filter(author=obj.user).count()
        else:
            if request_user and request_user.is_authenticated:
                user_university = getattr(request_user.profile, 'university', None) if hasattr(request_user, 'profile') else None
                return Post.objects.filter(
                    author=obj.user
                ).filter(
                    Q(visibility='public') |
                    (Q(visibility='university') & Q(author__profile__university=user_university) if user_university else Q(pk=None))
                ).count()
            else:
                return Post.objects.filter(author=obj.user, visibility='public').count()
    
    def get_projects_count(self, obj):
        """Get total count of user's visible projects"""
        from projects.models import Project
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if request_user == obj.user:
            owned = Project.objects.filter(owner=obj.user).count()
            member = Project.objects.filter(team_members=obj.user).count()
            return {'owned': owned, 'member': member, 'total': owned + member}
        else:
            if request_user and request_user.is_authenticated:
                user_university = getattr(request_user.profile, 'university', None) if hasattr(request_user, 'profile') else None
                owned = Project.objects.filter(
                    owner=obj.user
                ).filter(
                    Q(visibility='public') |
                    Q(visibility='cross_university') |
                    (Q(visibility='university') & Q(owner__profile__university=user_university) if user_university else Q(pk=None))
                ).count()
                member = Project.objects.filter(
                    team_members=obj.user
                ).filter(
                    Q(visibility='public') |
                    Q(visibility='cross_university') |
                    (Q(visibility='university') & Q(owner__profile__university=user_university) if user_university else Q(pk=None))
                ).count()
                return {'owned': owned, 'member': member, 'total': owned + member}
            else:
                owned = Project.objects.filter(owner=obj.user, visibility='public').count()
                member = Project.objects.filter(team_members=obj.user, visibility='public').count()
                return {'owned': owned, 'member': member, 'total': owned + member}


class EnhancedPublicUserProfileSerializer(PublicUserProfileSerializer):
    """
    Enhanced public profile serializer with posts and projects
    """
    user_posts = serializers.SerializerMethodField()
    owned_projects = serializers.SerializerMethodField()
    member_projects = serializers.SerializerMethodField()
    posts_count = serializers.SerializerMethodField()
    projects_count = serializers.SerializerMethodField()
    
    class Meta(PublicUserProfileSerializer.Meta):
        fields = PublicUserProfileSerializer.Meta.fields + [
            'user_posts', 'owned_projects', 'member_projects', 
            'posts_count', 'projects_count'
        ]
    
    def get_user_posts(self, obj):
        """Get user's public posts (limited to 10 most recent)"""
        from posts.models import Post
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if request_user and request_user.is_authenticated:
            user_university = getattr(request_user.profile, 'university', None) if hasattr(request_user, 'profile') else None
            posts = Post.objects.filter(
                author=obj.user
            ).filter(
                Q(visibility='public') |
                (Q(visibility='university') & Q(author__profile__university=user_university) if user_university else Q(pk=None))
            )
        else:
            posts = Post.objects.filter(author=obj.user, visibility='public')
        
        posts = posts.order_by('-created_at')[:10]
        return PostSummarySerializer(posts, many=True, context=self.context).data
    
    def get_owned_projects(self, obj):
        """Get user's public owned projects"""
        from projects.models import Project
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if request_user and request_user.is_authenticated:
            user_university = getattr(request_user.profile, 'university', None) if hasattr(request_user, 'profile') else None
            projects = Project.objects.filter(
                owner=obj.user
            ).filter(
                Q(visibility='public') |
                Q(visibility='cross_university') |
                (Q(visibility='university') & Q(owner__profile__university=user_university) if user_university else Q(pk=None))
            )
        else:
            projects = Project.objects.filter(owner=obj.user, visibility='public')
        
        projects = projects.order_by('-created_at')[:10]
        return ProjectSummarySerializer(projects, many=True, context=self.context).data
    
    def get_member_projects(self, obj):
        """Get user's public member projects"""
        from projects.models import Project
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if request_user and request_user.is_authenticated:
            user_university = getattr(request_user.profile, 'university', None) if hasattr(request_user, 'profile') else None
            projects = Project.objects.filter(
                team_members=obj.user
            ).filter(
                Q(visibility='public') |
                Q(visibility='cross_university') |
                (Q(visibility='university') & Q(owner__profile__university=user_university) if user_university else Q(pk=None))
            )
        else:
            projects = Project.objects.filter(team_members=obj.user, visibility='public')
        
        projects = projects.order_by('-created_at')[:10]
        return ProjectSummarySerializer(projects, many=True, context=self.context).data
    
    def get_posts_count(self, obj):
        """Get count of user's visible posts"""
        from posts.models import Post
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if request_user and request_user.is_authenticated:
            user_university = getattr(request_user.profile, 'university', None) if hasattr(request_user, 'profile') else None
            return Post.objects.filter(
                author=obj.user
            ).filter(
                Q(visibility='public') |
                (Q(visibility='university') & Q(author__profile__university=user_university) if user_university else Q(pk=None))
            ).count()
        else:
            return Post.objects.filter(author=obj.user, visibility='public').count()
    
    def get_projects_count(self, obj):
        """Get count of user's visible projects"""
        from projects.models import Project
        
        request_user = self.context.get('request').user if self.context.get('request') else None
        
        if request_user and request_user.is_authenticated:
            user_university = getattr(request_user.profile, 'university', None) if hasattr(request_user, 'profile') else None
            owned = Project.objects.filter(
                owner=obj.user
            ).filter(
                Q(visibility='public') |
                Q(visibility='cross_university') |
                (Q(visibility='university') & Q(owner__profile__university=user_university) if user_university else Q(pk=None))
            ).count()
            member = Project.objects.filter(
                team_members=obj.user
            ).filter(
                Q(visibility='public') |
                Q(visibility='cross_university') |
                (Q(visibility='university') & Q(owner__profile__university=user_university) if user_university else Q(pk=None))
            ).count()
            return {'owned': owned, 'member': member, 'total': owned + member}
        else:
            owned = Project.objects.filter(owner=obj.user, visibility='public').count()
            member = Project.objects.filter(team_members=obj.user, visibility='public').count()
            return {'owned': owned, 'member': member, 'total': owned + member}


class CustomPasswordResetSerializer(serializers.Serializer):
    """
    Custom password reset serializer that sends reset email with frontend URL
    """
    email = serializers.EmailField()

    def validate_email(self, value):
        """Validate that the email exists in the system"""
        # Check if user exists
        if not User.objects.filter(email__iexact=value).exists():
            # Don't reveal that the user doesn't exist for security
            pass
        return value

    def save(self):
        """Send password reset email with beautiful HTML template"""
        from django.conf import settings
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        from .email_utils import send_password_reset_email
        
        email = self.validated_data['email']
        
        # Get user by email
        users = User.objects.filter(email__iexact=email)
        
        for user in users:
            # Generate token and uid using the same method as Django's built-in password reset
            # IMPORTANT: Must convert user.pk to STRING first, then to bytes for proper encoding
            uid_encoded = urlsafe_base64_encode(force_bytes(str(user.pk)))
            
            # Django 3.x returns bytes, need to decode to string
            if isinstance(uid_encoded, bytes):
                uid = uid_encoded.decode('utf-8')
            else:
                uid = uid_encoded
            
            token = default_token_generator.make_token(user)
            
            # Build frontend reset URL
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            reset_url = f"{frontend_url}/reset-password/{uid}/{token}/"
            
            # Send beautiful HTML email
            try:
                success = send_password_reset_email(user, reset_url)
                if not success:
                    raise serializers.ValidationError("Failed to send password reset email")
            except Exception as e:
                # Error will be logged by email_utils
                raise serializers.ValidationError("Failed to send password reset email")
