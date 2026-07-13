import httpx
import logging
from typing import List, Optional, Dict
from datetime import date, datetime
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"


async def get_dividends_for_ticker(ticker: str) -> List[Dict]:
    """
    Fetch dividends for a ticker from MOEX ISS API.
    Returns list of dicts with keys: ticker, isin, registry_close_date, value, currency
    """
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
                result.append({
                    "ticker": entry.get("secid", ticker),
                    "isin": entry.get("isin", ""),
                    "registry_close_date": str(entry.get("registryclosedate", "")),
                    "value": float(entry.get("value", 0)),
                    "currency": entry.get("currencyid", "RUB"),
                })

            return result

        except Exception as e:
            logger.error(f"MOEX dividends fetch error for {ticker}: {e}")
            return []


async def get_portfolio_dividends(db: Session, portfolio_id: int) -> List[Dict]:
    """
    Get upcoming dividends for all securities in a portfolio.
    Returns dividends sorted by registry_close_date (nearest first).
    Only includes dividends with registry_close_date >= today (upcoming).
    """
    from .. import crud

    # Get securities in portfolio
    securities = crud.get_portfolio_securities(db, portfolio_id)

    today = date.today()
    all_dividends = []

    for sec in securities:
        try:
            divs = await get_dividends_for_ticker(sec.ticker)
            for div in divs:
                # Parse date
                try:
                    close_date = datetime.strptime(div["registry_close_date"], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue

                # Only include upcoming dividends
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
            logger.error(f"Error fetching dividends for {sec.ticker}: {e}")

    # Sort by registry_close_date (nearest first)
    all_dividends.sort(key=lambda x: x["registry_close_date"])

    return all_dividends


async def get_portfolio_dividends_all(db: Session, portfolio_id: int) -> List[Dict]:
    """
    Get ALL dividends (past and future) for all securities in a portfolio.
    Sorted by registry_close_date descending (most recent first).
    """
    from .. import crud

    securities = crud.get_portfolio_securities(db, portfolio_id)
    all_dividends = []

    for sec in securities:
        try:
            divs = await get_dividends_for_ticker(sec.ticker)
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
            logger.error(f"Error fetching dividends for {sec.ticker}: {e}")

    # Sort by registry_close_date descending (most recent first)
    all_dividends.sort(key=lambda x: x["registry_close_date"], reverse=True)

    return all_dividends
