from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.services.collector import collector
from app.repository.news_repo import news_repo
from app.services.ranking_engine import ranking_engine
from app.services.ai_service import ai_service
from app.services.scraper_service import scraper_service
from app.services.image_service import image_service
from app.models.models import Post, News, GenerationRun, ActivityLog, PublishLog, PublishQueue
import asyncio
from datetime import datetime, timedelta
import os
import logging
import random
import re

logger = logging.getLogger(__name__)

FALLBACK_IMAGES_REGISTRY = [
    {"url": "https://images.unsplash.com/photo-1607799279861-4dd421887fb3?w=800", "theme": "code", "color": "green", "style": "realistic"},
    {"url": "https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=800", "theme": "workspace", "color": "grey", "style": "minimalist"},
    {"url": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=800", "theme": "abstract", "color": "blue", "style": "conceptual"},
    {"url": "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=800", "theme": "datacenter", "color": "blue", "style": "realistic"},
    {"url": "https://images.unsplash.com/photo-1593508512255-86ab42a8e620?w=800", "theme": "device", "color": "grey", "style": "minimalist"},
    {"url": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=800", "theme": "hardware", "color": "grey", "style": "cyberpunk"},
    {"url": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800", "theme": "hardware", "color": "green", "style": "realistic"},
    {"url": "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=800", "theme": "hardware", "color": "grey", "style": "conceptual"},
    {"url": "https://images.unsplash.com/photo-1531297484001-80022131f5a1?w=800", "theme": "device", "color": "blue", "style": "minimalist"},
    {"url": "https://images.unsplash.com/photo-1504639725590-34d0984388bd?w=800", "theme": "code", "color": "green", "style": "cyberpunk"},
    {"url": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=800", "theme": "code", "color": "green", "style": "conceptual"},
    {"url": "https://images.unsplash.com/photo-1563986768609-322da13575f3?w=800", "theme": "device", "color": "grey", "style": "minimalist"},
    {"url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800", "theme": "abstract", "color": "pink", "style": "minimalist"},
    {"url": "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=800", "theme": "abstract", "color": "purple", "style": "cyberpunk"},
    {"url": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=800", "theme": "workspace", "color": "grey", "style": "realistic"},
    {"url": "https://images.unsplash.com/photo-1531403009284-440f080d1e12?w=800", "theme": "workspace", "color": "blue", "style": "minimalist"},
    {"url": "https://images.unsplash.com/photo-1581092921461-eab62e97a780?w=800", "theme": "hardware", "color": "grey", "style": "realistic"},
    {"url": "https://images.unsplash.com/photo-1535378917042-10a22c95931a?w=800", "theme": "abstract", "color": "dark", "style": "conceptual"},
    {"url": "https://images.unsplash.com/photo-1544256718-3bcf237f3974?w=800", "theme": "code", "color": "dark", "style": "realistic"},
    {"url": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=800", "theme": "abstract", "color": "blue", "style": "minimalist"}
]

def select_relevant_fallback_image(title: str, content: str, recent_posts: list) -> str:
    recent_urls = [p.image_url for p in recent_posts if p.image_url]
    recent_themes = {}
    recent_colors = {}
    recent_styles = {}
    
    for url in recent_urls:
        match = next((img for img in FALLBACK_IMAGES_REGISTRY if img["url"] == url), None)
        if match:
            recent_themes[match["theme"]] = recent_themes.get(match["theme"], 0) + 1
            recent_colors[match["color"]] = recent_colors.get(match["color"], 0) + 1
            recent_styles[match["style"]] = recent_styles.get(match["style"], 0) + 1

    # Extract all text for keyword matching
    text = (title + " " + (content or "")).lower()
    
    keyword_map = {
        "code": ["code", "program", "develop", "software", "python", "rust", "js", "typescript", "git", "github", "compiler", "coding", "algorithm", "developer", "engineering", "debugging", "ide", "vscode"],
        "datacenter": ["server", "cloud", "database", "host", "infra", "datacenter", "scale", "aws", "network", "kubernetes", "docker", "security", "encryption", "devops", "deploy", "postgres", "mysql", "redis", "mongodb"],
        "hardware": ["hardware", "chip", "cpu", "gpu", "nvidia", "intel", "amd", "processor", "silicon", "semiconductor", "circuit", "transistor", "motherboard", "tpu", "ram"],
        "device": ["phone", "laptop", "device", "iphone", "android", "mobile", "screen", "monitor", "tablet", "watch", "hardware", "gadget"],
        "workspace": ["workspace", "office", "team", "design", "ux", "ui", "remote", "desk", "work", "collaboration", "startup", "management", "agile", "product", "saas"],
        "abstract": ["ai", "model", "llm", "neural", "learning", "intelligence", "quantum", "future", "concept", "algorithm", "theory", "math", "gpt", "gemini", "claude", "meta", "openai", "copilot"]
    }
    
    matched_themes = []
    for theme, keywords in keyword_map.items():
        if any(kw in text for kw in keywords):
            matched_themes.append(theme)
            
    best_image = None
    best_score = -9999
    
    for candidate in FALLBACK_IMAGES_REGISTRY:
        url = candidate["url"]
        
        # 1. Similarity check / Image Similarity Detection
        similarity_penalty = 0
        if url in recent_urls[:5]:
            similarity_penalty = -100
        elif url in recent_urls:
            similarity_penalty = -50
            
        # 2. Visual Variety Score & Topic Diversity Score
        theme_count = recent_themes.get(candidate["theme"], 0)
        color_count = recent_colors.get(candidate["color"], 0)
        style_count = recent_styles.get(candidate["style"], 0)
        
        variety_penalty = (theme_count * 15) + (color_count * 10) + (style_count * 10)
        
        # 3. Relevance Bonus
        relevance_bonus = 0
        if candidate["theme"] in matched_themes:
            relevance_bonus = 40  # strong boost for matching the article's topic keywords
            
        jitter = random.uniform(0, 5)
        
        score = relevance_bonus - variety_penalty + similarity_penalty + jitter
        if score > best_score:
            best_score = score
            best_image = url
            
    return best_image or FALLBACK_IMAGES_REGISTRY[0]["url"]


def get_clean_fallback_caption(title: str, content: str, recent_posts: list) -> str:
    """
    Generates a structured, professional tech caption of exactly 20-25 words.
    Structure: Hook -> Insight -> CTA.
    Guarantees no duplicate captions or hooks against recent posts.
    """
    topic = title.split(" - ")[0].split(" | ")[0].strip()
    if topic.endswith(".") or topic.endswith("?"):
        topic = topic[:-1]
    
    topic_words = topic.split()
    if len(topic_words) > 6:
        topic = " ".join(topic_words[:5])
        
    hooks = [
        f"{topic} is redefining how teams build software.",
        f"The rapid evolution of {topic} is accelerating industry trends.",
        f"A new milestone for {topic} has officially been reached.",
        f"Recent developments in {topic} are turning heads across tech.",
        f"Significant updates to {topic} promise to streamline engineering workflows.",
        f"Understanding {topic} is now essential for modern product teams.",
        f"New reports on {topic} indicate major industry restructuring ahead.",
        f"Key shifts in {topic} are creating fresh opportunities globally.",
        f"Deploying {topic} allows organizations to optimize resource usage.",
        f"The architecture behind {topic} offers major scalability improvements."
    ]
    
    insights = [
        "Adopting these tools early provides a strong competitive edge.",
        "Automating key processes helps teams minimize overhead and deploy faster.",
        "Focusing on developer efficiency is critical for modern software groups.",
        "Integrating this technology helps systems scale with minimal maintenance.",
        "This shift forces engineering leads to rethink existing system design.",
        "Teams prioritizing this integration report much higher delivery speeds.",
        "Mitigating these technical risks secures better long-term system stability.",
        "Leveraging structured frameworks makes scaling operations simpler and cleaner.",
        "Standardizing these pipelines ensures consistent results under peak load.",
        "Improving codebase flexibility allows for rapid adaptation to future changes."
    ]
    
    ctas = [
        "What's your plan for this?",
        "Will you adopt this tool?",
        "Ready to implement this next?",
        "What are your key thoughts?",
        "How will this impact you?",
        "Is your stack ready yet?",
        "What are your core concerns?",
        "Would you try this today?",
        "How does this affect you?",
        "What is your next project?"
    ]
    
    # Extract first sentences (hooks) and full captions of recent posts to avoid duplication
    recent_captions = [p.caption for p in recent_posts if p.caption]
    recent_hooks = []
    for cap in recent_captions:
        parts = re.split(r'(?<=[.!?])\s+', cap)
        if parts:
            recent_hooks.append(parts[0])

    # Filter candidate hooks and insights to ensure diversity
    available_hooks = [h for h in hooks if h not in recent_hooks]
    if not available_hooks:
        available_hooks = hooks
        
    available_insights = insights
    
    # Try combinations
    for _ in range(300):
        h = random.choice(available_hooks)
        i = random.choice(available_insights)
        c = random.choice(ctas)
        combined = f"{h} {i} {c}"
        if combined in recent_captions:
            continue
        word_count = len(combined.split())
        if 20 <= word_count <= 25:
            return combined
            
    # Default fallback construct if search fails
    h = available_hooks[0]
    i = available_insights[0]
    c = ctas[0]
    combined = f"{h} {i} {c}"
    words = combined.split()
    
    if len(words) < 20:
        padding = ["now", "today", "efficiently", "seamlessly", "securely", "at scale"]
        while len(words) < 22:
            words.insert(-2, random.choice(padding))
    elif len(words) > 25:
        words = words[:23] + [words[-1]]
        
    return " ".join(words)


class AutomationPipeline:
    def __init__(self):
        self.status = "idle"
        self.last_run = None
        self.last_error = None

    async def run_generation(self, db: Session, limit: int = 4, source: str = "AUTO", bypass_cooldown: bool = False) -> int:
        """
        Runs the content generation pipeline.
        Enforces inventory thresholds (min 12 posts) to optimize AI credits.
        Generates posts in a single batch call.
        """
        # Fast connection check to Ollama
        await ai_service.check_online()

        # Prevent overlapping runs
        fifteen_minutes_ago = datetime.utcnow() - timedelta(minutes=15)
        overlapping_run = db.query(GenerationRun).filter(
            GenerationRun.status == "running",
            GenerationRun.started_at > fifteen_minutes_ago
        ).first()

        if overlapping_run:
            logger.warning("Pipeline run skipped: An overlapping run is already active.")
            return 0

        # Cooldown check: prevent runs within 5 minutes of a successfully completed run (only for AUTO source)
        if source == "AUTO" and not bypass_cooldown:
            five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
            recent_completed_run = db.query(GenerationRun).filter(
                GenerationRun.status == "completed",
                GenerationRun.source == "AUTO",
                GenerationRun.completed_at > five_minutes_ago
            ).first()
            if recent_completed_run:
                logger.warning("Pipeline run skipped: Cooldown active (last completed run was less than 5 minutes ago).")
                return 0

        # Check inventory threshold (DRAFT + QUEUED + PUBLISHING + FAILED)
        available_posts = db.query(Post).filter(
            Post.status.in_(["DRAFT", "QUEUED", "PUBLISHING", "FAILED"])
        ).count()
        
        # Min inventory threshold is 12 posts
        if available_posts >= 12:
            logger.info(f"Inventory threshold satisfied (have {available_posts} posts >= 12). Skipping AI generation.")
            # Record skipped run
            skipped_run = GenerationRun(
                source=source,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                status="skipped",
                generated_count=0
            )
            db.add(skipped_run)
            db.add(ActivityLog(
                action="skip_generation",
                entity_type="system",
                entity_id=None
            ))
            db.commit()
            return 0
            
        needed = 12 - available_posts
        actual_limit = min(limit, needed)
        logger.info(f"Inventory is {available_posts}/12 posts. Generating {actual_limit} missing posts.")

        # Log run start
        run_log = GenerationRun(
            source=source,
            started_at=datetime.utcnow(),
            status="running",
            generated_count=0
        )
        db.add(run_log)
        db.commit()

        self.status = "running"
        self.last_error = None
        generated_count = 0

        try:
            # 1. Fetch News
            news_items = await collector.collect_all()
            news_repo.save_news_items(db, news_items)
            
            # 2. Rank News
            await ranking_engine.process_new_stories(db)
            
            # 3. Select top stories that haven't been processed into posts (with similarity/duplicate check)
            existing_post_news_ids = db.query(Post.news_id).filter(Post.news_id.isnot(None))
            rejected_news_ids = db.query(Post.news_id).filter(
                Post.status == "REJECTED",
                Post.news_id.isnot(None)
            )

            query = db.query(News).filter(
                News.processed == True,
                News.id.notin_(existing_post_news_ids),
                News.id.notin_(rejected_news_ids)
            )
            
            candidate_stories = query.order_by(News.importance_score.desc(), News.created_at.desc()).limit(actual_limit * 3).all()
            
            from difflib import SequenceMatcher
            def is_similar(title1: str, title2: str, threshold: float = 0.6) -> bool:
                return SequenceMatcher(None, title1.lower(), title2.lower()).ratio() >= threshold

            # Fetch existing posts from the last 7 days to compare titles
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            recent_posts_db = db.query(Post).filter(Post.created_at > seven_days_ago).all()
            recent_titles = [p.title for p in recent_posts_db if p.title]
            
            top_stories = []
            for story in candidate_stories:
                if len(top_stories) >= actual_limit:
                    break
                    
                is_duplicate = False
                for existing_title in recent_titles:
                    if is_similar(story.title, existing_title, 0.6):
                        logger.info(f"Duplicate/Similarity check: Skipping '{story.title}' (similar to recent post: '{existing_title}')")
                        is_duplicate = True
                        break
                if is_duplicate:
                    continue
                    
                for selected in top_stories:
                    if is_similar(story.title, selected.title, 0.6):
                        logger.info(f"Duplicate/Similarity check: Skipping '{story.title}' (similar to another story in this batch)")
                        is_duplicate = True
                        break
                if is_duplicate:
                    continue
                    
                top_stories.append(story)
            
            if not top_stories:
                logger.warning("No top stories found after ranking.")
                run_log.completed_at = datetime.utcnow()
                run_log.status = "completed"
                db.commit()
                self.status = "idle"
                return 0
                
            # Compile stories data for batch AI request
            stories_data = [{"id": s.id, "title": s.title, "content": s.content} for s in top_stories]
            
            # 4. Call batch AI generation (1 call for all posts to save credits!)
            try:
                logger.info(f"AI: Calling batch generation for {len(stories_data)} stories")
                ai_posts = await asyncio.wait_for(
                    ai_service.generate_batch_posts(stories_data),
                    timeout=30.0
                )
            except Exception as e:
                logger.error(f"Batch AI Content Gen failed: {e}")
                ai_posts = []

            # Map the generated AI posts by news_id
            ai_posts_by_id = {p.get("news_id"): p for p in ai_posts if p.get("news_id")}
            
            # Query recent 20 posts from DB for diversity comparisons
            recent_posts = db.query(Post).order_by(Post.created_at.desc()).limit(20).all()
            recent_urls = [p.image_url for p in recent_posts if p.image_url]

            for story in top_stories:
                content = ai_posts_by_id.get(story.id)
                
                # Fallback content if AI failed to return this story
                if not content:
                    logger.info(f"Using fallback content for story {story.id}")
                    fallback_caption = get_clean_fallback_caption(story.title, story.content, recent_posts)
                    content = {
                        "headline": story.title[:100],
                        "caption": fallback_caption,
                        "hashtags": ["#Tech", "#News", f"#{story.source.replace(' ', '')}"]
                    }
                
                # 5. Extract Image
                try:
                    img_url = await asyncio.wait_for(
                        scraper_service.extract_og_image(story.url),
                        timeout=10.0
                    )
                except:
                    img_url = None
                
                # Check if scraped image is generic or duplicate
                is_scraped_invalid = False
                if img_url:
                    if any(x in img_url.lower() for x in ["logo", "favicon", "avatar", "brand", "social-default"]):
                        is_scraped_invalid = True
                    elif img_url in recent_urls:
                        is_scraped_invalid = True
                        
                final_image_url = img_url if (img_url and not is_scraped_invalid) else select_relevant_fallback_image(story.title, story.content, recent_posts)

                # Create Post record
                post = Post(
                    news_id=story.id,
                    title=content.get("headline", story.title[:100]),
                    caption=content.get("caption"),
                    template="default",
                    generation_source=source,
                    image_url=final_image_url,
                    status="DRAFT"
                )
                db.add(post)
                db.commit()
                generated_count += 1
                
                # Update recent_posts list in-memory so subsequent iterations in this run
                # avoid selecting the same image.
                recent_posts.insert(0, post)
                recent_urls.insert(0, final_image_url)
                
                # 6. Generate Social Card
                try:
                    if post.image_url:
                        img = await image_service.download_image(post.image_url)
                        if img:
                            image_service.generate_card(img, post.title, post.caption, str(post.id))
                except Exception as e:
                    logger.error(f"Card generation failed: {e}")
            
            # Log successful completion
            run_log.completed_at = datetime.utcnow()
            run_log.status = "completed"
            run_log.generated_count = generated_count
            db.commit()
            
            db.add(ActivityLog(
                action="generate",
                entity_type="generation_run",
                entity_id=run_log.id
            ))
            db.commit()
            
            self.last_run = run_log.completed_at.isoformat()
            logger.info(f"Pipeline completed. Generated {generated_count} posts.")
            
        except Exception as e:
            db.rollback()
            self.last_error = str(e)
            run_log.completed_at = datetime.utcnow()
            run_log.status = "failed"
            db.commit()
            logger.error(f"Pipeline failed: {e}")
        finally:
            self.status = "idle"
            
        return generated_count

    async def run_cleanup(self, db: Session) -> dict:
        """
        Cleanup old rejected posts, logs, and generated assets older than 10 days.
        """
        logger.info("Starting database and asset cleanup...")
        ten_days_ago = datetime.utcnow() - timedelta(days=10)
        
        # 1. Fetch posts older than 10 days with status REJECTED
        rejected_posts = db.query(Post).filter(
            Post.status == "REJECTED",
            Post.created_at < ten_days_ago
        ).all()
        
        deleted_posts_count = 0
        deleted_assets_count = 0
        
        for post in rejected_posts:
            # Delete corresponding generated card image
            card_path = os.path.join(image_service.output_dir, f"{post.id}.png")
            if os.path.exists(card_path):
                try:
                    os.remove(card_path)
                    deleted_assets_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete asset {card_path}: {e}")
            
            db.delete(post)
            deleted_posts_count += 1
            
        # 2. Delete old logs
        deleted_publish_logs = db.query(PublishLog).filter(PublishLog.created_at < ten_days_ago).delete()
        deleted_activity_logs = db.query(ActivityLog).filter(ActivityLog.created_at < ten_days_ago).delete()
        
        db.commit()
        
        # Log cleanup run
        db.add(ActivityLog(
            action="clean",
            entity_type="system",
            entity_id=None
        ))
        db.commit()
        
        result = {
            "deleted_posts": deleted_posts_count,
            "deleted_assets": deleted_assets_count,
            "deleted_publish_logs": deleted_publish_logs,
            "deleted_activity_logs": deleted_activity_logs
        }
        logger.info(f"Cleanup finished: {result}")
        return result

pipeline = AutomationPipeline()
