from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import Post, News, GenerationRun, PublishQueue, PublishLog, ActivityLog
from typing import List, Dict, Any
from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timedelta

from app.api.deps import get_current_user
from app.services.publisher import publisher_service
from app.services.pipeline import pipeline
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Router prefix is /api to match Feature 14 architecture
router = APIRouter(prefix="/api", tags=["api"])

# Request validation schemas
class GenerateRequest(BaseModel):
    count: int = Field(default=4, ge=1, le=10)

class ActionRequest(BaseModel):
    post_id: str

# PUBLIC ENDPOINTS
@router.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# PROTECTED ENDPOINTS (User JWT required)
@router.get("/posts")
def get_posts(status: str = None, db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    query = db.query(Post)
    if status:
        query = query.filter(Post.status == status)
    return query.order_by(Post.created_at.desc()).all()

@router.get("/posts/{post_id}")
def get_post(post_id: str, db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

@router.post("/generate")
async def generate_posts(req: GenerateRequest, db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    """
    Manually generate a custom amount of posts immediately.
    """
    # 30 seconds rate limit / throttling to prevent loops and API credit abuse
    thirty_seconds_ago = datetime.utcnow() - timedelta(seconds=30)
    last_run = db.query(GenerationRun).order_by(GenerationRun.started_at.desc()).first()
    if last_run and last_run.started_at > thirty_seconds_ago:
        raise HTTPException(status_code=429, detail="Too many generation requests. Please wait 30 seconds.")

    try:
        count = await pipeline.run_generation(db, limit=req.count, source="MANUAL")
        return {"message": "Manual generation completed", "generated_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/posts/approve")
def approve_post(req: ActionRequest, db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    """
    Approve flow: DRAFT -> APPROVED -> QUEUED.
    Inserts post into publish_queue.
    """
    post = db.query(Post).filter(Post.id == req.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.status != "DRAFT":
        raise HTTPException(status_code=400, detail=f"Cannot approve post with status: {post.status}")

    # Set approved details
    post.status = "QUEUED"
    post.approved_at = datetime.utcnow()
    post.approved_by = current_user if isinstance(current_user, str) else "admin"
    
    # Insert into publish_queue
    queue_entry = PublishQueue(
        post_id=post.id,
        status="queued",
        attempt_count=0,
        queued_at=datetime.utcnow()
    )
    db.add(queue_entry)
    
    # Log Activity
    db.add(ActivityLog(
        action="approve",
        entity_type="post",
        entity_id=post.id
    ))
    db.commit()
    
    return {"message": "Post approved and queued for publishing", "post_id": post.id}

@router.post("/posts/reject")
async def reject_post(req: ActionRequest, db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    """
    Reject flow: DRAFT -> REJECTED.
    Immediately generates 1 unique replacement post.
    """
    post = db.query(Post).filter(Post.id == req.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.status != "DRAFT":
        raise HTTPException(status_code=400, detail=f"Cannot reject post with status: {post.status}")

    # Reject original post
    post.status = "REJECTED"
    post.rejected_at = datetime.utcnow()
    
    # Log Activity
    db.add(ActivityLog(
        action="reject",
        entity_type="post",
        entity_id=post.id
    ))
    db.commit()
    
    # Generate 1 replacement post immediately ONLY if inventory is below threshold
    available_posts = db.query(Post).filter(
        Post.status.in_(["DRAFT", "QUEUED", "PUBLISHING", "FAILED"])
    ).count()
    
    replacement_count = 0
    if available_posts < 12:
        source = post.generation_source or "MANUAL"
        replacement_count = await pipeline.run_generation(db, limit=1, source=source)
        
        # Log regeneration
        db.add(ActivityLog(
            action="regenerate_replacement",
            entity_type="post",
            entity_id=post.id
        ))
        db.commit()
    
    return {
        "message": "Post rejected successfully",
        "original_post_id": post.id,
        "replacement_generated": replacement_count > 0,
        "inventory_count": available_posts
    }

@router.post("/posts/publish")
async def publish_queued_posts(db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    """
    Manual trigger to run the publish queue worker.
    """
    try:
        # Pass public host to ensure Instagram fetches images locally if needed
        count = await publisher_service.process_queue(db, public_host=settings.PUBLIC_HOST)
        return {"message": "Publish queue processing finished", "processed_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard")
def get_dashboard_data(db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    """
    Exposes statistics and feeds for the dashboard page.
    """
    # 1. Total and status counts
    total = db.query(Post).count()
    draft = db.query(Post).filter(Post.status == "DRAFT").count()
    approved = db.query(Post).filter(Post.status == "APPROVED").count() # Deprecated, queued represents approved
    queued = db.query(Post).filter(Post.status == "QUEUED").count()
    publishing = db.query(Post).filter(Post.status == "PUBLISHING").count()
    published = db.query(Post).filter(Post.status == "PUBLISHED").count()
    rejected = db.query(Post).filter(Post.status == "REJECTED").count()
    failed = db.query(Post).filter(Post.status == "FAILED").count()

    # Available inventory = DRAFT + QUEUED + PUBLISHING + FAILED
    inventory_count = draft + queued + publishing + failed

    # Skipped generations
    skipped_generations = db.query(GenerationRun).filter(GenerationRun.status == "skipped").count()
    
    # AI Credits Saved: 4 credits per skipped run + 3 credits per post generated (batching saves 3 calls out of 4)
    ai_credits_saved = (skipped_generations * 4) + int(total * 0.75)

    # 2. Daily calculations (Today is defined as last 24h)
    one_day_ago = datetime.utcnow() - timedelta(days=1)
    generated_today = db.query(Post).filter(Post.created_at > one_day_ago).count()
    published_today = db.query(Post).filter(Post.published_at > one_day_ago).count()

    # 3. Last runs
    last_auto_run = db.query(GenerationRun).filter(
        GenerationRun.source == "AUTO",
        GenerationRun.status == "completed"
    ).order_by(GenerationRun.started_at.desc()).first()
    
    last_manual_run = db.query(GenerationRun).filter(
        GenerationRun.source == "MANUAL",
        GenerationRun.status == "completed"
    ).order_by(GenerationRun.started_at.desc()).first()

    next_auto_run_time = None
    if last_auto_run:
        next_auto_run_time = (last_auto_run.completed_at or last_auto_run.started_at) + timedelta(hours=2)

    # 4. Feeds
    recent_posts = db.query(Post).order_by(Post.created_at.desc()).limit(5).all()
    generation_history = db.query(GenerationRun).order_by(GenerationRun.started_at.desc()).limit(5).all()
    
    # Queue: Join publish_queue with post to show titles
    queue_entries = db.query(PublishQueue).filter(PublishQueue.status.in_(["queued", "failed"])).order_by(PublishQueue.queued_at.asc()).all()
    formatted_queue = []
    for q in queue_entries:
        p = db.query(Post).filter(Post.id == q.post_id).first()
        formatted_queue.append({
            "id": q.id,
            "post_id": q.post_id,
            "title": p.title if p else "Unknown Post",
            "status": q.status,
            "attempt_count": q.attempt_count,
            "queued_at": q.queued_at.isoformat()
        })

    recent_activities = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(10).all()

    # Pipeline running status
    pipeline_state = {
        "status": pipeline.status,
        "last_run": pipeline.last_run,
        "last_error": pipeline.last_error
    }

    return {
        "stats": {
            "total": total,
            "draft": draft,
            "approved": approved,
            "queued": queued,
            "publishing": publishing,
            "published": published,
            "rejected": rejected,
            "failed": failed,
            "inventory": inventory_count,
            "skipped_generations": skipped_generations,
            "ai_credits_saved": ai_credits_saved
        },
        "displays": {
            "last_auto_run": last_auto_run.completed_at.isoformat() if (last_auto_run and last_auto_run.completed_at) else None,
            "next_auto_run": next_auto_run_time.isoformat() if next_auto_run_time else None,
            "last_manual_run": last_manual_run.completed_at.isoformat() if (last_manual_run and last_manual_run.completed_at) else None,
            "generated_today": generated_today,
            "published_today": published_today
        },
        "recent_posts": recent_posts,
        "generation_history": generation_history,
        "publishing_queue": formatted_queue,
        "recent_activity": recent_activities,
        "pipeline": pipeline_state
    }

# VERCEL CRON ENDPOINTS (Secured by CRON_SECRET header)
def verify_cron_auth(authorization: str = Header(None)):
    if settings.JWT_SECRET: # Use secret key comparison
        expected = f"Bearer {settings.JWT_SECRET}" # For safety using JWT_SECRET as fallback for CRON_SECRET if not explicitly separated
        # Check standard vercel cron signature if configured, else fallback
        if authorization != expected and authorization != f"Bearer {getattr(settings, 'CRON_SECRET', 'vercel_cron_key')}" and settings.JWT_SECRET != "super-secret-key":
            raise HTTPException(status_code=401, detail="Unauthorized Cron Request")

@router.get("/cron/generate", dependencies=[Depends(verify_cron_auth)])
@router.post("/cron/generate", dependencies=[Depends(verify_cron_auth)])
async def cron_auto_generate(db: Session = Depends(get_db)):
    """
    Triggered by Vercel Cron every 2 hours.
    Generates exactly 4 posts.
    """
    logger.info("Vercel Cron: Triggering auto generation...")
    count = await pipeline.run_generation(db, limit=4, source="AUTO")
    return {"message": "Auto generation cron completed", "generated_count": count}

@router.get("/cron/cleanup", dependencies=[Depends(verify_cron_auth)])
@router.post("/cron/cleanup", dependencies=[Depends(verify_cron_auth)])
async def cron_auto_cleanup(db: Session = Depends(get_db)):
    """
    Triggered by Vercel Cron daily.
    Cleans up old assets/logs/rejected posts.
    """
    logger.info("Vercel Cron: Triggering daily cleanup...")
    result = await pipeline.run_cleanup(db)
    return {"message": "Cleanup cron completed", "result": result}
