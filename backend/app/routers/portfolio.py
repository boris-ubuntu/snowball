from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import asyncio
import logging
from datetime import date, datetime

from .. import schemas, crud
from ..database import get_db
from ..services.moex_service import refresh_all_prices
from ..services.moex_dividends import get_portfolio_dividends, get_portfolio_dividends_all
from ..services.moex_coupons import get_portfolio_coupons
from ..services.auto_accrual import check_and_process_accruals
from ..services.lqdt_service import get_lqdt_projection

logger = logging.getLogger(__name__)


async def _auto_accrue(db: Session, portfolio_id: int):
    """
    Автоматически начисляет прошедшие дивиденды и купоны, по которым уже прошла
    дата закрытия реестра / выплаты купона и бумага на тот момент находилась в портфеле.
    Идемпотентно: уже начисленные записи пропускаются.
    """
    try:
        await check_and_process_accruals(db, portfolio_id)
    except Exception as e:
        logger.debug(f"Auto-accrual skipped for portfolio {portfolio_id}: {e}")


router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/", response_model=List[schemas.PortfolioResponse])
def list_portfolios(db: Session = Depends(get_db)):
    return crud.get_portfolios(db)


@router.post("/", response_model=schemas.PortfolioResponse, status_code=201)
def create_portfolio(data: schemas.PortfolioCreate, db: Session = Depends(get_db)):
    return crud.create_portfolio(db, data)


@router.get("/default", response_model=schemas.PortfolioResponse)
def get_default_portfolio(db: Session = Depends(get_db)):
    portfolio = crud.get_default_portfolio(db)
    return portfolio


@router.get("/{portfolio_id}", response_model=schemas.PortfolioResponse)
def get_portfolio(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


@router.get("/{portfolio_id}/dashboard", response_model=schemas.DashboardResponse)
async def get_dashboard(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    # Get dashboard from DB only (fast, no external API calls)
    result = await crud.get_dashboard(db, portfolio_id)
    
    # Kick off background refresh of prices, dividends, coupons, CBR rates, and auto-accruals
    # This runs in background after the response is sent
    from ..services.background_updater import (
        refresh_all_prices_background,
        refresh_dividends_background,
        refresh_coupons_background,
        refresh_cbr_rates_background,
        refresh_economy_background,
    )
    
    async def _background_refresh():
        try:
            from ..database import SessionLocal
            bg_db = SessionLocal()
            try:
                # Run all refreshes in parallel
                await asyncio.gather(
                    refresh_all_prices_background(bg_db),
                    refresh_dividends_background(bg_db, portfolio_id),
                    refresh_coupons_background(bg_db, portfolio_id),
                    refresh_cbr_rates_background(bg_db),
                    refresh_economy_background(bg_db),
                )
                # Auto-accruals in background (non-blocking)
                await _auto_accrue(bg_db, portfolio_id)
            finally:
                bg_db.close()
        except Exception as e:
            logger.debug(f"Background refresh error: {e}")
    
    # Schedule background task (fire-and-forget)
    asyncio.create_task(_background_refresh())
    
    return result


@router.get("/{portfolio_id}/securities", response_model=List[schemas.PortfolioSecurityResponse])
def get_portfolio_securities(portfolio_id: int, db: Session = Depends(get_db)):
    """Get securities that are in the portfolio (have positions/transactions)"""
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return crud.get_portfolio_securities(db, portfolio_id)


@router.get("/{portfolio_id}/dividends")
async def portfolio_dividends(
    portfolio_id: int,
    all: bool = Query(False, description="Show all dividends including past"),
    force_refresh: bool = Query(False, description="Force refresh from MOEX"),
    db: Session = Depends(get_db),
):
    """Get dividends for portfolio securities from MOEX + dohod.ru (cache-first, with auto-refresh)"""
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    # Автоматически начисляем прошедшие выплаты (дата закрытия реестра уже прошла
    # и бумага на тот момент находилась в портфеле) — они появятся в Операциях.
    await _auto_accrue(db, portfolio_id)
    
    # Use the proper API functions that handle caching (MOEX + dohod.ru merged)
    if all:
        dividends = await get_portfolio_dividends_all(db, portfolio_id, force_refresh=force_refresh)
    else:
        dividends = await get_portfolio_dividends(db, portfolio_id, force_refresh=force_refresh)
    return dividends


@router.get("/{portfolio_id}/coupons")
async def portfolio_coupons(
    portfolio_id: int,
    upcoming: bool = Query(False, description="Only upcoming coupons"),
    force_refresh: bool = Query(False, description="Force refresh from MOEX"),
    db: Session = Depends(get_db),
):
    """Get coupons for OFZ/bonds in portfolio"""
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    coupons = await get_portfolio_coupons(db, portfolio_id, upcoming_only=upcoming, force_refresh=force_refresh)
    return coupons


@router.post("/{portfolio_id}/process-accruals")
async def process_accruals(portfolio_id: int, db: Session = Depends(get_db)):
    """Auto-process historical dividends and coupons into accrual transactions"""
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    result = await check_and_process_accruals(db, portfolio_id)
    return result


@router.post("/refresh-prices")
async def refresh_prices(db: Session = Depends(get_db)):
    """Refresh current prices for all securities from MOEX API"""
    try:
        updated = await refresh_all_prices(db)
        return {"status": "ok", "updated": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh prices: {str(e)}")


@router.post("/{portfolio_id}/refresh-cache")
async def refresh_cache(
    portfolio_id: int,
    cache_type: Optional[str] = Query(None, description="dividends, coupons, or all"),
    db: Session = Depends(get_db),
):
    """Принудительно обновить кеш MOEX данных"""
    from ..services.moex_dividends import get_portfolio_dividends_all
    from ..services.moex_coupons import get_portfolio_coupons
    from ..services.cache_service import clear_expired_cache
    
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    try:
        result = {"status": "ok", "message": "", "updated": []}
        
        # Очищаем просроченный кеш
        cleared = clear_expired_cache(db)
        if cleared:
            result["message"] += f"Cleared {cleared} expired entries. "
        
        # Обновляем указанные типы кеша
        if cache_type is None or cache_type == "all" or cache_type == "dividends":
            await get_portfolio_dividends_all(db, portfolio_id, force_refresh=True)
            result["updated"].append("dividends")
            result["message"] += "Dividends cache refreshed. "
        
        if cache_type is None or cache_type == "all" or cache_type == "coupons":
            await get_portfolio_coupons(db, portfolio_id, force_refresh=True)
            result["updated"].append("coupons")
            result["message"] += "Coupons cache refreshed. "
        
        if not result["updated"]:
            result["message"] = f"Unknown cache_type: {cache_type}. Use: dividends, coupons, or all"
            result["status"] = "warning"
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh cache: {str(e)}")


# === Positions ===
@router.get("/{portfolio_id}/positions", response_model=List[schemas.PositionResponse])
def list_positions(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return crud.get_positions(db, portfolio_id)


@router.post("/{portfolio_id}/positions", response_model=schemas.PositionResponse, status_code=201)
def create_position(portfolio_id: int, data: schemas.PositionCreate, db: Session = Depends(get_db)):
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    security = crud.get_security(db, data.security_id)
    if not security:
        raise HTTPException(status_code=404, detail="Security not found")
    return crud.create_position(db, portfolio_id, data)


@router.put("/{portfolio_id}/positions/{position_id}", response_model=schemas.PositionResponse)
def update_position(portfolio_id: int, position_id: int, data: schemas.PositionUpdate, db: Session = Depends(get_db)):
    position = crud.update_position(db, position_id, data)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    return position


@router.delete("/{portfolio_id}/positions/{position_id}", status_code=204)
def delete_position(portfolio_id: int, position_id: int, db: Session = Depends(get_db)):
    if not crud.delete_position(db, position_id):
        raise HTTPException(status_code=404, detail="Position not found")


# === Transactions ===
@router.get("/{portfolio_id}/transactions", response_model=List[schemas.TransactionResponse])
def list_transactions(
    portfolio_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return crud.get_transactions(db, portfolio_id, skip=skip, limit=limit)


@router.post("/{portfolio_id}/transactions", response_model=schemas.TransactionResponse, status_code=201)
def create_transaction(portfolio_id: int, data: schemas.TransactionCreate, db: Session = Depends(get_db)):
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    security = crud.get_security(db, data.security_id)
    if not security:
        raise HTTPException(status_code=404, detail="Security not found")
    return crud.create_transaction(db, portfolio_id, data)


@router.put("/{portfolio_id}/transactions/{transaction_id}", response_model=schemas.TransactionResponse)
def update_transaction(portfolio_id: int, transaction_id: int, data: schemas.TransactionUpdate, db: Session = Depends(get_db)):
    transaction = crud.get_transaction(db, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    updated = crud.update_transaction(db, transaction_id, data)
    return updated


@router.delete("/{portfolio_id}/transactions/{transaction_id}", status_code=204)
def delete_transaction(portfolio_id: int, transaction_id: int, db: Session = Depends(get_db)):
    transaction = crud.get_transaction(db, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    crud.delete_transaction(db, transaction_id)


@router.delete("/{portfolio_id}/transactions/by-security/{security_id}", status_code=200)
def delete_transactions_by_security(portfolio_id: int, security_id: int, db: Session = Depends(get_db)):
    """Delete all transactions and position for a security in a portfolio."""
    deleted = crud.delete_transactions_by_security(db, portfolio_id, security_id)
    return {"deleted": deleted, "status": "ok"}


@router.get("/{portfolio_id}/lqdt-projection")
async def portfolio_lqdt_projection(portfolio_id: int, db: Session = Depends(get_db)):
    """Get projected LQDT accruals for the next 12 months for the histogram."""
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    projection = await get_lqdt_projection(db, portfolio_id)
    return projection
