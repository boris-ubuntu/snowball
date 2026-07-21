from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import asyncio
import logging
from datetime import date, datetime, timedelta


from .. import schemas, crud
from ..database import get_db
from ..services.moex_service import refresh_all_prices
from ..services.moex_dividends import get_portfolio_dividends, get_portfolio_dividends_all
from ..services.moex_coupons import get_portfolio_coupons
from ..services.auto_accrual import check_and_process_accruals
from ..services.lqdt_service import get_lqdt_projection

logger = logging.getLogger(__name__)


async def _auto_accrue(db: Session, portfolio_id: int):
    """Автоматически начисляет прошедшие дивиденды и купоны."""
    try:
        await check_and_process_accruals(db, portfolio_id)
    except Exception as e:
        logger.debug(f"Auto-accrual skipped for portfolio {portfolio_id}: {e}")


_BG_REFRESH_INTERVAL_MINUTES = 5


def _should_run_background_refresh(db: Session) -> bool:
    """Cross-process throttle backed by the DB cache table."""
    from ..services.cache_service import get_cached_data, set_cached_data

    if get_cached_data(db, "_system", "bg_refresh_throttle") is not None:
        return False
    set_cached_data(
        db, "_system", "bg_refresh_throttle",
        [{"ts": datetime.utcnow().isoformat()}],
        ttl_minutes=_BG_REFRESH_INTERVAL_MINUTES,
    )
    return True



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
    if _should_run_background_refresh(db):
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
                    # Run all refreshes in parallel (non-force, throttled by TTL)
                    await asyncio.gather(
                        refresh_all_prices_background(bg_db),
                        refresh_dividends_background(bg_db, portfolio_id),
                        refresh_coupons_background(bg_db, portfolio_id),
                        refresh_cbr_rates_background(bg_db),
                        refresh_economy_background(bg_db),
                    )
                    await _auto_accrue(bg_db, portfolio_id)
                finally:
                    bg_db.close()
            except Exception as e:
                logger.debug(f"Background refresh error: {e}")
        
        asyncio.create_task(_background_refresh())
    else:
        logger.debug("Background refresh skipped (throttled)")
    
    return result


@router.get("/{portfolio_id}/securities", response_model=List[schemas.PortfolioSecurityResponse])
def get_portfolio_securities(portfolio_id: int, db: Session = Depends(get_db)):
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
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    from ..services.cache_service import get_cached_data as _get_cache
    from ..services.dohod_service import get_dohod_dividends_for_portfolio
    from ..services.moex_dividends import get_portfolio_dividends_all
    from ..services.dividend_projection import estimate_dividend_for_ticker
    
    today = date.today()
    one_year = today + timedelta(days=365)
    
    result = []
    covered_tickers = set()
    
    # Try dohod.ru first
    try:
        dohod_divs = await get_dohod_dividends_for_portfolio(db, portfolio_id, force_refresh=force_refresh)
        for d in dohod_divs:
            try:
                close_date = datetime.strptime(d["registry_close_date"], "%Y-%m-%d").date()
                if all or close_date >= today:
                    result.append(d)
                if close_date <= one_year:
                    covered_tickers.add(d["ticker"])
            except:
                pass
    except Exception as e:
        logger.debug(f"Dohod dividends fetch failed: {e}")
    
    # Fallback: MOEX API
    try:
        moex_divs = await get_portfolio_dividends_all(db, portfolio_id, force_refresh=force_refresh)
        for d in moex_divs:
            try:
                close_date = datetime.strptime(d["registry_close_date"], "%Y-%m-%d").date()
            except:
                continue
            if (d["ticker"], d["registry_close_date"]) in {(r["ticker"], r["registry_close_date"]) for r in result}:
                continue
            if all or close_date >= today:
                result.append(d)
            if today <= close_date <= one_year:
                covered_tickers.add(d["ticker"])
    except Exception as e:
        logger.debug(f"MOEX dividends fetch failed: {e}")
    
    # Достраиваем прогноз для акций без данных на ближайшие 12 месяцев
    try:
        securities = crud.get_portfolio_securities(db, portfolio_id)
        for sec in securities:
            if sec.security_type != "stock" or getattr(sec, "quantity", 0) <= 0:
                continue
            if sec.ticker in covered_tickers:
                continue
            projected = await estimate_dividend_for_ticker(db, sec.ticker, sec.quantity)
            if projected:
                result.append({
                    "ticker": sec.ticker,
                    "name": sec.name,
                    "isin": sec.isin or "",
                    "registry_close_date": projected["registry_close_date"],
                    "value_per_share": projected["value_per_share"],
                    "currency": sec.currency or "RUB",
                    "quantity": projected["quantity"],
                    "total_expected": projected["total_expected"],
                    "source": "projected",
                })
    except Exception as e:
        logger.debug(f"Dividend projection failed for portfolio {portfolio_id}: {e}")
    
    result.sort(key=lambda x: x["registry_close_date"], reverse=True)
    return result



@router.get("/{portfolio_id}/coupons")
async def portfolio_coupons(
    portfolio_id: int,
    upcoming: bool = Query(False, description="Only upcoming coupons"),
    force_refresh: bool = Query(False, description="Force refresh from MOEX"),
    db: Session = Depends(get_db),
):
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    from ..services.moex_coupons import get_portfolio_coupons as _get_portfolio_coupons
    result = await _get_portfolio_coupons(portfolio_id, upcoming_only=upcoming)
    result.sort(key=lambda x: x["coupon_date"], reverse=True)
    return result


@router.post("/{portfolio_id}/process-accruals")
async def process_accruals(portfolio_id: int, db: Session = Depends(get_db)):
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
        cleared = clear_expired_cache(db)
        if cleared:
            result["message"] += f"Cleared {cleared} expired entries. "
        
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


@router.post("/refresh-all")
async def refresh_all_data(data: dict, db: Session = Depends(get_db)):
    """Refresh all data from external sources with force=True (no cache skip)."""
    portfolio_id = data.get("portfolio_id", 1)
    from ..services.background_updater import (
        refresh_all_prices_background,
        refresh_dividends_background,
        refresh_coupons_background,
        refresh_cbr_rates_background,
        refresh_economy_background,
    )
    results = {}
    errors = []
    try:
        # Run all refreshes and capture results/errors
        tasks = {
            "prices": refresh_all_prices_background(db, force=True),
            "dividends": refresh_dividends_background(db, portfolio_id, force=True),
            "coupons": refresh_coupons_background(db, portfolio_id, force=True),
            "cbr_rates": refresh_cbr_rates_background(db, force=True),
            "economy": refresh_economy_background(db, force=True),
        }
        for name, coro in tasks.items():
            try:
                await coro
                results[name] = "ok"
            except Exception as e:
                results[name] = f"error: {str(e)}"
                errors.append(f"{name}: {str(e)}")
        # Auto-accrue after refresh
        try:
            await _auto_accrue(db, portfolio_id)
            results["accrual"] = "ok"
        except Exception as e:
            results["accrual"] = f"error: {str(e)}"
            errors.append(f"accrual: {str(e)}")
        status = "ok" if not errors else "partial"
        return {
            "status": status,
            "results": results,
            "errors": errors if errors else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh all data: {str(e)}")


@router.get("/{portfolio_id}/lqdt-projection")
async def portfolio_lqdt_projection(portfolio_id: int, db: Session = Depends(get_db)):
    """Get projected LQDT accruals for the next 12 months for the histogram."""
    portfolio = crud.get_portfolio(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    projection = await get_lqdt_projection(db, portfolio_id)
    return projection