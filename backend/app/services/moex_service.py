import httpx
import logging
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime

from .cache_service import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"
OFZ_FACE_VALUE = 1000.0


def _rows_as_dicts(payload: dict, block: str) -> List[Dict[str, Any]]:
    """Convert a MOEX ISS `{block: {columns: [...], data: [[...], ...]}}` block
    into a list of dicts keyed by column name."""
    section = payload.get(block, {})
    columns = section.get("columns", [])
    rows = section.get("data", [])
    return [dict(zip(columns, row)) for row in rows]


def _first_positive_price(entries: List[Dict[str, Any]], *keys: str) -> Optional[float]:
    """Return the first positive float found under any of `keys` across `entries`."""
    for entry in entries:
        for key in keys:
            raw = entry.get(key)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (ValueError, TypeError):
                continue
            if value > 0:
                return value
    return None


async def _fetch_bond_price(client: httpx.AsyncClient, ticker: str) -> Optional[float]:
    """Fetch price (in RUB) for a bond/OFZ from MOEX TQOB board.
    PREVPRICE/LAST for bonds are a percentage of face value."""
    url = (
        f"{MOEX_BASE}/engines/stock/markets/bonds/boards/TQOB/securities/{ticker}.json"
        "?iss.meta=off&securities.columns=SECID,PREVPRICE,LAST,FACEVALUE"
    )
    try:
        resp = await client.get(url)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка запроса для {ticker}: {e}")
        return None

    if resp.status_code != 200:
        logger.warning(f"⚠️ MOEX вернул {resp.status_code} для {ticker}")
        return None

    entries = _rows_as_dicts(resp.json(), "securities")
    for entry in entries:
        price_raw = entry.get("PREVPRICE") or entry.get("LAST")
        if price_raw is None:
            continue
        try:
            price_percent = float(price_raw)
        except (ValueError, TypeError) as e:
            logger.warning(f"⚠️ Ошибка конвертации цены для {ticker}: {e}")
            continue
        if price_percent <= 0:
            continue
        try:
            face_value = float(entry.get("FACEVALUE") or 0)
        except (ValueError, TypeError):
            face_value = 0
        if face_value <= 0:
            face_value = OFZ_FACE_VALUE
        price_rub = price_percent / 100.0 * face_value
        logger.info(f"✅ Получена цена для ОФЗ {ticker}: {price_rub} ₽ ({price_percent}% от номинала {face_value})")
        return price_rub

    return None


async def _fetch_share_price(client: httpx.AsyncClient, ticker: str, board: str) -> Optional[float]:
    """Fetch price for a share/ETF/depositary receipt from a given board (e.g. TQBR, TQTF, TQBD)."""
    url = (
        f"{MOEX_BASE}/engines/stock/markets/shares/boards/{board}/securities/{ticker}.json"
        "?iss.meta=off&marketdata.columns=SECID,LAST,LCURRENTPRICE"
        "&securities.columns=SECID,PREVPRICE,LAST"
    )
    try:
        resp = await client.get(url)
    except Exception as e:
        logger.debug(f"Error getting price for {ticker} on board {board}: {e}")
        return None

    if resp.status_code != 200:
        return None

    data = resp.json()
    price = _first_positive_price(_rows_as_dicts(data, "marketdata"), "LAST", "LCURRENTPRICE")
    if price is None:
        # Fall back to securities block (PREVPRICE/LAST) when marketdata has no live quote
        price = _first_positive_price(_rows_as_dicts(data, "securities"), "PREVPRICE", "LAST")
    return price


async def get_current_price(
    db: Session,
    ticker: str,
    isin: Optional[str] = None,
    security_type: Optional[str] = None,
    force_refresh: bool = False,
) -> Optional[float]:
    """
    Fetch current market price for a security from MOEX ISS API with caching.
    """
    if not force_refresh:
        cached = get_cached_data(db, ticker, 'price')
        if cached is not None and len(cached) > 0:
            logger.debug(f"Using cached price for {ticker}")
            return cached[0].get('price')

    async with httpx.AsyncClient(timeout=10.0) as client:
        price: Optional[float] = None

        if security_type in ("bond", "ofz"):
            price = await _fetch_bond_price(client, ticker)
        elif security_type == "currency":
            price = await _fetch_currency_rate(ticker)
        else:
            board = "TQTF" if security_type == "etf" else "TQBR"
            price = await _fetch_share_price(client, ticker, board)
            if price is None and security_type != "etf":
                # Some depositary receipts trade on TQBD instead of TQBR
                price = await _fetch_share_price(client, ticker, "TQBD")

        if price is not None and price > 0:
            set_cached_data(db, ticker, 'price', [{'price': price}], ttl_minutes=5)
            logger.info(f"✅ Получена цена для {ticker}: {price}")
            return price

        logger.warning(f"❌ Не удалось получить цену для {ticker}")
        return None


async def _fetch_currency_rate(ticker: str) -> Optional[float]:
    """Official CBR exchange rate for currency-type securities."""
    try:
        from .cbr_service import fetch_cbr_rates
        rates = await fetch_cbr_rates()
        rate = rates.get(ticker)
        if rate is not None and rate > 0:
            logger.info(f"✅ Курс ЦБ для {ticker}: {rate}")
            return rate
    except Exception as e:
        logger.debug(f"Error getting CBR rate for {ticker}: {e}")
    return None


async def refresh_all_prices(db: Session) -> int:
    """Refresh current prices only for securities that have positions in any portfolio"""
    from .. import models

    # Get only securities that have positions (actively held)
    securities = (
        db.query(models.Security)
        .join(models.PortfolioPosition, models.PortfolioPosition.security_id == models.Security.id)
        .all()
    )
    updated = 0

    logger.info(f"🔄 Обновляем цены для {len(securities)} бумаг в портфеле...")

    for sec in securities:
        try:
            price = await get_current_price(db, sec.ticker, sec.isin, sec.security_type, force_refresh=True)
            if price is not None and price > 0:
                sec.current_price = price
                sec.price_updated_at = datetime.utcnow()
                updated += 1
                logger.info(f"✅ Цена обновлена для {sec.ticker}: {price}")
            else:
                logger.warning(f"❌ Не удалось получить цену для {sec.ticker}")

            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"❌ Ошибка обновления для {sec.ticker}: {e}")
            continue

    db.commit()
    logger.info(f"✅ Обновлены цены для {updated}/{len(securities)} бумаг в портфеле")
    return updated
