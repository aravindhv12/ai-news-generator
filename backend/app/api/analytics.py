from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.analytics import analytics_service

from app.api.deps import get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(get_current_user)])

@router.get("/dashboard")
def get_dashboard_stats(db: Session = Depends(get_db)):
    return analytics_service.get_dashboard_stats(db)

@router.get("/sources")
def get_source_stats(db: Session = Depends(get_db)):
    return analytics_service.get_source_statistics(db)
