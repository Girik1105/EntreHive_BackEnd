from django.urls import path
from . import views
from . import investor_views

app_name = 'projects'

urlpatterns = [
    # Investor-specific routes (must come before general routes to avoid conflicts)
    path('investor/check-access/', investor_views.check_investor_access, name='investor-check-access'),
    path('investor/<uuid:id>/', investor_views.InvestorProjectDetailView.as_view(), name='investor-project-detail'),
    
    # Project CRUD (students/professors only)
    path('', views.ProjectListCreateView.as_view(), name='project-list-create'),
    path('<uuid:pk>/', views.ProjectDetailView.as_view(), name='project-detail'),
    
    # User projects
    path('user/<int:user_id>/', views.UserProjectsView.as_view(), name='user-projects'),
    
    # Team management (students/professors only)
    path('<uuid:project_id>/team/add/', views.add_team_member, name='add-team-member'),
    path('<uuid:project_id>/team/remove/<int:user_id>/', views.remove_team_member, name='remove-team-member'),
    
    # Invitations (students/professors only)
    path('<uuid:project_id>/invitations/', views.ProjectInvitationListCreateView.as_view(), name='project-invitations'),
    path('invitations/me/', views.UserInvitationsView.as_view(), name='my-invitations'),
    path('invitations/<uuid:invitation_id>/respond/', views.respond_to_invitation, name='respond-invitation'),
    
    # Categories
    path('categories/', views.CategoryListView.as_view(), name='category-list'),

    # Search endpoints
    path('search/', views.project_search, name='project-search'),
    path('categories/search/', views.categories_search, name='categories-search'),
]
