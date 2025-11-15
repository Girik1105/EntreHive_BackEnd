from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Project, ProjectInvitation
from accounts.serializers import UserProfileSerializer
from notifications.models import Notification


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user serializer for project team member display"""
    full_name = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'full_name', 'profile']
        read_only_fields = ['id', 'username', 'email']
    
    def get_full_name(self, obj):
        if hasattr(obj, 'profile'):
            return obj.profile.get_full_name()
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username
    
    def get_profile(self, obj):
        """Include profile data with full_name"""
        try:
            if hasattr(obj, 'profile') and obj.profile:
                return {
                    'full_name': obj.profile.get_full_name(),
                    'profile_picture': obj.profile.profile_picture.url if obj.profile.profile_picture else None,
                    'user_role': obj.profile.user_role,
                    'university': {
                        'id': str(obj.profile.university.id),
                        'name': obj.profile.university.name,
                        'short_name': obj.profile.university.short_name
                    } if obj.profile.university else None,
                    'bio': obj.profile.bio,
                }
        except Exception as e:
            # Log the error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error accessing profile for user {obj.id}: {e}")
        
        # Fallback when profile doesn't exist or there's an error
        return {
            'full_name': f"{obj.first_name} {obj.last_name}".strip() or obj.username,
            'profile_picture': None,
            'user_role': 'student',
            'university': None,
            'bio': None,
        }


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for Project model"""
    owner = UserBasicSerializer(read_only=True)
    team_members = UserBasicSerializer(many=True, read_only=True)
    team_count = serializers.SerializerMethodField()
    is_team_member = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    banner_image = serializers.ImageField(required=False, allow_null=True)
    university = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id', 'title', 'owner', 'team_members', 'project_type', 'status',
            'summary', 'needs', 'categories', 'tags', 'preview_image',
            'banner_style', 'banner_gradient', 'banner_image',
            'pitch_url', 'repo_url', 'visibility', 'university', 'created_at', 'updated_at',
            'team_count', 'is_team_member', 'can_edit',
            'approval_status', 'reviewed_at', 'rejection_reason'
        ]
        read_only_fields = ['id', 'owner', 'university', 'created_at', 'updated_at',
                           'approval_status', 'reviewed_at', 'rejection_reason']
    
    def get_university(self, obj):
        """Return university information"""
        if obj.university:
            return {
                'id': obj.university.id,
                'name': obj.university.name,
                'short_name': getattr(obj.university, 'short_name', obj.university.name)
            }
        return None
    
    def get_team_count(self, obj):
        return obj.get_team_count()
    
    def get_is_team_member(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.is_team_member(request.user)
        return False
    
    def get_can_edit(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return request.user == obj.owner
        return False
    
    def create(self, validated_data):
        # Set the owner to the current user
        request = self.context.get('request')
        validated_data['owner'] = request.user
        return super().create(validated_data)


class ProjectCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating projects"""
    banner_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Project
        fields = [
            'id', 'title', 'project_type', 'status', 'summary', 'needs',
            'categories', 'tags', 'preview_image', 'banner_style',
            'banner_gradient', 'banner_image', 'pitch_url',
            'repo_url', 'visibility'
        ]
        read_only_fields = ['id']
    
    def create(self, validated_data):
        # Set the owner to the current user
        request = self.context.get('request')
        validated_data['owner'] = request.user
        return super().create(validated_data)


class ProjectUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating projects"""
    banner_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Project
        fields = [
            'title', 'project_type', 'status', 'summary', 'needs',
            'categories', 'tags', 'preview_image', 'banner_style',
            'banner_gradient', 'banner_image', 'pitch_url',
            'repo_url', 'visibility'
        ]


class ProjectInvitationSerializer(serializers.ModelSerializer):
    """Serializer for Project Invitations"""
    project = ProjectSerializer(read_only=True)
    inviter = UserBasicSerializer(read_only=True)
    invitee = UserBasicSerializer(read_only=True)
    invitee_username = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = ProjectInvitation
        fields = [
            'id', 'project', 'inviter', 'invitee', 'invitee_username',
            'message', 'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'inviter', 'status', 'created_at', 'updated_at']
    
    def validate_invitee_username(self, value):
        """Validate that the invitee username exists"""
        if value:
            try:
                user = User.objects.get(username=value)
                return user
            except User.DoesNotExist:
                raise serializers.ValidationError("User with this username does not exist.")
        return value
    
    def create(self, validated_data):
        request = self.context.get('request')
        project_id = self.context.get('project_id')
        
        # Get the project
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            raise serializers.ValidationError("Project does not exist.")
        
        # Check if user can invite (must be owner or team member)
        if not project.is_team_member(request.user):
            raise serializers.ValidationError("You don't have permission to invite users to this project.")
        
        # Get invitee from username
        invitee_username = validated_data.pop('invitee_username', None)
        if invitee_username:
            invitee = self.validate_invitee_username(invitee_username)
            validated_data['invitee'] = invitee
        
        # Set additional fields
        validated_data['project'] = project
        validated_data['inviter'] = request.user
        
        # Check if user is already a team member
        if project.is_team_member(validated_data['invitee']):
            raise serializers.ValidationError("User is already a member of this project.")
        
        # Check for existing pending invitation
        existing_invitation = ProjectInvitation.objects.filter(
            project=project,
            invitee=validated_data['invitee'],
            status='pending'
        ).first()
        
        if existing_invitation:
            raise serializers.ValidationError("A pending invitation already exists for this user.")

        invitation = super().create(validated_data)

        # Create notification for the invitee
        try:
            Notification.create_project_invite_notification(
                inviter=request.user,
                invitee=invitation.invitee,
                project_id=project.id,
                project_title=project.title
            )
        except Exception as e:
            print(f"Error creating project invitation notification: {e}")

        return invitation


class AddTeamMemberSerializer(serializers.Serializer):
    """Serializer for adding team members by username"""
    username = serializers.CharField()
    
    def validate_username(self, value):
        try:
            user = User.objects.get(username=value)
            return user
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this username does not exist.")
    
    def save(self, project):
        user = self.validated_data['username']
        
        # Check if user is already a team member
        if project.is_team_member(user):
            raise serializers.ValidationError("User is already a member of this project.")
        
        # Add user to project
        success = project.add_team_member(user)
        if not success:
            raise serializers.ValidationError("Failed to add user to project.")
        
        return user
