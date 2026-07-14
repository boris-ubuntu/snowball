import httpx
import logging
from typing import List, Optional, Dict
from datetime import date, datetime
from sqlalchemy.orm import Session

from .. import models
from .cache_service import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"


async def get_dividends_for_ticker(db: Session, ticker: str, force_refresh: bool = False) -> List[Dict]:
    """
    Fetch dividends for a ticker from MOEX ISS API with caching.
    """
    # Пытаемся получить из кеша
    if not force_refresh:
        cached = get_cached_data(db, ticker, 'dividends')
        if cached is not None:
            logger.debug(f"Using cached dividends for {ticker}")
            return cached

    # Если нет в кеше или нужно обновить - запрашиваем из MOEX
    url = f"{MOEX_BASE}/securities/{ticker}/dividends.json"
    params = {"iss.meta": "off"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.debug(f"MOEX dividends error for {ticker}: HTTP {resp.status_code}")
                return []

            data = resp.json()
            dividends_data = data.get("dividends", {})
            
            if not dividends_data:
                return []
                
            columns = dividends_data.get("columns", [])
            rows = dividends_data.get("data", [])

            if not rows:
                return []

            result = []
            for row in rows:
                entry = {}
                for i, col in enumerate(columns):
                    if i < len(row):
                        entry[col.lower()] = row[i]
                
                registry_date = str(entry.get("registryclosedate", ""))
                value = entry.get("value")
                
                if not registry_date or value is None:
                    continue
                    
                try:
                    value_float = float(value)
                except (ValueError, TypeError):
                    continue
                    
                if value_float <= 0:
                    continue
                    
                result.append({
                    "ticker": entry.get("secid", ticker),
                    "isin": entry.get("isin", ""),
                    "registry_close_date": registry_date,
                    "value": value_float,
                    "currency": entry.get("currencyid", "RUB"),
                })

            # Сохраняем в кеш
            if result:
                set_cached_data(db, ticker, 'dividends', result)

            return result

        except Exception as e:
            logger.debug(f"MOEX dividends fetch error for {ticker}: {e}")
            return []


async def get_portfolio_dividends(db: Session, portfolio_id: int, force_refresh: bool = False) -> List[Dict]:
    """
    Get upcoming dividends for all securities in a portfolio.
    """
    from .. import crud

    securities = crud.get_portfolio_securities(db, portfolio_id)
    today = date.today()
    all_dividends = []

    for sec in securities:
        if getattr(sec, "quantity", 0) <= 0:
            continue
            
        try:
            divs = await get_dividends_for_ticker(db, sec.ticker, force_refresh)
            for div in divs:
                try:
                    close_date = datetime.strptime(div["registry_close_date"], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue

                if close_date >= today:
                    all_dividends.append({
                        "ticker": sec.ticker,
                        "name": sec.name,
                        "isin": div.get("isin", ""),
                        "registry_close_date": div["registry_close_date"],
                        "value_per_share": div["value"],
                        "currency": div.get("currency", "RUB"),
                        "quantity": getattr(sec, "quantity", 0),
                        "total_expected": div["value"] * getattr(sec, "quantity", 0),
                    })
        except Exception as e:
            logger.debug(f"Error fetching dividends for {sec.ticker}: {e}")
            continue

    all_dividends.sort(key=lambda x: x["registry_close_date"])
    return all_dividends


async def get_portfolio_dividends_all(db: Session, portfolio_id: int, force_refresh: bool = False) -> List[Dict]:
    """
    Get ALL dividends (past and future) for all securities in a portfolio.
    """
    from .. import crud

    securities = crud.get_portfolio_securities(db, portfolio_id)
    all_dividends = []

    for sec in securities:
        if getattr(sec, "quantity", 0) <= 0:
            continue
            
        try:
            divs = await get_dividends_for_ticker(db, sec.ticker, force_refresh)
            for div in divs:
                try:
                    close_date = datetime.strptime(div["registry_close_date"], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue

                all_dividends.append({
                    "ticker": sec.ticker,
                    "name": sec.name,
                    "isin": div.get("isin", ""),
                    "registry_close_date": div["registry_close_date"],
                    "value_per_share": div["value"],
                    "currency": div.get("currency", "RUB"),
                    "quantity": getattr(sec, "quantity", 0),
                    "total_expected": div["value"] * getattr(sec, "quantity", 0),
                })
        except Exception as e:
            logger.debug(f"Error fetching dividends for {sec.ticker}: {e}")
            continue

    all_dividends.sort(key=lambda x: x["registry_close_date"], reverse=True)
    return all_dividends