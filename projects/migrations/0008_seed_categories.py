from django.db import migrations
from django.utils.text import slugify


# Union of all categories from existing projects + hardcoded investor topics
SEED_CATEGORIES = [
    'AI/ML', 'Accessibility', 'Analytics', 'Art Tech', 'Automation',
    'B2B Tools', 'BioTech', 'Blockchain', 'CRM', 'CleanTech',
    'Cloud Computing', 'Community', 'Content Creation', 'Cybersecurity',
    'Design', 'DevOps', 'E-commerce', 'Education', 'Environment',
    'FinTech', 'Gaming', 'Healthcare', 'IoT', 'MarTech',
    'Materials Science', 'Media', 'Mobile Apps', 'Music Tech',
    'Non-profit', 'Productivity', 'Quantum', 'Robotics', 'SaaS',
    'Social Impact', 'Space Tech', 'VR/AR', 'Web Development',
    # From investor topics (add any not already covered)
    'AI', 'Web Dev', 'Fintech', 'Biotech', 'Climate',
    'Hardware', 'EdTech', 'HealthTech', 'Social Justice',
]


def seed_categories(apps, schema_editor):
    Category = apps.get_model('projects', 'Category')
    seen_slugs = set()
    order = 0
    for name in SEED_CATEGORIES:
        slug = slugify(name)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        Category.objects.get_or_create(
            slug=slug,
            defaults={
                'name': name,
                'is_active': True,
                'display_order': order,
            }
        )
        order += 10


def reverse_seed(apps, schema_editor):
    Category = apps.get_model('projects', 'Category')
    Category.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0007_category'),
    ]

    operations = [
        migrations.RunPython(seed_categories, reverse_seed),
    ]
