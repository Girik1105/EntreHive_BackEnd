from django.contrib import admin
from .models import UserProfile, Follow


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'get_full_name', 'user_role', 'university', 
        'location', 'is_profile_public', 'created_at', 'email_verified'
    ]
    list_filter = [
        'user_role', 'is_profile_public', 'show_email', 'created_at',
        'email_verified'
    ]
    search_fields = [
        'user__username', 'user__email', 'first_name', 'last_name',
        'bio', 'university__name', 'location'
    ]
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'first_name', 'last_name', 'user_role')
        }),
        ('Profile Details', {
            'fields': ('profile_picture', 'bio', 'location', 'university')
        }),
        ('Role-Specific Information', {
            'fields': (
                'major', 'graduation_year',  # Student
                'department', 'research_interests',  # Professor
                'investment_focus', 'company'  # Investor
            ),
            'classes': ('collapse',)
        }),
        ('Social Links', {
            'fields': ('linkedin_url', 'website_url', 'github_url'),
            'classes': ('collapse',)
        }),
        ('Privacy Settings', {
            'fields': ('is_profile_public', 'show_email')
        }),
        ('Email Verification', {
            'fields': ('email_verified', 'verification_sent_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = 'Full Name'


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ['follower', 'following', 'created_at']
    list_filter = ['created_at']
    search_fields = ['follower__username', 'following__username']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
