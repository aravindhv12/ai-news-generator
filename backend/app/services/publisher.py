import httpx
import logging
from sqlalchemy.orm import Session
from app.models.models import Post, PublishQueue, PublishLog, ActivityLog
from app.core.config import settings
from datetime import datetime
import asyncio
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BasePublisher(ABC):
    @abstractmethod
    async def publish(self, post: Post, image_url: str) -> tuple[bool, str | None, str | None]:
        """
        Returns (success, external_id, error_message)
        """
        pass

class InstagramPublisher(BasePublisher):
    def __init__(self):
        self.access_token = getattr(settings, "INSTAGRAM_ACCESS_TOKEN", None)
        self.ig_user_id = getattr(settings, "INSTAGRAM_BUSINESS_ID", None)
        self.base_url = "https://graph.facebook.com/v19.0"

    async def publish(self, post: Post, image_url: str) -> tuple[bool, str | None, str | None]:
        # If credentials are not set, act as a pluggable mock provider in dev/test environment
        if not self.access_token or not self.ig_user_id:
            logger.warning("Instagram credentials missing. Running mock publishing.")
            # Simulate slight delay
            await asyncio.sleep(1)
            # Mock success unless specified in caption for test cases
            if "fail" in (post.caption or "").lower():
                return False, None, "Mock publish simulated error"
            return True, f"mock_ig_{int(datetime.utcnow().timestamp())}", None

        try:
            async with httpx.AsyncClient() as client:
                # 1. Create Media Container
                logger.info("Instagram: Creating media container")
                container_resp = await client.post(
                    f"{self.base_url}/{self.ig_user_id}/media",
                    params={
                        "image_url": image_url,
                        "caption": f"{post.title}\n\n{post.caption}\n\n{post.hashtags or ''}",
                        "access_token": self.access_token
                    }
                )
                container_data = container_resp.json()
                if "id" not in container_data:
                    return False, None, f"Container creation failed: {container_data}"
                
                container_id = container_data["id"]

                # 2. Wait for container to be ready
                await asyncio.sleep(5) 

                # 3. Publish Media
                logger.info(f"Instagram: Publishing container {container_id}")
                publish_resp = await client.post(
                    f"{self.base_url}/{self.ig_user_id}/media_publish",
                    params={
                        "creation_id": container_id,
                        "access_token": self.access_token
                    }
                )
                publish_data = publish_resp.json()
                if "id" not in publish_data:
                    return False, None, f"Publishing failed: {publish_data}"
                
                return True, publish_data["id"], None

        except Exception as e:
            logger.error(f"Instagram API Error: {e}")
            return False, None, str(e)

class PublisherService:
    def __init__(self, provider: BasePublisher = None):
        self.provider = provider or InstagramPublisher()

    async def process_queue(self, db: Session, public_host: str = None) -> int:
        """
        Processes pending items in the publish queue.
        """
        # Find queued or failed posts that haven't exceeded retry limit (max 3 attempts)
        queue_items = db.query(PublishQueue).filter(
            PublishQueue.status.in_(["queued", "failed"]),
            PublishQueue.attempt_count < 3
        ).order_by(PublishQueue.queued_at.asc()).all()

        processed_count = 0
        for item in queue_items:
            post = db.query(Post).filter(Post.id == item.post_id).first()
            if not post:
                continue

            processed_count += 1
            item.status = "publishing"
            post.status = "PUBLISHING"
            item.attempt_count += 1
            db.commit()

            image_url = f"{public_host}/output/{post.id}.png" if public_host else post.image_url
            
            logger.info(f"Publishing post {post.id} (Attempt {item.attempt_count})...")
            
            # Write start publishing log
            db.add(PublishLog(
                post_id=post.id,
                message=f"Starting publish attempt {item.attempt_count} for post: {post.title}",
                level="info"
            ))
            
            success, ext_id, error = await self.provider.publish(post, image_url)
            
            if success:
                item.status = "published"
                item.published_at = datetime.utcnow()
                
                post.status = "PUBLISHED"
                post.published_at = datetime.utcnow()
                
                db.add(PublishLog(
                    post_id=post.id,
                    message=f"Successfully published to Instagram. External ID: {ext_id}",
                    level="info"
                ))
                db.add(ActivityLog(
                    action="publish",
                    entity_type="post",
                    entity_id=post.id
                ))
            else:
                item.status = "failed"
                post.status = "FAILED"
                
                db.add(PublishLog(
                    post_id=post.id,
                    message=f"Publishing failed: {error}",
                    level="error"
                ))
            
            db.commit()
            
        return processed_count

publisher_service = PublisherService()
