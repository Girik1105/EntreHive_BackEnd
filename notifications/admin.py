from django.contrib import admin
from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['notification_type', 'recipient', 'sender', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['recipient__username', 'sender__username', 'title', 'message']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('recipient', 'sender')


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'follow_enabled', 'like_enabled', 'comment_enabled', 'mention_enabled', 'message_enabled', 'project_invite_enabled', 'project_join_enabled']
    list_filter = ['follow_enabled', 'like_enabled', 'comment_enabled', 'mention_enabled', 'message_enabled']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['user__username']

    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Notification Preferences', {
            'fields': (
                'follow_enabled',
                'like_enabled',
                'comment_enabled',
                'mention_enabled',
                'message_enabled',
                'project_invite_enabled',
                'project_join_enabled'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
