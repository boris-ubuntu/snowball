"""
Background updater service.
Runs periodic tasks to refresh cached data from MOEX, CBR, etc.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from .cache_service import CACHE_TTL

logger = logging.getLogger(__name__)


async def _refresh_single_price(db: Session, ticker: str, security_type: Optional[str], isin: Optional[str] = None):
    """Refresh price for a single security and cache it."""
    from .moex_service import get_current_price
    try:
        await get_current_price(ticker, isin, security_type)
    except Exception as e:
        logger.debug(f"Background price refresh failed for {ticker}: {e}")


async def refresh_all_prices_background(db: Session, force: bool = False):
    """Refresh prices for securities with positions.
    If force=True, refreshes ALL securities regardless of cache age.
    """
    from .. import models

    now = datetime.now(timezone.utc)
    securities = (
        db.query(models.Security)
        .join(models.PortfolioPosition, models.PortfolioPosition.security_id == models.Security.id)
        .all()
    )

    if force:
        stale = securities
        logger.info(f"🔄 Force refresh: refreshing prices for all {len(securities)} securities")
    else:
        PRICE_MAX_AGE = timedelta(minutes=10)
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
            try:
                from .moex_service import get_current_price
                price = await get_current_price(sec.ticker, sec.isin, sec.security_type)
                if price is not None and price > 0:
                    sec.current_price = price
                    sec.price_updated_at = datetime.now(timezone.utc)
                    logger.info(f"✅ Price updated for {sec.ticker}: {price}")
                else:
                    logger.warning(f"❌ No price for {sec.ticker}")
            except Exception as e:
                logger.error(f"❌ Error refreshing price for {sec.ticker}: {e}")

    tasks = [_refresh(sec) for sec in stale]
    await asyncio.gather(*tasks)
    
    db.commit()
    logger.info(f"✅ Prices refreshed for {len(stale)} securities")


async def _refresh_dividends_for_ticker(db: Session, ticker: str, force_refresh: bool = False):
    """Refresh dividends for a single ticker."""
    from .moex_dividends import get_dividends_for_ticker
    try:
        await get_dividends_for_ticker(db, ticker, force_refresh=force_refresh)
    except Exception as e:
        logger.debug(f"Dividends refresh failed for {ticker}: {e}")


async def refresh_dividends_background(db: Session, portfolio_id: int, force: bool = False):
    """Refresh dividends for all securities in portfolio."""
    from .. import crud
    
    securities = crud.get_portfolio_securities(db, portfolio_id)
    logger.info(f"🔄 {'Force' if force else 'Background'}: refreshing dividends for {len(securities)} securities")
    
    # 1. Refresh dohod.ru dividends
    try:
        from .dohod_service import fetch_dohod_dividends
        await fetch_dohod_dividends(db, force_refresh=force)
        logger.info(f"✅ dohod.ru dividends refreshed")
    except Exception as e:
        logger.debug(f"dohod.ru refresh failed: {e}")
    
    # 2. Refresh MOEX dividends for each ticker
    semaphore = asyncio.Semaphore(3)
    
    async def _refresh(sec):
        async with semaphore:
            await _refresh_dividends_for_ticker(db, sec.ticker, force_refresh=force)
    
    tasks = [_refresh(sec) for sec in securities if getattr(sec, "quantity", 0) > 0]
    await asyncio.gather(*tasks)
    logger.info(f"✅ Dividends refreshed")


async def _refresh_coupons_for_ticker(db: Session, ticker: str):
    """Refresh coupons for a single ticker and store in cache."""
    from .moex_coupons import get_coupons_for_ticker
    from .cache_service import set_cached_data
    try:
        coupons = await get_coupons_for_ticker(ticker)
        if coupons:
            set_cached_data(db, ticker, 'coupons', coupons, ttl_minutes=60)
    except Exception as e:
        logger.debug(f"Coupons refresh failed for {ticker}: {e}")


async def refresh_coupons_background(db: Session, portfolio_id: int, force: bool = False):
    """Refresh coupons for all bonds/OFZ in portfolio."""
    from .. import crud
    
    securities = crud.get_portfolio_securities(db, portfolio_id)
    logger.info(f"🔄 {'Force' if force else 'Background'}: refreshing coupons for bonds/OFZ")
    
    semaphore = asyncio.Semaphore(3)
    
    async def _refresh(sec):
        async with semaphore:
            if sec.security_type in ("bond", "ofz"):
                await _refresh_coupons_for_ticker(db, sec.ticker)
    
    tasks = [_refresh(sec) for sec in securities if getattr(sec, "quantity", 0) > 0]
    await asyncio.gather(*tasks)
    logger.info(f"✅ Coupons refreshed")


async def refresh_cbr_rates_background(db: Session, force: bool = False):
    """Refresh CBR exchange rates. If force=True, always fetch from CBR."""
    if not force:
        from .cache_service import get_cached_data
        if get_cached_data(db, "CBR_ALL", "cbr_rates") is not None:
            logger.info("🔄 Background: CBR rates cache fresh, skipping")
            return
    try:
        from .cbr_service import fetch_cbr_rates
        rates = await fetch_cbr_rates()
        from .cache_service import set_cached_data
        cbr_list = [{"currency": k, "rate": v} for k, v in rates.items()]
        set_cached_data(db, "CBR_ALL", "cbr_rates", cbr_list, ttl_minutes=60 * 24)
        logger.info(f"✅ CBR rates refreshed")
    except Exception as e:
        logger.debug(f"CBR rates refresh failed: {e}")


async def refresh_economy_background(db: Session, force: bool = False):
    """Refresh economy indicators from CBR. If force=True, always fetch."""
    if not force:
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
        logger.info(f"✅ Economy indicators refreshed: key_rate={indicators['key_rate']}%, inflation={indicators['inflation_rate']}%")
    except Exception as e:
        logger.debug(f"Economy refresh failed: {e}")