from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.utils import timezone
from datetime import timedelta
import random
import uuid

from universities.models import University
from accounts.models import UserProfile
from posts.models import Post
from projects.models import Project
from feed.models import ContentScore


class Command(BaseCommand):
    help = 'Generate comprehensive feed content with 200-300 posts and projects including categories and tags'

    def add_arguments(self, parser):
        parser.add_argument(
            '--posts',
            type=int,
            default=200,
            help='Number of posts to create (default: 200)'
        )
        parser.add_argument(
            '--projects',
            type=int,
            default=100,
            help='Number of projects to create (default: 100)'
        )
        parser.add_argument(
            '--users',
            type=int,
            default=50,
            help='Number of users to create (default: 50)'
        )

    def handle(self, *args, **options):
        self.stdout.write("🚀 Starting comprehensive feed content generation...")
        
        # Create universities first
        universities = self._ensure_universities()
        self.stdout.write(f"✅ Universities ready: {len(universities)}")
        
        # Create users
        users = self._create_users(universities, options['users'])
        self.stdout.write(f"✅ Created {len(users)} users")
        
        # Get all users for content creation
        all_users = list(User.objects.all())
        self.stdout.write(f"📊 Total users available: {len(all_users)}")
        
        # Create posts
        posts = self._create_posts(all_users, options['posts'])
        self.stdout.write(f"✅ Created {len(posts)} posts")
        
        # Create projects with categories and tags
        projects = self._create_projects(all_users, options['projects'])
        self.stdout.write(f"✅ Created {len(projects)} projects")
        
        # Generate content scores for timeline system
        self._generate_content_scores(posts, projects)
        
        self.stdout.write(self.style.SUCCESS("🎉 Feed content generation completed!"))
        self.stdout.write(f"📊 Summary:")
        self.stdout.write(f"   - Users: {len(all_users)}")
        self.stdout.write(f"   - Posts: {len(posts)}")
        self.stdout.write(f"   - Projects: {len(projects)}")
        self.stdout.write(f"   - Universities: {len(universities)}")

    def _ensure_universities(self):
        """Create or get existing universities"""
        university_data = [
            {
                'name': 'Massachusetts Institute of Technology',
                'short_name': 'MIT',
                'city': 'Cambridge',
                'state_province': 'Massachusetts',
                'country': 'United States',
                'university_type': 'private',
                'website': 'https://mit.edu',
                'email_domain': 'mit.edu'
            },
            {
                'name': 'Stanford University',
                'short_name': 'Stanford',
                'city': 'Stanford',
                'state_province': 'California',
                'country': 'United States',
                'university_type': 'private',
                'website': 'https://stanford.edu',
                'email_domain': 'stanford.edu'
            },
            {
                'name': 'University of California, Berkeley',
                'short_name': 'UC Berkeley',
                'city': 'Berkeley',
                'state_province': 'California',
                'country': 'United States',
                'university_type': 'public',
                'website': 'https://berkeley.edu',
                'email_domain': 'berkeley.edu'
            },
            {
                'name': 'Harvard University',
                'short_name': 'Harvard',
                'city': 'Cambridge',
                'state_province': 'Massachusetts',
                'country': 'United States',
                'university_type': 'private',
                'website': 'https://harvard.edu',
                'email_domain': 'harvard.edu'
            },
            {
                'name': 'California Institute of Technology',
                'short_name': 'Caltech',
                'city': 'Pasadena',
                'state_province': 'California',
                'country': 'United States',
                'university_type': 'private',
                'website': 'https://caltech.edu',
                'email_domain': 'caltech.edu'
            }
        ]
        
        universities = []
        for data in university_data:
            university, created = University.objects.get_or_create(
                name=data['name'],
                defaults=data
            )
            universities.append(university)
        
        return universities

    def _create_users(self, universities, count):
        """Create diverse users with profiles"""
        
        first_names = [
            'Alex', 'Jordan', 'Taylor', 'Casey', 'Morgan', 'Avery', 'Riley', 'Cameron',
            'Emma', 'Liam', 'Olivia', 'Noah', 'Ava', 'William', 'Sophia', 'James',
            'Isabella', 'Benjamin', 'Charlotte', 'Lucas', 'Amelia', 'Mason', 'Mia', 'Ethan',
            'Harper', 'Alexander', 'Evelyn', 'Henry', 'Aria', 'Jacob', 'Luna', 'Michael',
            'Priya', 'Raj', 'Ananya', 'Arjun', 'Sneha', 'Vikram', 'Aditi', 'Karan',
            'Maria', 'Carlos', 'Sofia', 'Diego', 'Valentina', 'Sebastian', 'Camila', 'Mateo'
        ]
        
        last_names = [
            'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
            'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson',
            'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson',
            'Patel', 'Sharma', 'Singh', 'Kumar', 'Gupta', 'Chen', 'Wang', 'Li'
        ]
        
        majors = [
            'Computer Science', 'Electrical Engineering', 'Mechanical Engineering', 
            'Business Administration', 'Economics', 'Psychology', 'Biology', 'Chemistry',
            'Physics', 'Mathematics', 'Data Science', 'Artificial Intelligence',
            'Biomedical Engineering', 'Environmental Science', 'Political Science'
        ]
        
        bios = [
            "Building the future of technology 🚀",
            "AI/ML enthusiast and researcher 🤖",
            "Sustainable tech advocate 🌱",
            "Full-stack developer and entrepreneur 💻",
            "Biotech innovator 🧬",
            "Fintech explorer 💰",
            "Space technology enthusiast 🛰️",
            "EdTech revolutionary 📚",
            "Social impact entrepreneur 🌍",
            "Quantum computing researcher 🔬"
        ]
        
        new_users = []

        # Disconnect email signal to avoid sending emails for generated users
        from accounts.signals import send_welcome_and_verification_emails
        post_save.disconnect(send_welcome_and_verification_emails, sender=User)

        try:
            for i in range(count):
                first_name = random.choice(first_names)
                last_name = random.choice(last_names)
                username = f"{first_name.lower()}.{last_name.lower()}{random.randint(100, 999)}"

                # Check if user already exists
                if User.objects.filter(username=username).exists():
                    continue

                university = random.choice(universities)

                user = User.objects.create_user(
                    username=username,
                    email=f"{username}@{university.email_domain}",
                    first_name=first_name,
                    last_name=last_name,
                    password='password123'
                )

                # Create profile
                user_role = random.choice(['student', 'professor', 'investor', 'mentor'])
                profile_data = {
                    'first_name': first_name,
                    'last_name': last_name,
                    'user_role': user_role,
                    'bio': random.choice(bios),
                    'location': f"{random.choice(['San Francisco', 'Boston', 'New York', 'Seattle', 'Austin'])}, USA",
                    'university': university,
                }

                if user_role == 'student':
                    profile_data.update({
                        'major': random.choice(majors),
                        'graduation_year': random.randint(2024, 2028)
                    })
                elif user_role == 'mentor':
                    profile_data.update({
                        'company': random.choice(['TechStars', 'Y Combinator', 'Sequoia Capital', 'a16z', 'Greylock Partners', 'Accel', 'Benchmark']),
                        'investment_focus': random.choice(['AI/ML', 'Fintech', 'EdTech', 'HealthTech', 'SaaS', 'Climate Tech', 'Web3'])
                    })

                # Use update_or_create since post_save signal may have already created an empty profile
                profile, created = UserProfile.objects.update_or_create(
                    user=user,
                    defaults=profile_data
                )

                new_users.append(user)
        finally:
            # Always reconnect the email signal
            post_save.connect(send_welcome_and_verification_emails, sender=User)

        return new_users

    def _create_posts(self, users, count):
        """Create diverse and engaging posts"""
        
        # Post content templates with modern startup/tech themes
        post_templates = [
            "🚀 Just launched {product_name}! A {product_type} that {value_prop}. Early feedback has been incredible - {metric}! Looking for {call_to_action}. #{hashtag1} #{hashtag2}",
            
            "💡 Had a breakthrough moment today working on {project_name}. Realized that {insight}. This could change how we approach {domain}. Thoughts? #{hashtag1} #{hashtag2}",
            
            "📊 Market research update: {statistic} of {target_audience} are struggling with {problem}. That's exactly why we're building {solution}. #{hashtag1} #{hashtag2}",
            
            "🎯 {milestone} achieved! When we started {project_name} {timeframe} ago, this seemed impossible. Key lessons: {lesson1}, {lesson2}, and {lesson3}. #{hashtag1} #{hashtag2}",
            
            "🔬 Deep diving into {technology} and the applications for {use_case} are mind-blowing. Just implemented {feature} and saw {improvement}. #{hashtag1} #{hashtag2}",
            
            "🤝 Looking for {role} to join our {company_type} team! We're {company_description} and need someone passionate about {domain}. DM if interested! #{hashtag1} #{hashtag2}",
            
            "📈 {product_name} just hit {user_metric}! From idea to {milestone} in {timeframe}. Grateful for everyone who believed in the vision. #{hashtag1} #{hashtag2}",
            
            "💭 Hot take: {opinion} will completely transform {industry} in the next {timeframe}. Here's why: {reasoning}. What do you think? #{hashtag1} #{hashtag2}",
            
            "🏆 Excited to announce that {project_name} won {award} at {event}! Thank you to our amazing team and supporters. On to the next challenge! #{hashtag1} #{hashtag2}",
            
            "🌱 Sustainability update: Our {eco_initiative} has resulted in {environmental_impact}. Proving that {sustainable_business_message}. #{hashtag1} #{hashtag2}"
        ]
        
        # Dynamic content variables
        variables = {
            'product_name': ['EcoTracker', 'StudySync', 'CodeMentor', 'HealthHub', 'GreenBuild', 'FinFlow', 'TechBridge', 'DataViz', 'AI Connect', 'SocialGood'],
            'product_type': ['mobile app', 'web platform', 'AI tool', 'SaaS solution', 'IoT device', 'marketplace', 'analytics platform', 'collaboration tool'],
            'value_prop': ['helps students track their carbon footprint', 'connects mentors with aspiring developers', 'analyzes health data for personalized insights', 'automates financial planning for Gen Z'],
            'metric': ['500+ sign-ups in first week', '95% user satisfaction rate', '$10K in pre-orders', '50+ pilot customers'],
            'call_to_action': ['beta testers', 'design feedback', 'co-founders', 'seed funding', 'strategic partnerships'],
            'project_name': ['NextGen Learning', 'Quantum Solutions', 'Green Innovation', 'Social Impact Hub', 'Tech for Good'],
            'insight': ['user behavior patterns are more complex than we thought', 'AI can solve this problem more efficiently', 'the market timing is perfect'],
            'domain': ['education', 'healthcare', 'sustainability', 'fintech', 'social impact'],
            'statistic': ['78%', '85%', '92%', '67%', '89%'],
            'target_audience': ['college students', 'young professionals', 'small business owners', 'healthcare workers'],
            'problem': ['managing their finances', 'finding reliable study partners', 'accessing mental health resources'],
            'solution': ['an AI-powered budgeting app', 'a peer-to-peer learning platform', 'virtual therapy sessions'],
            'milestone': ['$50K ARR', '1000 users', 'Series A funding', 'Product-market fit'],
            'timeframe': ['6 months', '1 year', '18 months', '2 years'],
            'lesson1': ['user feedback is gold', 'iterate fast', 'focus on one thing'],
            'lesson2': ['team chemistry matters', 'timing is everything', 'solve real problems'],
            'lesson3': ['persistence pays off', 'data drives decisions', 'simplicity wins'],
            'technology': ['machine learning', 'blockchain', 'quantum computing', 'edge computing', 'AR/VR'],
            'use_case': ['personalized education', 'sustainable energy', 'healthcare diagnostics', 'financial inclusion'],
            'feature': ['real-time analytics', 'smart recommendations', 'automated workflows', 'predictive modeling'],
            'improvement': ['40% faster processing', '60% better accuracy', '25% cost reduction'],
            'role': ['frontend developer', 'product manager', 'UX designer', 'data scientist', 'marketing lead'],
            'company_type': ['early-stage startup', 'B2B SaaS', 'social impact venture', 'deep tech company'],
            'company_description': ['revolutionizing online education', 'building the future of work', 'solving climate change through technology'],
            'user_metric': ['10K users', '100K downloads', '$100K revenue', '1M API calls'],
            'opinion': ['No-code platforms', 'Quantum computing', 'Sustainable tech', 'AI automation'],
            'industry': ['education', 'healthcare', 'finance', 'manufacturing', 'retail'],
            'reasoning': ['the technology is finally mature', 'market demand is exploding', 'regulatory support is increasing'],
            'award': ['Best Innovation Award', 'Peoples Choice', 'Tech Excellence Prize', 'Social Impact Award'],
            'event': ['TechCrunch Disrupt', 'Y Combinator Demo Day', 'University Innovation Challenge', 'Startup Weekend'],
            'eco_initiative': ['carbon offset program', 'renewable energy switch', 'waste reduction system'],
            'environmental_impact': ['50% carbon reduction', '1000 trees planted', '75% less waste'],
            'sustainable_business_message': ['profit and planet can coexist', 'sustainability drives innovation', 'green tech is the future'],
            'hashtag1': ['startup', 'innovation', 'tech', 'AI', 'sustainability', 'entrepreneurship', 'coding', 'design'],
            'hashtag2': ['building', 'growth', 'learning', 'community', 'future', 'impact', 'success', 'teamwork']
        }
        
        posts = []
        valid_users = [u for u in users if hasattr(u, 'profile') and u.profile.university]
        
        if not valid_users:
            self.stdout.write(self.style.WARNING("No users with university profiles found"))
            return []
        
        for i in range(count):
            author = random.choice(valid_users)
            template = random.choice(post_templates)
            
            # Fill template with random values
            content_vars = {}
            for key in variables:
                if key in template:
                    content_vars[key] = random.choice(variables[key])
            
            try:
                content = template.format(**content_vars)
            except KeyError:
                # Fallback for missing variables
                content = template
            
            post = Post.objects.create(
                author=author,
                content=content,
                visibility=random.choices(
                    ['public', 'university', 'private'],
                    weights=[70, 25, 5]  # More public content for diverse feeds
                )[0],
                created_at=timezone.now() - timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )
            )
            posts.append(post)
        
        return posts

    def _create_projects(self, users, count):
        """Create projects with comprehensive categories and tags"""
        
        # Project categories organized by domain
        categories_by_domain = {
            'Technology': ['AI/ML', 'Web Development', 'Mobile Apps', 'Cybersecurity', 'Blockchain', 'IoT', 'DevOps', 'Cloud Computing'],
            'Business': ['FinTech', 'E-commerce', 'MarTech', 'SaaS', 'B2B Tools', 'Analytics', 'CRM', 'Productivity'],
            'Social Impact': ['Education', 'Healthcare', 'Environment', 'Social Justice', 'Accessibility', 'Non-profit', 'Community'],
            'Creative': ['Design', 'Media', 'Gaming', 'Content Creation', 'Art Tech', 'Music Tech', 'VR/AR', 'Entertainment'],
            'Science': ['BioTech', 'CleanTech', 'Space Tech', 'Materials Science', 'Quantum', 'Robotics', 'Automation']
        }
        
        # Tags for discoverability
        tech_tags = ['python', 'javascript', 'react', 'nodejs', 'tensorflow', 'pytorch', 'docker', 'kubernetes', 'aws', 'firebase']
        business_tags = ['startup', 'mvp', 'saas', 'b2b', 'api', 'analytics', 'growth', 'marketing', 'sales', 'revenue']
        impact_tags = ['sustainability', 'social-good', 'education', 'health', 'accessibility', 'community', 'environment', 'nonprofit']
        creative_tags = ['design', 'ui-ux', 'branding', 'content', 'video', 'audio', 'animation', 'graphics', 'creative']
        science_tags = ['research', 'biotech', 'cleantech', 'innovation', 'lab', 'experiment', 'data', 'algorithm', 'hardware']
        
        all_tags = tech_tags + business_tags + impact_tags + creative_tags + science_tags
        
        # Project templates with realistic titles and descriptions
        project_data = [
            # AI/ML Projects
            {'title': 'StudyBuddy AI', 'summary': 'AI-powered study companion that creates personalized learning paths and quizzes based on your learning style and progress.', 'domain': 'Technology', 'tags': ['ai', 'education', 'machine-learning', 'students']},
            {'title': 'EcoPredict', 'summary': 'Machine learning platform that predicts environmental impact of business decisions and suggests sustainable alternatives.', 'domain': 'Science', 'tags': ['ai', 'environment', 'sustainability', 'prediction']},
            {'title': 'HealthSense', 'summary': 'AI diagnostic tool that analyzes symptoms and medical data to provide preliminary health assessments and recommendations.', 'domain': 'Technology', 'tags': ['ai', 'healthcare', 'diagnostics', 'mobile']},
            
            # Web/Mobile Development
            {'title': 'LocalConnect', 'summary': 'Hyperlocal social platform connecting neighbors for community events, resource sharing, and local business discovery.', 'domain': 'Technology', 'tags': ['social', 'community', 'web', 'mobile']},
            {'title': 'SkillSwap Network', 'summary': 'Peer-to-peer learning marketplace where users can trade skills and knowledge through virtual and in-person sessions.', 'domain': 'Business', 'tags': ['education', 'marketplace', 'skills', 'p2p']},
            {'title': 'CarbonTracker Pro', 'summary': 'Comprehensive carbon footprint tracking app for individuals and businesses with actionable reduction recommendations.', 'domain': 'Science', 'tags': ['environment', 'tracking', 'sustainability', 'mobile']},
            
            # FinTech/Business
            {'title': 'StudentFi', 'summary': 'Financial literacy and budgeting platform designed specifically for college students with gamified saving challenges.', 'domain': 'Business', 'tags': ['fintech', 'students', 'budgeting', 'gamification']},
            {'title': 'InvestorMatch', 'summary': 'Platform connecting early-stage startups with angel investors based on industry, stage, and investment preferences.', 'domain': 'Business', 'tags': ['startup', 'investment', 'networking', 'b2b']},
            {'title': 'CreatorEcon', 'summary': 'Creator economy platform helping content creators monetize their audience through multiple revenue streams and analytics.', 'domain': 'Business', 'tags': ['creator-economy', 'monetization', 'analytics', 'content']},
            
            # Social Impact
            {'title': 'MentorBridge', 'summary': 'Connects underrepresented students with industry professionals for mentorship, career guidance, and networking opportunities.', 'domain': 'Social Impact', 'tags': ['mentorship', 'diversity', 'career', 'networking']},
            {'title': 'FoodRescue', 'summary': 'App that connects restaurants and grocery stores with local charities to redistribute surplus food and reduce waste.', 'domain': 'Social Impact', 'tags': ['food-waste', 'charity', 'sustainability', 'social-good']},
            {'title': 'AccessPath', 'summary': 'Digital accessibility audit platform that helps businesses make their websites and apps more inclusive for users with disabilities.', 'domain': 'Social Impact', 'tags': ['accessibility', 'inclusion', 'web', 'audit']},
            
            # Creative/Design
            {'title': 'DesignCollab', 'summary': 'Real-time collaborative design platform for remote teams with integrated feedback, version control, and client approval workflows.', 'domain': 'Creative', 'tags': ['design', 'collaboration', 'remote-work', 'workflow']},
            {'title': 'StoryAR', 'summary': 'Augmented reality storytelling platform that lets users create immersive narrative experiences in physical spaces.', 'domain': 'Creative', 'tags': ['ar', 'storytelling', 'immersive', 'creative']},
            {'title': 'MusicMind', 'summary': 'AI-powered music composition tool that helps musicians generate melodies, harmonies, and arrangements based on their style.', 'domain': 'Creative', 'tags': ['music', 'ai', 'composition', 'creative-tools']},
            
            # Science/Research
            {'title': 'LabFlow', 'summary': 'Laboratory management system that digitizes research workflows, tracks experiments, and facilitates collaboration between researchers.', 'domain': 'Science', 'tags': ['research', 'lab-management', 'workflow', 'collaboration']},
            {'title': 'BioPrint3D', 'summary': '3D bioprinting platform for creating tissue models and organ prototypes for medical research and drug testing.', 'domain': 'Science', 'tags': ['biotech', '3d-printing', 'medical', 'research']},
            {'title': 'QuantumSim', 'summary': 'Quantum computing simulator that makes quantum algorithms accessible to computer science students and researchers.', 'domain': 'Science', 'tags': ['quantum', 'simulation', 'education', 'computing']},
            
            # More diverse projects
            {'title': 'PlantNet IoT', 'summary': 'Smart agriculture system using IoT sensors to monitor soil conditions, automate irrigation, and optimize crop yields.', 'domain': 'Science', 'tags': ['iot', 'agriculture', 'automation', 'sensors']},
            {'title': 'CodeReview AI', 'summary': 'AI-powered code review assistant that identifies bugs, suggests improvements, and ensures coding best practices.', 'domain': 'Technology', 'tags': ['ai', 'code-review', 'development', 'quality']},
            {'title': 'TherapyBot', 'summary': 'AI chatbot providing 24/7 mental health support and crisis intervention for college students and young adults.', 'domain': 'Social Impact', 'tags': ['mental-health', 'ai', 'support', 'students']},
            {'title': 'EnergyGrid', 'summary': 'Decentralized energy trading platform enabling neighborhoods to buy and sell renewable energy using blockchain technology.', 'domain': 'Science', 'tags': ['blockchain', 'energy', 'renewable', 'decentralized']},
            {'title': 'VirtualClassroom', 'summary': 'Immersive VR education platform that creates realistic learning environments for remote and hybrid education.', 'domain': 'Technology', 'tags': ['vr', 'education', 'immersive', 'remote-learning']},
        ]
        
        projects = []
        valid_users = [u for u in users if hasattr(u, 'profile') and u.profile.university]
        
        if not valid_users:
            self.stdout.write(self.style.WARNING("No users with university profiles found"))
            return []
        
        # Create multiple instances of each project template with variations
        for i in range(count):
            template = random.choice(project_data)
            owner = random.choice(valid_users)
            
            # Add some variation to titles for uniqueness
            title_variations = ['', ' Pro', ' Plus', ' 2.0', ' Beta', ' Labs', ' Studio', ' Hub', ' Connect']
            title = template['title'] + random.choice(title_variations)
            
            # Select categories from the domain
            domain_categories = categories_by_domain[template['domain']]
            selected_categories = random.sample(domain_categories, random.randint(1, 3))
            
            # Select tags
            base_tags = template['tags'].copy()
            additional_tags = random.sample(all_tags, random.randint(2, 5))
            all_project_tags = list(set(base_tags + additional_tags))  # Remove duplicates
            
            project = Project.objects.create(
                title=title[:140],  # Ensure it fits the field limit
                owner=owner,
                university=owner.profile.university,
                summary=template['summary'],
                project_type=random.choice(['startup', 'side_project', 'research', 'hackathon', 'course_project']),
                status=random.choice(['concept', 'mvp', 'launched']),
                visibility=random.choices(
                    ['public', 'university', 'private'],
                    weights=[60, 30, 10]  # More public content for feed diversity
                )[0],
                needs=random.sample(['design', 'dev', 'marketing', 'research', 'funding', 'mentor'], 
                                   random.randint(1, 4)),
                categories=selected_categories,
                tags=all_project_tags,
                created_at=timezone.now() - timedelta(
                    days=random.randint(0, 90),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )
            )
            
            # Add team members occasionally
            if random.random() > 0.7:  # 30% chance of having team members
                team_size = random.randint(1, 3)
                potential_members = [u for u in valid_users if u != owner and u.profile.university == owner.profile.university]
                if potential_members:
                    team_members = random.sample(potential_members, min(team_size, len(potential_members)))
                    project.team_members.set(team_members)
            
            projects.append(project)
        
        return projects

    def _generate_content_scores(self, posts, projects):
        """Generate ContentScore entries for the timeline system"""
        self.stdout.write("🔄 Generating content scores for timeline system...")
        
        created_scores = 0
        
        # Generate scores for posts
        for post in posts:
            score, created = ContentScore.objects.get_or_create(
                content_type='post',
                content_id=post.id,
                defaults={
                    'base_score': random.uniform(40.0, 95.0),
                    'engagement_score': random.uniform(0.0, 30.0),
                    'recency_score': self._calculate_recency_score(post.created_at),
                    'trending_score': random.uniform(0.0, 20.0),
                    'expires_at': timezone.now() + timedelta(hours=24)
                }
            )
            if created:
                created_scores += 1
        
        # Generate scores for projects
        for project in projects:
            score, created = ContentScore.objects.get_or_create(
                content_type='project',
                content_id=project.id,
                defaults={
                    'base_score': random.uniform(45.0, 90.0),
                    'engagement_score': random.uniform(10.0, 40.0),  # Projects tend to have higher engagement
                    'recency_score': self._calculate_recency_score(project.created_at),
                    'trending_score': random.uniform(0.0, 25.0),
                    'expires_at': timezone.now() + timedelta(hours=24)
                }
            )
            if created:
                created_scores += 1
        
        self.stdout.write(f" Generated {created_scores} content scores")

    def _calculate_recency_score(self, created_at):
        """Calculate recency score based on age"""
        hours_old = (timezone.now() - created_at).total_seconds() / 3600
        # Decay over 7 days (168 hours)
        return max(0, 100 - (hours_old / 168) * 100)
