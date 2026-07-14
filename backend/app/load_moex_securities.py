import httpx
import asyncio
import logging
from typing import Optional
from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal

logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"

# Группы ценных бумаг, которые нас интересуют
GROUPS = {
    "stock_shares": "stock",   # Акции
    "stock_bonds": "bond",     # Облигации
    "etf_ppif": "etf",         # ETF
    "stock_dr": "stock",       # Депозитарные расписки
    "stock_mortgage": "bond",  # Ипотечные облигации
}


async def load_all_securities(db: Session) -> int:
    """Load all securities from MOEX and insert into database."""
    existing_tickers = {s.ticker for s in db.query(models.Security).all()}
    added = 0
    page_size = 500

    async with httpx.AsyncClient(timeout=30.0) as client:
        for group_name, sec_type in GROUPS.items():
            start = 0
            total = None

            while total is None or start < total:
                url = f"{MOEX_BASE}/securities.json"
                params = {
                    "iss.meta": "off",
                    "iss.only": "securities",
                    "securities.columns": "secid,shortname,isin,group",
                    "securities.limit": page_size,
                    "securities.start": start,
                    "group": group_name,
                    "group_by": "group",
                    "group_by_filter": group_name,
                }

                try:
                    resp = await client.get(url, params=params)
                    if resp.status_code != 200:
                        logger.warning(f"Failed to load {group_name}: {resp.status_code}")
                        break

                    data = resp.json()
                    sec_data = data.get("securities", {})
                    columns = sec_data.get("columns", [])
                    rows = sec_data.get("data", [])

                    if total is None:
                        total = sec_data.get("total", len(rows))

                    if not rows:
                        break

                    col_map = {col: i for i, col in enumerate(columns)}

                    for row in rows:
                        if not row or len(row) < 2:
                            continue

                        ticker = str(row[col_map.get("secid", 0)]).strip() if "secid" in col_map else ""
                        short_name = str(row[col_map.get("shortname", 1)]).strip() if "shortname" in col_map else ""
                        isin = str(row[col_map.get("isin", 2)]).strip().upper() if "isin" in col_map and row[col_map["isin"]] else None

                        if not ticker or not short_name:
                            continue
                        if ticker in existing_tickers:
                            continue

                        try:
                            sec = models.Security(
                                ticker=ticker,
                                name=short_name,
                                short_name=short_name,
                                security_type=sec_type,
                                isin=isin,
                                exchange="MOEX",
                            )
                            db.add(sec)
                            existing_tickers.add(ticker)
                            added += 1
                        except Exception as e:
                            logger.debug(f"Error adding {ticker}: {e}")

                    start += len(rows)
                    logger.info(f"Loaded {len(rows)} from {group_name} (total: {total}, start: {start})")

                    await asyncio.sleep(0.3)  # Rate limit

                except Exception as e:
                    logger.error(f"Error loading {group_name} at {start}: {e}")
                    break

    if added > 0:
        db.commit()

    logger.info(f"Total new securities added: {added}")
    return added


def ensure_currency_securities(db: Session) -> int:
    """Ensure 5 major currency securities exist in the database."""
    from .services.cbr_service import CURRENCY_INFO

    currencies = [
        {"ticker": "RUB", "name_ru": "Российский рубль", "name_en": "Russian Ruble"},
        {"ticker": "USD", "name_ru": "Доллар США", "name_en": "US Dollar"},
        {"ticker": "EUR", "name_ru": "Евро", "name_en": "Euro"},
        {"ticker": "CNY", "name_ru": "Китайский юань", "name_en": "Chinese Yuan"},
        {"ticker": "AED", "name_ru": "Дирхам ОАЭ", "name_en": "UAE Dirham"},
    ]

    existing = {s.ticker for s in db.query(models.Security).all()}
    added = 0

    for c in currencies:
        if c["ticker"] not in existing:
            sec = models.Security(
                ticker=c["ticker"],
                name=c["name_ru"],
                short_name=c["name_en"],
                security_type="currency",
                currency=c["ticker"],
                lot_size=1,
                exchange="CBR",
            )
            db.add(sec)
            existing.add(c["ticker"])
            added += 1
            logger.info(f"Added currency security: {c['ticker']} - {c['name_ru']}")

    if added > 0:
        db.commit()
        logger.info(f"Added {added} currency securities")
    else:
        logger.info("All currency securities already exist")

    return added


async def main():
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        added = await load_all_securities(db)
        added += ensure_currency_securities(db)
        print(f"✅ Added {added} new securities (including currencies)")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
