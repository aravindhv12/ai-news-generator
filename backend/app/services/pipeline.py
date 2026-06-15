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

logger = logging.getLogger(__name__)

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
            
            for story in top_stories:
                content = ai_posts_by_id.get(story.id)
                
                # Fallback content if AI failed to return this story
                if not content:
                    logger.info(f"Using fallback content for story {story.id}")
                    content = {
                        "headline": story.title[:100],
                        "caption": (story.content[:150] + "..." if story.content else "Latest technology news update. Read more details here."),
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
                
                # Create Post record
                post = Post(
                    news_id=story.id,
                    title=content.get("headline", story.title[:100]),
                    caption=content.get("caption"),
                    template="default",
                    generation_source=source,
                    image_url=img_url or "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=800",
                    status="DRAFT"
                )
                db.add(post)
                db.commit()
                generated_count += 1
                
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
            card_path = f"output/{post.id}.png"
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
