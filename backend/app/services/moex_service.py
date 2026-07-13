import httpx
import logging
import asyncio
from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"


async def get_current_price(ticker: str, isin: Optional[str] = None, security_type: Optional[str] = None) -> Optional[float]:
    """
    Fetch current market price for a security from MOEX ISS API.
    Uses correct market type based on security type.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Determine market and board based on security type
        market = "shares"
        board = "TQBR"
        
        if security_type in ("bond", "ofz"):
            market = "bonds"
            board = "TQOB"
        elif security_type == "etf":
            market = "shares"
            board = "TQTF"
        
        # Try the correct market with standard fields
        url = f"{MOEX_BASE}/engines/stock/markets/{market}/boards/{board}/securities/{ticker}.json"
        params = {"iss.meta": "off", "marketdata.columns": "SECID,LAST,LCURRENTPRICE,VALUTYPE"}

        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                market_data = data.get("marketdata", {})
                columns = market_data.get("columns", [])
                rows = market_data.get("data", [])

                for row in rows:
                    entry = dict(zip(columns, row))
                    # Try LAST first, then LCURRENTPRICE
                    price = entry.get("LAST") or entry.get("LCURRENTPRICE")
                    if price is not None:
                        return float(price)

                # For bonds/OFZ, also check securities table for current face value
                sec_data = data.get("securities", {})
                sec_cols = sec_data.get("columns", [])
                sec_rows = sec_data.get("data", [])
                for row in sec_rows:
                    entry = dict(zip(sec_cols, row))
                    price = entry.get("PREVPRICE") or entry.get("PREVLEGALCLOSEPRICE")
                    if price is not None:
                        return float(price)
                       
        except Exception as e:
            logger.debug(f"Price fetch error for {ticker} on {market}/{board}: {e}")

        # Fallback: try TQBR board for all types
        if market != "shares":
            try:
                url = f"{MOEX_BASE}/engines/stock/markets/shares/boards/TQBR/securities/{ticker}.json"
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    market_data = data.get("marketdata", {})
                    columns = market_data.get("columns", [])
                    for row in market_data.get("data", []):
                        entry = dict(zip(columns, row))
                        price = entry.get("LAST") or entry.get("LCURRENTPRICE")
                        if price is not None:
                            return float(price)
            except:
                pass

        # Fallback: try by ISIN
        if isin:
            try:
                url = f"{MOEX_BASE}/securities/{isin}.json"
                resp = await client.get(url, params={"iss.meta": "off"})
                if resp.status_code == 200:
                    data = resp.json()
                    # Check description for FACEVALUE (bonds/OFZ)
                    desc = data.get("description", {})
                    cols = desc.get("columns", [])
                    for row in desc.get("data", []):
                        entry = dict(zip(cols, row))
                        if entry.get("name") == "FACEVALUE" and entry.get("value"):
                            return float(entry["value"])
            except:
                pass

        return None


async def refresh_all_prices(db: Session) -> int:
    """Refresh current prices for all securities from MOEX API"""
    from .. import models

    securities = db.query(models.Security).all()
    updated = 0

    logger.info(f"Refreshing prices for {len(securities)} securities...")

    for sec in securities:
        try:
            price = await get_current_price(sec.ticker, sec.isin, sec.security_type)
            if price is not None:
                sec.current_price = price
                sec.price_updated_at = datetime.utcnow()
                updated += 1

            await asyncio.sleep(0.15)  # Rate limiting
        except Exception as e:
            logger.error(f"Error refreshing price for {sec.ticker}: {e}")
            continue

    db.commit()
    logger.info(f"Updated prices for {updated}/{len(securities)} securities")
    return updated