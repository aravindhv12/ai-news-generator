from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.orm import Session
from app.db.session import get_db, SessionLocal
from app.models.models import Post, News, GenerationRun, PublishQueue, PublishLog, ActivityLog, SystemSetting
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timedelta

import os

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

class SettingsUpdateRequest(BaseModel):
    PROJECT_NAME: Optional[str] = None
    OLLAMA_BASE_URL: Optional[str] = None
    OLLAMA_MODEL: Optional[str] = None
    INSTAGRAM_ACCESS_TOKEN: Optional[str] = None
    INSTAGRAM_BUSINESS_ID: Optional[str] = None
    PUBLIC_HOST: Optional[str] = None
    CRON_SECRET: Optional[str] = None

# Background Task helpers
async def bg_run_generation(limit: int, source: str):
    db = SessionLocal()
    try:
        await pipeline.run_generation(db, limit=limit, source=source)
    except Exception as e:
        logger.error(f"Background run_generation failed: {e}")
    finally:
        db.close()

async def bg_reject_replacement(post_id: str, source: str):
    db = SessionLocal()
    try:
        await pipeline.run_generation(db, limit=1, source=source)
        db.add(ActivityLog(
            action="regenerate_replacement",
            entity_type="post",
            entity_id=post_id
        ))
        db.commit()
    except Exception as e:
        logger.error(f"Background reject_replacement failed: {e}")
    finally:
        db.close()


# PUBLIC ENDPOINTS
@router.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# PROTECTED ENDPOINTS (User JWT required)
@router.get("/posts")
def get_posts(status: str = None, limit: int = 100, db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    query = db.query(Post)
    if status:
        query = query.filter(Post.status == status)
    return query.order_by(Post.created_at.desc()).limit(limit).all()

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

    pipeline.status = "running"
    try:
        count = await pipeline.run_generation(db, limit=req.count, source="MANUAL", bypass_cooldown=True)
        return {"message": "Manual generation completed", "generated_count": count}
    except Exception as e:
        logger.error(f"Manual generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pipeline.status = "idle"

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
async def reject_post(req: ActionRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    """
    Reject flow: DRAFT -> REJECTED.
    Immediately generates 1 unique replacement post in background.
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
    
    replacement_triggered = False
    if available_posts < 12:
        source = post.generation_source or "MANUAL"
        pipeline.status = "running"
        background_tasks.add_task(bg_reject_replacement, post.id, source)
        replacement_triggered = True
    
    return {
        "message": "Post rejected successfully",
        "original_post_id": post.id,
        "replacement_generated": replacement_triggered,
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
    # 1. Total and status counts (Optimized using SQLAlchemy group_by query)
    from sqlalchemy import func
    status_counts = dict(db.query(Post.status, func.count(Post.id)).group_by(Post.status).all())
    
    total = sum(status_counts.values())
    draft = status_counts.get("DRAFT", 0)
    approved = status_counts.get("APPROVED", 0)
    queued = status_counts.get("QUEUED", 0)
    publishing = status_counts.get("PUBLISHING", 0)
    published = status_counts.get("PUBLISHED", 0)
    rejected = status_counts.get("REJECTED", 0)
    failed = status_counts.get("FAILED", 0)

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

def verify_cron_auth(authorization: str = Header(None)):
    # Local dev or testing bypass: allow cron endpoints locally without auth headers
    if os.getenv("VERCEL") is None:
        return
        
    # 1. Check Vercel-injected CRON_SECRET
    cron_secret = settings.CRON_SECRET or os.getenv("CRON_SECRET")
    if cron_secret:
        if authorization == f"Bearer {cron_secret}":
            return
            
    # 2. Fallback to JWT_SECRET if configured securely
    if settings.JWT_SECRET and settings.JWT_SECRET != "super-secret-key":
        if authorization == f"Bearer {settings.JWT_SECRET}":
            return
            
    # If on Vercel and unauthorized, raise 401
    logger.warning(f"Unauthorized Cron request blocked. Header: {authorization[:15] if authorization else 'None'}...")
    raise HTTPException(status_code=401, detail="Unauthorized Cron Request")

@router.get("/cron/generate", dependencies=[Depends(verify_cron_auth)])
@router.post("/cron/generate", dependencies=[Depends(verify_cron_auth)])
async def cron_auto_generate(db: Session = Depends(get_db)):
    """
    Triggered by Vercel Cron every 2 hours.
    Generates exactly 4 posts with retry logic and failure monitoring.
    """
    logger.info("Vercel Cron: Triggering auto generation...")
    import asyncio
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            count = await pipeline.run_generation(db, limit=4, source="AUTO")
            return {"message": "Auto generation cron completed", "generated_count": count}
        except Exception as e:
            logger.error(f"Vercel Cron auto generation attempt {attempt + 1} failed: {e}")
            if attempt == max_attempts - 1:
                # Log final failure to DB for monitoring / alerts
                db.add(ActivityLog(
                    action="cron_generate_failed",
                    entity_type="system",
                    entity_id=None
                ))
                db.commit()
                # Critical warning alert logged
                logger.critical(f"ALERT: Cron generation failed after {max_attempts} attempts. Error: {e}")
                raise HTTPException(status_code=500, detail=f"Cron failed after {max_attempts} attempts: {e}")
            await asyncio.sleep(2 ** attempt)

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

# System settings management endpoints
@router.get("/settings")
def get_settings(db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    """
    Get all dynamic system settings merged with in-memory fallback defaults.
    """
    if current_user != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin access only")

    db_settings = {s.key: s.value for s in db.query(SystemSetting).all()}
    return {
        "PROJECT_NAME": db_settings.get("PROJECT_NAME") or settings.PROJECT_NAME,
        "OLLAMA_BASE_URL": db_settings.get("OLLAMA_BASE_URL") or settings.OLLAMA_BASE_URL,
        "OLLAMA_MODEL": db_settings.get("OLLAMA_MODEL") or settings.OLLAMA_MODEL,
        "INSTAGRAM_ACCESS_TOKEN": db_settings.get("INSTAGRAM_ACCESS_TOKEN") or settings.INSTAGRAM_ACCESS_TOKEN or "",
        "INSTAGRAM_BUSINESS_ID": db_settings.get("INSTAGRAM_BUSINESS_ID") or settings.INSTAGRAM_BUSINESS_ID or "",
        "PUBLIC_HOST": db_settings.get("PUBLIC_HOST") or settings.PUBLIC_HOST,
        "CRON_SECRET": db_settings.get("CRON_SECRET") or settings.CRON_SECRET or "",
    }

@router.post("/settings")
def update_settings(req: SettingsUpdateRequest, db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    """
    Save settings to database and dynamically apply them in-memory to backend config settings.
    """
    if current_user != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin access only")

    update_dict = req.dict(exclude_unset=True)
    for key, value in update_dict.items():
        db_setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not db_setting:
            db_setting = SystemSetting(key=key, value=value)
            db.add(db_setting)
        else:
            db_setting.value = value
        
        # Apply in-memory override immediately
        if hasattr(settings, key):
            setattr(settings, key, value)
            
    db.commit()
    return {"message": "Settings updated successfully"}

