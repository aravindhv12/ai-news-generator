from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.repository.news_repo import news_repo
from app.services.ai_service import ai_service
from app.models.models import Post
import asyncio
import logging

logger = logging.getLogger(__name__)

class RankingEngine:
    async def process_new_stories(self, db: Session):
        unprocessed = news_repo.get_unprocessed_news(db, limit=10)
        logger.info(f"Ranking {len(unprocessed)} stories")
        
        semaphore = asyncio.Semaphore(3) # Limit concurrency to 3 to avoid overloading Ollama
        
        async def rank_story(item):
            async with semaphore:
                try:
                    # Limit Ollama call to 10s to prevent hanging
                    score = await asyncio.wait_for(
                        ai_service.rank_news(item.title, item.content or ""),
                        timeout=10.0
                    )
                    item.importance_score = score
                except Exception as e:
                    logger.warning(f"Failed to rank story {item.id}, using default: {e}")
                    item.importance_score = 5.0
                item.processed = True
                try:
                    db.commit()
                except Exception as e:
                    db.rollback()
                    logger.error(f"Failed to commit rank for news story {item.id}: {e}")

        await asyncio.gather(*(rank_story(item) for item in unprocessed))
    
    async def select_top_stories(self, db: Session, limit: int = 4):
        from app.models.models import News
        # Get processed news that haven't been made into posts yet
        query = db.query(News).outerjoin(Post).filter(
            News.processed == True,
            Post.id == None
        )
        # Order by score, but fallback to date to ensure content always flows
        top_news = query.order_by(News.importance_score.desc(), News.created_at.desc()).limit(limit).all()
        
        return top_news

ranking_engine = RankingEngine()
