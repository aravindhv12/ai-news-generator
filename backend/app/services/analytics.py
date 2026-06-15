from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.models import Post, PublishLog, News, PublishQueue
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class AnalyticsService:
    def get_dashboard_stats(self, db: Session):
        total_news = db.query(News).count()
        total_posts = db.query(Post).count()
        published_posts = db.query(Post).filter(Post.status == "PUBLISHED").count()
        pending_approval = db.query(Post).filter(Post.status == "DRAFT").count()
        
        # Success rate from queue
        total_attempts = db.query(PublishQueue).filter(PublishQueue.status.in_(["published", "failed"])).count()
        success_attempts = db.query(PublishQueue).filter(PublishQueue.status == "published").count()
        success_rate = (success_attempts / total_attempts * 100) if total_attempts > 0 else 0.0
        
        return {
            "total_news": total_news,
            "total_posts": total_posts,
            "published_posts": published_posts,
            "pending_approval": pending_approval,
            "success_rate": round(success_rate, 2)
        }

    def get_source_statistics(self, db: Session):
        stats = db.query(
            News.source, 
            func.count(News.id).label("count")
        ).group_by(News.source).all()
        
        return {s.source: s.count for s in stats}

analytics_service = AnalyticsService()
