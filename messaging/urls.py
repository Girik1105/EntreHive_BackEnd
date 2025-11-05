from django.urls import path
from . import views

urlpatterns = [
    # Conversations
    path('conversations/', views.ConversationListView.as_view(), name='conversation-list'),
    path('conversations/create/', views.CreateConversationView.as_view(), name='conversation-create'),
    path('conversations/<uuid:id>/', views.ConversationDetailView.as_view(), name='conversation-detail'),
    path('conversations/<uuid:conversation_id>/archive/', views.archive_conversation, name='conversation-archive'),
    path('conversations/<uuid:conversation_id>/unarchive/', views.unarchive_conversation, name='conversation-unarchive'),
    
    # Messages
    path('conversations/<uuid:conversation_id>/messages/', views.MessageListCreateView.as_view(), name='message-list-create'),
    path('messages/<uuid:message_id>/read/', views.mark_message_read, name='message-read'),
    
    # Project View Requests
    path('project-requests/', views.ProjectViewRequestListCreateView.as_view(), name='project-request-list-create'),
    path('project-requests/<uuid:id>/', views.ProjectViewRequestDetailView.as_view(), name='project-request-detail'),
    path('project-requests/<uuid:request_id>/respond/', views.respond_to_project_request, name='project-request-respond'),
    path('project-requests/<uuid:request_id>/cancel/', views.cancel_project_request, name='project-request-cancel'),
    
    # Stats
    path('stats/', views.inbox_stats, name='inbox-stats'),

    # Group Conversations
    path('group-conversations/', views.GroupConversationListView.as_view(), name='group-conversation-list'),
    path('group-conversations/create/', views.CreateGroupConversationView.as_view(), name='group-conversation-create'),
    path('group-conversations/<uuid:pk>/', views.GroupConversationDetailView.as_view(), name='group-conversation-detail'),
    path('group-conversations/<uuid:group_id>/messages/', views.GroupMessageListView.as_view(), name='group-message-list'),
    path('group-conversations/<uuid:group_id>/messages/create/', views.CreateGroupMessageView.as_view(), name='group-message-create'),
]

