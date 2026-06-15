from sqlalchemy.orm import Session
from app.models.models import News
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class NewsRepository:
    def save_news_items(self, db: Session, items: List[Dict]):
        saved_count = 0
        seen_urls = set()
        for item in items:
            url = item.get("url")
            if not url:
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            # Check for existing URL to avoid duplicates
            existing = db.query(News).filter(News.url == url).first()
            if not existing:
                new_item = News(
                    title=item["title"],
                    url=url,
                    source=item["source"],
                    content=item["content"][:2000] if item["content"] else "", # Truncate for safety
                    published_at=item["published_at"]
                )
                db.add(new_item)
                saved_count += 1
        
        if saved_count > 0:
            try:
                db.commit()
                logger.info(f"Successfully saved {saved_count} new stories to database in batch.")
            except Exception as e:
                db.rollback()
                logger.error(f"Error committing news batch: {e}. Retrying individually...")
                
                # Retry individual inserts to save whatever valid stories we can
                saved_count = 0
                for item in items:
                    url = item.get("url")
                    if not url:
                        continue
                    existing = db.query(News).filter(News.url == url).first()
                    if not existing:
                        try:
                            new_item = News(
                                title=item["title"],
                                url=url,
                                source=item["source"],
                                content=item["content"][:2000] if item["content"] else "",
                                published_at=item["published_at"]
                            )
                            db.add(new_item)
                            db.commit()
                            saved_count += 1
                        except Exception as inner_e:
                            db.rollback()
                            logger.error(f"Failed to save item individually {url}: {inner_e}")
                logger.info(f"Successfully saved {saved_count} new stories to database via individual commits.")
            
    def get_unprocessed_news(self, db: Session, limit: int = 50) -> List[News]:
        return db.query(News).filter(News.processed == False).limit(limit).all()

news_repo = NewsRepository()
