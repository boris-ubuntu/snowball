"""
Exchange rates router - CBR currency rates
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.cbr_service import fetch_cbr_rates, CURRENCY_INFO

router = APIRouter(prefix="/api/rates", tags=["rates"])


@router.get("/cbr")
async def get_cbr_rates():
    """Get current CBR exchange rates"""
    rates = await fetch_cbr_rates()
    return {
        "status": "ok",
        "rates": rates,
        "currencies": CURRENCY_INFO,
    }


@router.post("/cbr/refresh")
async def refresh_cbr_rates():
    """Force refresh CBR exchange rates (always hits the CBR API directly, no local cache)"""
    rates = await fetch_cbr_rates()
    return {"status": "ok", "rates": rates}


