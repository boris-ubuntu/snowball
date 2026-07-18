"""
Background updater service.
Runs periodic tasks to refresh cached data from MOEX, CBR, etc.
This ensures the dashboard loads fast from cache, with background refresh.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from .cache_service import CACHE_TTL

logger = logging.getLogger(__name__)


async def _refresh_single_price(db: Session, ticker: str, security_type: Optional[str], isin: Optional[str] = None):
    """Refresh price for a single security and cache it."""
    from .moex_service import get_current_price
    try:
        await get_current_price(db, ticker, isin, security_type, force_refresh=True)
    except Exception as e:
        logger.debug(f"Background price refresh failed for {ticker}: {e}")


async def refresh_all_prices_background(db: Session):
    """Refresh prices for securities with positions whose price is stale (background task).

    Only refreshes securities that have no recent price (older than PRICE_MAX_AGE),
    so we don't hammer MOEX on every background cycle for already-fresh data.
    """
    from .. import models
    from datetime import datetime, timedelta

    PRICE_MAX_AGE = timedelta(minutes=10)

    now = datetime.utcnow()
    securities = (
        db.query(models.Security)
        .join(models.PortfolioPosition, models.PortfolioPosition.security_id == models.Security.id)
        .all()
    )

    # Keep only securities whose price is missing or older than the max age
    stale = [
        sec for sec in securities
        if sec.price_updated_at is None or (now - sec.price_updated_at) > PRICE_MAX_AGE
    ]

    if not stale:
        logger.info("🔄 Background: all prices fresh, skipping price refresh")
        return

    logger.info(f"🔄 Background: refreshing prices for {len(stale)}/{len(securities)} stale securities")

    # Batch: process up to 5 simultaneously
    semaphore = asyncio.Semaphore(5)

    async def _refresh(sec):
        async with semaphore:
            await _refresh_single_price(db, sec.ticker, sec.security_type, sec.isin)

    tasks = [_refresh(sec) for sec in stale]
    await asyncio.gather(*tasks)
    
    # Commit prices to database
    for sec in securities:
        cache_entry = db.query(models.MoexCache).filter(
            models.MoexCache.ticker == sec.ticker,
            models.MoexCache.cache_type == 'price'
        ).first()
        if cache_entry:
            import json
            try:
                data = json.loads(cache_entry.data) if isinstance(cache_entry.data, str) else cache_entry.data
                if data and len(data) > 0:
                    price = data[0].get('price')
                    if price and price > 0:
                        sec.current_price = price
                        sec.price_updated_at = datetime.utcnow()
            except:
                pass
    
    db.commit()
    logger.info(f"✅ Background: prices refreshed")


async def _refresh_dividends_for_ticker(db: Session, ticker: str):
    """Refresh dividends for a single ticker."""
    from .moex_dividends import get_dividends_for_ticker
    try:
        await get_dividends_for_ticker(db, ticker, force_refresh=False)
    except Exception as e:
        logger.debug(f"Background dividends refresh failed for {ticker}: {e}")


async def refresh_dividends_background(db: Session, portfolio_id: int):
    """Refresh dividends for all securities in portfolio (background).
    Uses dohod.ru as primary source (has future dividends for SBER, MDMG, etc.)
    and MOEX as fallback (historical dividends)."""
    from .. import crud
    
    securities = crud.get_portfolio_securities(db, portfolio_id)
    logger.info(f"🔄 Background: refreshing dividends for {len(securities)} securities")
    
    # 1. Refresh dohod.ru dividends (primary source for future dividends).
    #    Respect the 24h cache TTL — skip the heavy HTML scrape if cache is fresh.
    try:
        from .dohod_service import fetch_dohod_dividends
        await fetch_dohod_dividends(db, force_refresh=False)
        logger.info("✅ Background: dohod.ru dividends refreshed (or served from cache)")
    except Exception as e:
        logger.debug(f"Background dohod.ru refresh failed: {e}")
    
    # 2. Refresh MOEX dividends (historical data) for each ticker
    semaphore = asyncio.Semaphore(3)
    
    async def _refresh(sec):
        async with semaphore:
            await _refresh_dividends_for_ticker(db, sec.ticker)
    
    tasks = [_refresh(sec) for sec in securities if getattr(sec, "quantity", 0) > 0]
    await asyncio.gather(*tasks)
    logger.info(f"✅ Background: dividends refreshed")


async def _refresh_coupons_for_ticker(db: Session, ticker: str):
    """Refresh coupons for a single ticker."""
    from .moex_coupons import get_coupons_for_ticker
    try:
        await get_coupons_for_ticker(db, ticker, force_refresh=False)
    except Exception as e:
        logger.debug(f"Background coupons refresh failed for {ticker}: {e}")


async def refresh_coupons_background(db: Session, portfolio_id: int):
    """Refresh coupons for all bonds/OFZ in portfolio (background)."""
    from .. import crud
    
    securities = crud.get_portfolio_securities(db, portfolio_id)
    logger.info(f"🔄 Background: refreshing coupons for bonds/OFZ")
    
    semaphore = asyncio.Semaphore(3)
    
    async def _refresh(sec):
        async with semaphore:
            if sec.security_type in ("bond", "ofz"):
                await _refresh_coupons_for_ticker(db, sec.ticker)
    
    tasks = [_refresh(sec) for sec in securities if getattr(sec, "quantity", 0) > 0]
    await asyncio.gather(*tasks)
    logger.info(f"✅ Background: coupons refreshed")


async def refresh_cbr_rates_background(db: Session):
    """Refresh CBR exchange rates (background). Skip if cache is fresh (24h TTL)."""
    from .cache_service import get_cached_data
    if get_cached_data(db, "CBR_ALL", "cbr_rates") is not None:
        logger.info("🔄 Background: CBR rates cache fresh, skipping")
        return
    try:
        from .cbr_service import fetch_cbr_rates
        rates = await fetch_cbr_rates()
        # Cache in moex_cache
        from .cache_service import set_cached_data
        cbr_list = [{"currency": k, "rate": v} for k, v in rates.items()]
        set_cached_data(db, "CBR_ALL", "cbr_rates", cbr_list, ttl_minutes=60 * 24)
        logger.info(f"✅ Background: CBR rates refreshed")
    except Exception as e:
        logger.debug(f"Background CBR rates refresh failed: {e}")


async def refresh_economy_background(db: Session):
    """Refresh economy indicators from CBR (background). Skip if cache is fresh (24h TTL)."""
    from .cache_service import get_cached_data
    if get_cached_data(db, "ECONOMY", "economy") is not None:
        logger.info("🔄 Background: economy indicators cache fresh, skipping")
        return
    try:
        from .cbr_economy import fetch_economy_indicators
        indicators = await fetch_economy_indicators()
        from .cache_service import set_cached_data
        econ_data = [{"key_rate": indicators["key_rate"], "inflation_rate": indicators["inflation_rate"]}]
        set_cached_data(db, "ECONOMY", "economy", econ_data, ttl_minutes=60 * 24)
        logger.info(f"✅ Background: economy indicators refreshed: key_rate={indicators['key_rate']}%, inflation={indicators['inflation_rate']}%")
    except Exception as e:
        logger.debug(f"Background economy refresh failed: {e}")
