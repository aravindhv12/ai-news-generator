from sqlalchemy import Column, String, Text, DateTime, Float, Boolean, ForeignKey, Integer, Index
from sqlalchemy.orm import declarative_base, relationship
import uuid
from datetime import datetime

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

class News(Base):
    __tablename__ = "news"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String, nullable=False)
    url = Column(String, unique=True, nullable=False, index=True)
    source = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    published_at = Column(DateTime, default=datetime.utcnow)
    importance_score = Column(Float, default=0.0)
    processed = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post", back_populates="news", uselist=False)

class Post(Base):
    __tablename__ = "posts"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    news_id = Column(String, ForeignKey("news.id"), nullable=True)
    title = Column(String, nullable=False) # e.g. headline
    caption = Column(Text, nullable=True) # e.g. summary/caption
    template = Column(String, nullable=True, default="default")
    status = Column(String, default="DRAFT", index=True) # DRAFT, APPROVED, REJECTED, QUEUED, PUBLISHING, PUBLISHED, FAILED
    generation_source = Column(String, default="MANUAL", index=True) # AUTO, MANUAL
    image_url = Column(String, nullable=True)
    hashtags = Column(String, nullable=True)
    approved_by = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)

    news = relationship("News", back_populates="post")
    queue_entries = relationship("PublishQueue", back_populates="post", cascade="all, delete-orphan")
    logs = relationship("PublishLog", back_populates="post", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_posts_status_created", "status", "created_at"),
    )

class GenerationRun(Base):
    __tablename__ = "generation_runs"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    source = Column(String, nullable=False) # AUTO, MANUAL
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="running") # running, completed, failed
    generated_count = Column(Integer, default=0)

class PublishQueue(Base):
    __tablename__ = "publish_queue"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    post_id = Column(String, ForeignKey("posts.id"), nullable=False)
    status = Column(String, default="queued") # queued, publishing, published, failed
    attempt_count = Column(Integer, default=0)
    queued_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)

    post = relationship("Post", back_populates="queue_entries")

class PublishLog(Base):
    __tablename__ = "publish_logs"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    post_id = Column(String, ForeignKey("posts.id"), nullable=True)
    message = Column(Text, nullable=False)
    level = Column(String, default="info") # info, warning, error
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post", back_populates="logs")

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    action = Column(String, nullable=False) # e.g. approve, reject, generate, clean
    entity_type = Column(String, nullable=False) # e.g. post, generation_run
    entity_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class SystemSetting(Base):
    __tablename__ = "system_settings"
    
    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)

