from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinLengthValidator, MaxLengthValidator
import uuid


class Project(models.Model):
    """
    Project model with one-to-many relationship to users
    One project can have many users
    """
    
    # Project types
    PROJECT_TYPE_CHOICES = [
        ('startup', 'Startup'),
        ('side_project', 'Side Project'),
        ('research', 'Research'),
        ('hackathon', 'Hackathon'),
        ('course_project', 'Course Project'),
    ]
    
    # Project status
    STATUS_CHOICES = [
        ('concept', 'Concept'),
        ('mvp', 'MVP'),
        ('launched', 'Launched'),
    ]
    
    # Visibility options
    VISIBILITY_CHOICES = [
        ('private', 'Private'),
        ('university', 'University'),
        ('public', 'Public'),
    ]

    BANNER_STYLE_CHOICES = [
        ('gradient', 'Gradient'),
        ('image', 'Image'),
    ]

    # Approval status choices
    APPROVAL_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    # Project needs
    NEED_CHOICES = [
        ('design', 'Design'),
        ('dev', 'Development'),
        ('marketing', 'Marketing'),
        ('research', 'Research'),
        ('funding', 'Funding'),
        ('mentor', 'Mentor'),
    ]
    
    # Core fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(
        max_length=140, 
        validators=[MinLengthValidator(3)],
        help_text="Project title (3-140 characters)"
    )
    
    # Owner relationship
    owner = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='owned_projects',
        help_text="Project owner"
    )
    
    # University relationship
    university = models.ForeignKey(
        'universities.University',
        on_delete=models.CASCADE,
        related_name='projects',
        help_text="University associated with this project (derived from owner's university)"
    )
    
    # Team members relationship (many-to-many)
    team_members = models.ManyToManyField(
        User,
        related_name='projects',
        blank=True,
        help_text="Users who are part of this project"
    )
    
    # Project details
    project_type = models.CharField(
        max_length=20, 
        choices=PROJECT_TYPE_CHOICES,
        help_text="Type of project"
    )
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='concept',
        help_text="Current project status"
    )
    
    summary = models.TextField(
        max_length=5000, 
        blank=True, 
        null=True,
        help_text="Detailed project description"
    )
    
    # Project requirements and categorization
    needs = models.JSONField(
        default=list,
        blank=True,
        help_text="Array of project needs (design, dev, marketing, etc.)"
    )
    
    categories = models.JSONField(
        default=list,
        blank=True,
        help_text="Project categories (e.g., AI, EdTech)"
    )
    
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Project tags for searchability"
    )
    
    # Media and links
    preview_image = models.URLField(
        blank=True, 
        null=True,
        help_text="Preview image URL"
    )

    banner_style = models.CharField(
        max_length=20,
        choices=BANNER_STYLE_CHOICES,
        default='gradient',
        help_text="Display style for the project hero/banner"
    )

    banner_gradient = models.CharField(
        max_length=50,
        default='sunrise',
        help_text="Identifier for the selected banner gradient"
    )

    banner_image = models.ImageField(
        upload_to='project_banners/',
        blank=True,
        null=True,
        help_text="Optional uploaded banner image"
    )
    
    pitch_url = models.URLField(
        blank=True, 
        null=True,
        help_text="Pitch video/presentation URL"
    )
    
    repo_url = models.URLField(
        blank=True, 
        null=True,
        help_text="Repository URL (GitHub, GitLab, etc.)"
    )
    
    # Visibility and access
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='private',
        help_text="Project visibility level"
    )

    # Approval workflow fields
    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default='pending',
        help_text="Approval status for project moderation"
    )

    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_projects',
        help_text="Admin who reviewed this project"
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when project was reviewed"
    )

    rejection_reason = models.TextField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Reason for rejection (if applicable)"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project_type']),
            models.Index(fields=['status']),
            models.Index(fields=['visibility']),
            models.Index(fields=['approval_status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.owner.username}"
    
    def get_team_count(self):
        """Return total number of team members including owner"""
        return self.team_members.count() + 1  # +1 for owner
    
    def is_team_member(self, user):
        """Check if user is part of the project team (including owner)"""
        return user == self.owner or self.team_members.filter(id=user.id).exists()
    
    def add_team_member(self, user):
        """Add a user to the project team"""
        if user != self.owner and not self.team_members.filter(id=user.id).exists():
            self.team_members.add(user)
            return True
        return False
    
    def remove_team_member(self, user):
        """Remove a user from the project team"""
        if user != self.owner and self.team_members.filter(id=user.id).exists():
            self.team_members.remove(user)
            return True
        return False
    
    @property
    def all_team_members(self):
        """Get all team members including the owner"""
        from django.db.models import Q
        team_ids = list(self.team_members.values_list('id', flat=True))
        team_ids.append(self.owner.id)
        return User.objects.filter(id__in=team_ids)
    
    def save(self, *args, **kwargs):
        """Override save to automatically set university from owner's profile"""
        if self.owner and hasattr(self.owner, 'profile') and self.owner.profile.university:
            self.university = self.owner.profile.university
        super().save(*args, **kwargs)


class ProjectInvitation(models.Model):
    """
    Model to handle project invitations
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name='invitations'
    )
    inviter = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='sent_invitations'
    )
    invitee = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='received_invitations'
    )
    message = models.TextField(
        max_length=500, 
        blank=True, 
        null=True,
        help_text="Optional invitation message"
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Project Invitation"
        verbose_name_plural = "Project Invitations"
        ordering = ['-created_at']
        unique_together = ('project', 'invitee')  # Prevent duplicate invitations
    
    def __str__(self):
        return f"{self.project.title} - {self.inviter.username} → {self.invitee.username}"
    
    def accept(self):
        """Accept the invitation and add user to project"""
        if self.status == 'pending':
            self.status = 'accepted'
            self.save()
            self.project.add_team_member(self.invitee)
            return True
        return False
    
    def decline(self):
        """Decline the invitation"""
        if self.status == 'pending':
            self.status = 'declined'
            self.save()
            return True
        return False
    
    def cancel(self):
        """Cancel the invitation (by inviter)"""
        if self.status == 'pending':
            self.status = 'cancelled'
            self.save()
            return True
        return False
