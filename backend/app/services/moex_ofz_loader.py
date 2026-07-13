import httpx
import asyncio
import logging
import re
from typing import List, Dict, Optional
from datetime import date
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"


def _parse_secid(row, col_map):
    """Extract secid from a row dict or list"""
    if isinstance(row, dict):
        return row.get("SECID") or row.get("secid", "")
    return str(row[col_map.get("SECID", 0)])


def _parse_value(row, col_map, key, default=""):
    if isinstance(row, dict):
        return row.get(key) or row.get(key.lower(), default)
    idx = col_map.get(key, -1)
    if idx >= 0 and idx < len(row):
        return row[idx]
    idx2 = col_map.get(key.lower(), -1)
    if idx2 >= 0 and idx2 < len(row):
        return row[idx2]
    return default


async def search_moex_security(query: str) -> List[Dict]:
    """Search for a security on MOEX by ticker, name or ISIN"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        url = f"{MOEX_BASE}/securities.json"
        params = {
            "iss.meta": "off",
            "iss.only": "securities",
            "securities.columns": "secid,shortname,name,isin,group",
            "securities.limit": 20,
            "q": query,
        }
        try:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning(f"MOEX search failed: {resp.status_code}")
                return []

            data = resp.json()
            sec_data = data.get("securities", {})
            columns = sec_data.get("columns", [])
            rows = sec_data.get("data", [])

            results = []
            for row in rows:
                entry = {columns[i]: (row[i] if i < len(row) else "") for i in range(len(columns))}
                results.append({
                    "ticker": entry.get("secid", ""),
                    "name": entry.get("name") or entry.get("shortname", ""),
                    "isin": entry.get("isin", ""),
                    "group": entry.get("group", ""),
                })
            return results
        except Exception as e:
            logger.error(f"MOEX search error: {e}")
            return []


async def fetch_security_details(ticker: str) -> Optional[Dict]:
    """Fetch detailed info about a security by ticker"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Try the description endpoint
        url = f"{MOEX_BASE}/securities/{ticker}.json"
        params = {"iss.meta": "off", "iss.only": "description"}
        try:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning(f"MOEX details failed for {ticker}: {resp.status_code}")
                return None

            data = resp.json()
            desc = data.get("description", {})
            columns = desc.get("columns", [])
            rows = desc.get("data", [])

            result = {}
            for row in rows:
                if len(row) >= 3:
                    name = str(row[0]) if row[0] else ""
                    value = str(row[2]) if row[2] else ""
                    result[name] = value

            # Get ISIN if available
            # Also try name/group from securities endpoint
            sec_url = f"{MOEX_BASE}/securities/{ticker}.json"
            sec_params = {"iss.meta": "off", "iss.only": "securities",
                         "securities.columns": "secid,shortname,name,isin,group"}
            try:
                sec_resp = await client.get(sec_url, params=sec_params)
                if sec_resp.status_code == 200:
                    sec_data = sec_resp.json()
                    for sec_rows in sec_data.get("securities", {}).get("data", []):
                        if len(sec_rows) >= 5:
                            result["TICKER"] = sec_rows[0]
                            result["SHORTNAME"] = sec_rows[1] or ""
                            result["NAME"] = sec_rows[2] or sec_rows[1] or ""
                            result["ISIN"] = sec_rows[3] or result.get("ISIN", "")
                            result["GROUP"] = sec_rows[4] or ""
            except:
                pass

            return result
        except Exception as e:
            logger.error(f"Error fetching details for {ticker}: {e}")
            return None


async def load_ofz_bonds(db: Session) -> int:
    """
    Load all OFZ bonds (гособлигации) from MOEX and add them to the DB.
    Scans the TQOB board for securities with secid starting with SU or where name contains "ОФЗ".
    """
    existing_tickers = {s.ticker for s in db.query(models.Security).all()}
    added = 0
    start = 0
    page_size = 100
    total = None

    async with httpx.AsyncClient(timeout=15.0) as client:
        while total is None or start < total:
            url = f"{MOEX_BASE}/engines/stock/markets/bonds/boards/TQOB/securities.json"
            params = {
                "iss.meta": "off",
                "iss.only": "securities",
                "securities.columns": "SECID,SHORTNAME,NAME,ISIN,MATDATE,FACEVALUE",
                "securities.limit": page_size,
                "securities.start": start,
            }

            try:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning(f"MOEX TQOB list failed: {resp.status_code}")
                    break

                data = resp.json()
                sec_data = data.get("securities", {})
                columns = sec_data.get("columns", [])
                rows = sec_data.get("data", [])

                if total is None:
                    total = sec_data.get("total", len(rows))

                # Check for empty columns and handle marketdata format
                if not columns and rows:
                    # Try to detect SECID from marketdata
                    # MOEX returns marketdata with rows but not securities columns
                    # This is a known MOEX quirk — skip this approach
                    logger.info("TQOB API returned empty columns, falling back to securities endpoint")
                    break

                col_map = {col: i for i, col in enumerate(columns)}

                for row in rows:
                    secid = _parse_value(row, col_map, "SECID", "")
                    shortname = _parse_value(row, col_map, "SHORTNAME", "")
                    name = _parse_value(row, col_map, "NAME", shortname)
                    isin = _parse_value(row, col_map, "ISIN", "")

                    if not secid or not name:
                        continue

                    # Check if it's an OFZ (secid starts with SU or name contains ОФЗ)
                    is_ofz = (secid.startswith("SU") or "ОФЗ" in name or "ОФЗ" in shortname)
                    sec_type = "ofz" if is_ofz else "bond"

                    if secid in existing_tickers:
                        continue

                    try:
                        sec = models.Security(
                            ticker=secid,
                            name=name,
                            short_name=shortname,
                            security_type=sec_type,
                            isin=isin or None,
                            exchange="MOEX",
                        )
                        db.add(sec)
                        existing_tickers.add(secid)
                        added += 1
                    except Exception as e:
                        logger.debug(f"Error adding {secid}: {e}")

                start += len(rows)
                logger.info(f"Loaded {len(rows)} bonds from TQOB (total: {total}, start: {start})")
                await asyncio.sleep(0.3)

            except Exception as e:
                logger.error(f"Error loading TQOB at {start}: {e}")
                break

    if added > 0:
        db.commit()

    if added == 0:
        # Fallback: try the general securities endpoint with OFZ bonds
        logger.info("Trying fallback: load OFZ from securities list")
        added = await _load_ofz_from_general_list(db, existing_tickers)

    return added


async def _load_ofz_from_general_list(db: Session, existing_tickers: set) -> int:
    """Fallback: load OFZ via the general securities endpoint filtered by group"""
    added = 0
    page_size = 500

    async with httpx.AsyncClient(timeout=20.0) as client:
        for start in range(0, 2000, page_size):
            url = f"{MOEX_BASE}/securities.json"
            params = {
                "iss.meta": "off",
                "iss.only": "securities",
                "securities.columns": "secid,shortname,name,isin,group",
                "securities.limit": page_size,
                "securities.start": start,
                "group": "stock_bonds",
                "group_by": "group",
                "group_by_filter": "stock_bonds",
            }

            try:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    break

                data = resp.json()
                sec_data = data.get("securities", {})
                columns = sec_data.get("columns", [])
                rows = sec_data.get("data", [])

                if not rows:
                    break

                col_map = {col: i for i, col in enumerate(columns)}

                for row in rows:
                    secid = str(row[col_map.get("secid", 0)]).strip() if len(row) > 0 else ""
                    shortname = str(row[col_map.get("shortname", 1)]).strip() if len(row) > 1 else ""
                    name = str(row[col_map.get("name", 2)]).strip() if len(row) > 2 else shortname
                    isin = str(row[col_map.get("isin", 3)]).strip().upper() if col_map.get("isin", -1) >= 0 and len(row) > 3 and row[col_map["isin"]] else None

                    if not secid or not name:
                        continue

                    # Filter: only OFZ (secid starting with SU or name containing ОФЗ)
                    if not (secid.startswith("SU") or "ОФЗ" in name or "ОФЗ" in shortname):
                        continue

                    if secid in existing_tickers:
                        continue

                    try:
                        sec = models.Security(
                            ticker=secid,
                            name=name,
                            short_name=shortname,
                            security_type="ofz",
                            isin=isin,
                            exchange="MOEX",
                        )
                        db.add(sec)
                        existing_tickers.add(secid)
                        added += 1
                    except Exception as e:
                        logger.debug(f"Error adding {secid}: {e}")

                await asyncio.sleep(0.3)

            except Exception as e:
                logger.error(f"Error in fallback load at {start}: {e}")
                break

    if added > 0:
        db.commit()

    logger.info(f"Total OFZ bonds added: {added}")
    return added