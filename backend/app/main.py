import os
import sys

# Add backend directory to sys.path to support importing 'app' package when run directly by Vercel
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.posts import router as posts_router
from app.api.analytics import router as analytics_router

app = FastAPI(
    title="AI Tech News Platform API",
    description="Automated social media publishing for tech news",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.auth import router as auth_router

from fastapi import Request
from fastapi.responses import JSONResponse
import logging
from collections import defaultdict
import time

RATE_LIMITS = defaultdict(list)

@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    path = request.url.path
    if path in ["/api/auth/login", "/api/generate", "/auth/login"]:
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        RATE_LIMITS[ip] = [t for t in RATE_LIMITS[ip] if now - t < 60]
        if len(RATE_LIMITS[ip]) >= 5:
            return JSONResponse(
                status_code=429,
                content={"message": "Too many requests. Please try again in a minute."}
            )
        RATE_LIMITS[ip].append(now)
    return await call_next(request)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self' http: https: data: 'unsafe-inline' 'unsafe-eval'; frame-ancestors 'none';"
    return response

app.include_router(auth_router)
app.include_router(posts_router)
app.include_router(analytics_router)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Global error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "detail": str(exc)},
    )

# Mount the output directory to serve generated images
if os.getenv("VERCEL"):
    output_path = "/tmp/output"
else:
    output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../output"))
os.makedirs(output_path, exist_ok=True)
app.mount("/output", StaticFiles(directory=output_path), name="output")

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.services.pipeline import pipeline
from app.services.publisher import publisher_service
from app.db.session import SessionLocal

# Setup Scheduler
scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def start_scheduler():
    # Automatically initialize database schema
    from app.models.models import Base
    from app.db.session import engine
    Base.metadata.create_all(bind=engine)

    # Load settings from db and apply to settings object
    db = SessionLocal()
    try:
        from app.models.models import SystemSetting
        db_settings = db.query(SystemSetting).all()
        for s in db_settings:
            if hasattr(settings, s.key) and s.value is not None:
                setattr(settings, s.key, s.value)
    except Exception as e:
        logging.error(f"Failed to load system settings from database: {e}")
    finally:
        db.close()

    # Ensure social card fonts are loaded
    from app.services.image_service import image_service
    await image_service.ensure_fonts()

    # 1. Schedule auto generation run every 2 hours
    async def scheduled_generate():
        db = SessionLocal()
        try:
            await pipeline.run_generation(db, limit=4, source="AUTO")
        except Exception as e:
            logging.error(f"Scheduler generate task failed: {e}")
        finally:
            db.close()
            
    scheduler.add_job(scheduled_generate, 'interval', hours=2)
    
    # 2. Schedule publish queue processing every 30 minutes
    async def scheduled_publish():
        db = SessionLocal()
        try:
            await publisher_service.process_queue(db, public_host=settings.PUBLIC_HOST)
        except Exception as e:
            logging.error(f"Scheduler publish task failed: {e}")
        finally:
            db.close()

    scheduler.add_job(scheduled_publish, 'interval', minutes=30)
    
    scheduler.start()


@app.get("/")
async def root():
    return {"message": "AI Tech News Platform API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# Vercel trigger rebuild comment

