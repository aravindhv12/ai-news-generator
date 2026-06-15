from app.db.session import SessionLocal
from app.models.models import News, Post

def check():
    db = SessionLocal()
    news_count = db.query(News).count()
    posts_count = db.query(Post).count()
    print(f"News count: {news_count}")
    print(f"Posts count: {posts_count}")
    
    if news_count > 0:
        latest_news = db.query(News).order_by(News.created_at.desc()).first()
        print(f"Latest news: {latest_news.title} (Source: {latest_news.source})")
        
    db.close()

if __name__ == "__main__":
    check()
