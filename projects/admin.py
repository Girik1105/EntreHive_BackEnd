from django.contrib import admin
from django.utils import timezone
from .models import Project, ProjectInvitation


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['title', 'owner', 'project_type', 'status', 'visibility', 'approval_status', 'created_at', 'team_count']
    list_filter = ['approval_status', 'project_type', 'status', 'visibility', 'created_at']
    search_fields = ['title', 'summary', 'owner__username', 'owner__email']
    readonly_fields = ['id', 'created_at', 'updated_at', 'reviewed_by', 'reviewed_at']
    filter_horizontal = ['team_members']
    actions = ['approve_projects', 'reject_projects']

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'title', 'owner', 'project_type', 'status')
        }),
        ('Content', {
            'fields': ('summary', 'preview_image', 'pitch_url', 'repo_url')
        }),
        ('Categorization', {
            'fields': ('needs', 'categories', 'tags')
        }),
        ('Team & Access', {
            'fields': ('team_members', 'visibility')
        }),
        ('Moderation & Approval', {
            'fields': ('approval_status', 'reviewed_by', 'reviewed_at', 'rejection_reason'),
            'classes': ('wide',),
            'description': 'Review and approve/reject projects. Approved projects are visible to all users.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def team_count(self, obj):
        return obj.get_team_count()
    team_count.short_description = 'Team Size'

    def approve_projects(self, request, queryset):
        """Bulk approve selected projects"""
        updated = 0
        for project in queryset:
            project.approval_status = 'approved'
            project.reviewed_by = request.user
            project.reviewed_at = timezone.now()
            project.rejection_reason = None  # Clear any previous rejection reason
            project.save()
            updated += 1

        self.message_user(request, f'{updated} project(s) successfully approved.')
    approve_projects.short_description = 'Approve selected projects'

    def reject_projects(self, request, queryset):
        """Bulk reject selected projects"""
        updated = 0
        for project in queryset:
            project.approval_status = 'rejected'
            project.reviewed_by = request.user
            project.reviewed_at = timezone.now()
            # Note: Rejection reason should be set manually in the admin detail page
            project.save()
            updated += 1

        self.message_user(request, f'{updated} project(s) rejected. Please add rejection reasons individually.')
    reject_projects.short_description = 'Reject selected projects'


@admin.register(ProjectInvitation)
class ProjectInvitationAdmin(admin.ModelAdmin):
    list_display = ['project', 'inviter', 'invitee', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['project__title', 'inviter__username', 'invitee__username']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Invitation Details', {
            'fields': ('id', 'project', 'inviter', 'invitee', 'message')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )