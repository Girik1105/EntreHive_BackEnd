# Generated data migration for creating admin permission groups

from django.db import migrations
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


def create_admin_groups(apps, schema_editor):
    """
    Create 5 admin permission groups with appropriate model permissions:
    1. Contact Management
    2. User Management
    3. Project Management
    4. Content Management
    5. University Management
    """

    # Get models
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('accounts', 'UserProfile')
    Follow = apps.get_model('accounts', 'Follow')
    ContactInquiry = apps.get_model('contact', 'ContactInquiry')
    Project = apps.get_model('projects', 'Project')
    ProjectInvitation = apps.get_model('projects', 'ProjectInvitation')
    Post = apps.get_model('posts', 'Post')
    Comment = apps.get_model('posts', 'Comment')
    Like = apps.get_model('posts', 'Like')
    PostShare = apps.get_model('posts', 'PostShare')
    Conversation = apps.get_model('messaging', 'Conversation')
    Message = apps.get_model('messaging', 'Message')
    GroupConversation = apps.get_model('messaging', 'GroupConversation')
    GroupMessage = apps.get_model('messaging', 'GroupMessage')
    ProjectViewRequest = apps.get_model('messaging', 'ProjectViewRequest')
    MessagePermission = apps.get_model('messaging', 'MessagePermission')
    Notification = apps.get_model('notifications', 'Notification')
    NotificationPreference = apps.get_model('notifications', 'NotificationPreference')
    University = apps.get_model('universities', 'University')

    # Helper function to add all permissions for a model to a group
    def add_model_permissions(group, model):
        content_type = ContentType.objects.get_for_model(model)
        permissions = Permission.objects.filter(content_type=content_type)
        group.permissions.add(*permissions)

    # 1. Contact Management Group
    contact_group, created = Group.objects.get_or_create(name='Contact Management')
    if created or not contact_group.permissions.exists():
        contact_group.permissions.clear()
        add_model_permissions(contact_group, ContactInquiry)
        print(f"✓ Created/Updated 'Contact Management' group with permissions")

    # 2. User Management Group
    user_group, created = Group.objects.get_or_create(name='User Management')
    if created or not user_group.permissions.exists():
        user_group.permissions.clear()
        add_model_permissions(user_group, User)
        add_model_permissions(user_group, UserProfile)
        add_model_permissions(user_group, Follow)
        add_model_permissions(user_group, NotificationPreference)
        print(f"✓ Created/Updated 'User Management' group with permissions")

    # 3. Project Management Group
    project_group, created = Group.objects.get_or_create(name='Project Management')
    if created or not project_group.permissions.exists():
        project_group.permissions.clear()
        add_model_permissions(project_group, Project)
        add_model_permissions(project_group, ProjectInvitation)
        print(f"✓ Created/Updated 'Project Management' group with permissions")

    # 4. Content Management Group (Messages and Posts)
    content_group, created = Group.objects.get_or_create(name='Content Management')
    if created or not content_group.permissions.exists():
        content_group.permissions.clear()
        # Posts
        add_model_permissions(content_group, Post)
        add_model_permissions(content_group, Comment)
        add_model_permissions(content_group, Like)
        add_model_permissions(content_group, PostShare)
        # Messaging
        add_model_permissions(content_group, Conversation)
        add_model_permissions(content_group, Message)
        add_model_permissions(content_group, GroupConversation)
        add_model_permissions(content_group, GroupMessage)
        add_model_permissions(content_group, ProjectViewRequest)
        add_model_permissions(content_group, MessagePermission)
        # Notifications
        add_model_permissions(content_group, Notification)
        print(f"✓ Created/Updated 'Content Management' group with permissions")

    # 5. University Management Group
    university_group, created = Group.objects.get_or_create(name='University Management')
    if created or not university_group.permissions.exists():
        university_group.permissions.clear()
        add_model_permissions(university_group, University)
        print(f"✓ Created/Updated 'University Management' group with permissions")

    print("\n" + "="*50)
    print("Successfully created/updated 5 admin permission groups:")
    print("  1. Contact Management")
    print("  2. User Management")
    print("  3. Project Management")
    print("  4. Content Management")
    print("  5. University Management")
    print("="*50)


def remove_admin_groups(apps, schema_editor):
    """
    Reverse migration: Remove the admin permission groups
    """
    Group.objects.filter(name__in=[
        'Contact Management',
        'User Management',
        'Project Management',
        'Content Management',
        'University Management'
    ]).delete()
    print("Removed admin permission groups")


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_add_investor_interests'),
        ('contact', '0001_initial'),
        ('projects', '0006_project_approval_status_project_rejection_reason_and_more'),
        ('posts', '0002_add_search_indexes'),
        ('messaging', '0002_groupconversation_groupmessage'),
        ('notifications', '0005_fix_profile_urls'),
        ('universities', '0002_remove_university_allow_cross_university_collaboration_and_more'),
    ]

    operations = [
        migrations.RunPython(create_admin_groups, remove_admin_groups),
    ]
