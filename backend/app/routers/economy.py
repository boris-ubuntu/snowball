"""
Economy indicators router - CBR key rate, inflation
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.cache_service import get_cached_data
from app.services.cbr_economy import fetch_economy_indicators

router = APIRouter(prefix="/api/economy", tags=["economy"])


@router.get("/indicators")
async def get_economy_indicators(db: Session = Depends(get_db)):
    """Get current CBR key rate and inflation (cache-first)"""
    from app.services.cbr_economy import DEFAULT_KEY_RATE, DEFAULT_INFLATION

    # Try cache first
    cached = get_cached_data(db, "ECONOMY", "economy")
    if cached and len(cached) > 0:
        key_rate = cached[0].get("key_rate", 0)
        inflation_rate = cached[0].get("inflation_rate", 0)
        # If cached values are None (from previous bad background update), use fallbacks
        if key_rate is None:
            key_rate = DEFAULT_KEY_RATE
        if inflation_rate is None:
            inflation_rate = DEFAULT_INFLATION
        return {
            "status": "ok",
            "key_rate": key_rate,
            "inflation_rate": inflation_rate,
        }
    
    # Fall back to live fetch (which has its own fallbacks)
    indicators = await fetch_economy_indicators()
    return {
        "status": "ok",
        **indicators,
    }
