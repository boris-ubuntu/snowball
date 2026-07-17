import httpx
import asyncio
import logging
from typing import Optional
from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal

logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"


async def fetch_board_securities(client: httpx.AsyncClient, market: str, board: str, sec_type: str) -> list:
    """Fetch all securities from a specific board on MOEX."""
    all_rows = []
    start = 0
    limit = 500

    while True:
        url = f"{MOEX_BASE}/engines/stock/markets/{market}/boards/{board}/securities.json"
        params = {
            "iss.meta": "off",
            "securities.columns": "SECID,SHORTNAME,ISIN",
            "securities.limit": limit,
            "securities.start": start,
        }
        try:
            resp = await client.get(url, params=params, timeout=30.0)
            if resp.status_code != 200:
                logger.warning(f"Board {board} returned {resp.status_code}")
                break

            data = resp.json()
            sec_data = data.get("securities", {})
            columns = sec_data.get("columns", [])
            rows = sec_data.get("data", [])

            if not rows:
                break

            col_map = {col: i for i, col in enumerate(columns)}
            for row in rows:
                if not row or len(row) < 2:
                    continue
                ticker = str(row[col_map.get("secid", 0)]).strip() if "secid" in col_map else ""
                short_name = str(row[col_map.get("shortname", 1)]).strip() if "shortname" in col_map else ""
                isin = str(row[col_map.get("isin", 2)]).strip().upper() if "isin" in col_map and row[col_map["isin"]] else None
                if ticker and short_name:
                    all_rows.append({"ticker": ticker, "name": short_name, "isin": isin, "type": sec_type})

            start += len(rows)
            logger.info(f"  {board}: loaded {len(rows)} rows (total so far: {start})")
            await asyncio.sleep(0.2)

        except Exception as e:
            logger.error(f"Error fetching {board}: {e}")
            break

    return all_rows


async def load_all_securities(db: Session) -> int:
    """
    Load all securities from MOEX exchanges:
    - TQBR: акции (обыкновенные и привилегированные)
    - TQOB: облигации / ОФЗ
    - TQTF: ETF / фонды (включая ВИМ ликвидность)
    - TQBD: депозитарные расписки
    - TQOD: облигации (дополнительный список)
    """
    existing_tickers = {s.ticker for s in db.query(models.Security).all()}
    added = 0

    boards = [
        ("shares", "TQBR", "stock"),   # Акции (обычные + привилегированные)
        ("shares", "TQBD", "stock"),   # Депозитарные расписки
        ("bonds", "TQOB", "bond"),     # Облигации / ОФЗ
        ("bonds", "TQOD", "bond"),     # Облигации доп.список
        ("bonds", "TQCB", "bond"),     # Облигации коммерческие
        ("shares", "TQTF", "etf"),     # ETF / БПИФы (включая ВИМ ликвидность)
        ("shares", "TQTE", "etf"),     # Торгуемые ETF
        ("shares", "TQIF", "etf"),     # Интервальные ПИФы
        ("shares", "TQTC", "stock"),   # Третий уровень (ТКС)
        ("shares", "TQLR", "stock"),   # Внесписочные ликвидные
        ("shares", "TQPI", "stock"),   # ПИФы открытые
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for market, board, sec_type in boards:
            logger.info(f"Loading {market}/{board} as {sec_type}...")
            securities = await fetch_board_securities(client, market, board, sec_type)

            for sec in securities:
                ticker = sec["ticker"]
                if ticker in existing_tickers:
                    continue

                # Skip very short names that look like errors
                if len(ticker) < 1:
                    continue

                db.add(models.Security(
                    ticker=ticker,
                    name=sec["name"],
                    short_name=sec["name"],
                    security_type=sec_type,
                    isin=sec["isin"],
                    exchange="MOEX",
                ))
                existing_tickers.add(ticker)
                added += 1

            logger.info(f"Added {len(securities)} securities from {board}")

    if added > 0:
        db.commit()

    logger.info(f"Total new securities added: {added}")
    return added


def ensure_currency_securities(db: Session) -> int:
    """Ensure 5 major currency securities exist in the database."""
    currencies = [
        {"ticker": "RUB", "name_ru": "Российский рубль"},
        {"ticker": "USD", "name_ru": "Доллар США"},
        {"ticker": "EUR", "name_ru": "Евро"},
        {"ticker": "CNY", "name_ru": "Китайский юань"},
        {"ticker": "AED", "name_ru": "Дирхам ОАЭ"},
    ]

    existing = {s.ticker for s in db.query(models.Security).all()}
    added = 0

    for c in currencies:
        if c["ticker"] not in existing:
            db.add(models.Security(
                ticker=c["ticker"],
                name=c["name_ru"],
                short_name=c["name_ru"],
                security_type="currency",
                currency=c["ticker"],
                lot_size=1,
                exchange="CBR",
            ))
            existing.add(c["ticker"])
            added += 1
            logger.info(f"Added currency: {c['ticker']}")

    if added > 0:
        db.commit()
    return added


async def main():
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        added = await load_all_securities(db)
        added += ensure_currency_securities(db)
        print(f"✅ Added {added} new securities")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())