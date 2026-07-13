from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import asyncio
from datetime import datetime

from .. import schemas, crud
from ..database import get_db
from ..services.moex_service import get_current_price
from ..services.moex_ofz_loader import search_moex_security, load_ofz_bonds

router = APIRouter(prefix="/api/securities", tags=["securities"])


@router.get("/search")
async def search_securities(q: str = Query("", description="Search query"), db: Session = Depends(get_db)):
    """Search MOEX for securities by ticker, name or ISIN"""
    if not q or len(q) < 2:
        return []
    return await search_moex_security(q)


@router.post("/load-ofz")
async def load_ofz(db: Session = Depends(get_db)):
    """Load all available OFZ bonds from MOEX"""
    added = await load_ofz_bonds(db)
    return {"status": "ok", "added": added}


@router.get("/", response_model=List[schemas.SecurityResponse])
def list_securities(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    return crud.get_securities(db, skip=skip, limit=limit)


@router.get("/{security_id}", response_model=schemas.SecurityResponse)
def get_security(security_id: int, db: Session = Depends(get_db)):
    security = crud.get_security(db, security_id)
    if not security:
        raise HTTPException(status_code=404, detail="Security not found")
    return security


@router.post("/", response_model=schemas.SecurityResponse, status_code=201)
async def create_security(data: schemas.SecurityCreate, db: Session = Depends(get_db)):
    existing = crud.get_security_by_ticker(db, data.ticker)
    if existing:
        raise HTTPException(status_code=400, detail=f"Security with ticker '{data.ticker}' already exists")
    
    security = crud.create_security(db, data)
    
    # Try to fetch current price from MOEX
    try:
        price = await get_current_price(security.ticker, security.isin)
        if price is not None:
            security.current_price = price
            security.price_updated_at = datetime.utcnow()
            db.commit()
            db.refresh(security)
    except Exception as e:
        print(f"Could not fetch price for {security.ticker}: {e}")
    
    return security


@router.post("/{security_id}/refresh-price", response_model=schemas.SecurityResponse)
async def refresh_security_price(security_id: int, db: Session = Depends(get_db)):
    """Refresh price for a single security from MOEX"""
    security = crud.get_security(db, security_id)
    if not security:
        raise HTTPException(status_code=404, detail="Security not found")
    price = await get_current_price(security.ticker, security.isin)
    if price is not None:
        security.current_price = price
        security.price_updated_at = datetime.utcnow()
        db.commit()
        db.refresh(security)
    return security


@router.put("/{security_id}", response_model=schemas.SecurityResponse)
def update_security(security_id: int, data: schemas.SecurityUpdate, db: Session = Depends(get_db)):
    security = crud.update_security(db, security_id, data)
    if not security:
        raise HTTPException(status_code=404, detail="Security not found")
    return security


@router.delete("/{security_id}", status_code=204)
def delete_security(security_id: int, db: Session = Depends(get_db)):
    if not crud.delete_security(db, security_id):
        raise HTTPException(status_code=404, detail="Security not found")