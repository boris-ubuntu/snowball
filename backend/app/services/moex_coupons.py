import httpx
import logging
from typing import List, Dict, Optional
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"

# OFZ typical coupon periods
OFZ_COUPON_PERIODS = {
    "262": 183,  # OFZ-PD: semi-annual (~183 days)
    "290": 183,  # OFZ-PK: semi-annual
    "460": 183,  # OFZ-AD: semi-annual
    "520": 365,  # OFZ-IN: annual
}


def extrapolate_future_coupons(rows_data: List[Dict], max_years: int = 2) -> List[Dict]:
    """Extrapolate future coupon dates based on the pattern of last known coupons."""
    if not rows_data:
        return []
    
    # Sort by coupon_date ascending
    sorted_rows = sorted(rows_data, key=lambda r: r.get("coupon_date", ""))
    
    today = date.today()
    
    # Separate past and future coupons
    past_coupons = []
    future_coupons = []
    
    for row in sorted_rows:
        try:
            cd = datetime.strptime(row["coupon_date"], "%Y-%m-%d").date()
            if cd >= today:
                future_coupons.append(row)
            else:
                past_coupons.append(row)
        except (ValueError, TypeError):
            continue
    
    # If we already have future coupons, return them
    if future_coupons:
        return future_coupons
    
    # Need to extrapolate: calculate coupon period from last known dates
    if len(past_coupons) >= 2:
        last = past_coupons[-1]
        prev = past_coupons[-2]
        try:
            last_date = datetime.strptime(last["coupon_date"], "%Y-%m-%d").date()
            prev_date = datetime.strptime(prev["coupon_date"], "%Y-%m-%d").date()
            period_days = (last_date - prev_date).days
        except:
            period_days = 183  # default semi-annual
    
    elif len(past_coupons) == 1:
        period_days = 183  # default semi-annual
        try:
            last_date = datetime.strptime(past_coupons[-1]["coupon_date"], "%Y-%m-%d").date()
        except:
            return []
    else:
        return []
    
    # Extrapolate forward
    coupon_value = float(past_coupons[-1].get("value_rub") or past_coupons[-1].get("value", 0))
    if coupon_value == 0:
        return []
    
    result = []
    next_date = last_date
    limit = today + timedelta(days=max_years * 365)
    
    while next_date <= limit:
        next_date += timedelta(days=period_days)
        if next_date >= today:
            row_copy = dict(past_coupons[-1])
            row_copy["coupon_date"] = next_date.strftime("%Y-%m-%d")
            row_copy["record_date"] = (next_date - timedelta(days=1)).strftime("%Y-%m-%d")
            row_copy["is_extrapolated"] = True
            result.append(row_copy)
    
    return result


async def get_coupons_for_ticker(ticker: str, extrapolate: bool = True) -> List[Dict]:
    """
    Fetch coupon schedule for a bond/OFZ from MOEX ISS bondization API.
    Returns list of dicts with keys: ticker, isin, coupon_date, record_date, value, value_rub, facevalue
    If extrapolate=True, also projects future coupons beyond what MOEX returns.
    """
    url = f"{MOEX_BASE}/securities/{ticker}/bondization.json"
    params = {"iss.meta": "off"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.debug(f"MOEX bondization error for {ticker}: HTTP {resp.status_code}")
                return []

            data = resp.json()
            coupons_data = data.get("coupons", {})
            columns = coupons_data.get("columns", [])
            rows = coupons_data.get("data", [])

            if not rows:
                return []

            result = []
            for row in rows:
                entry = {}
                for i, col in enumerate(columns):
                    if i < len(row):
                        entry[col.lower()] = row[i]

                coupon_date = str(entry.get("coupondate", ""))
                record_date = str(entry.get("recorddate", ""))
                value = entry.get("value", 0)
                value_rub = entry.get("value_rub", 0)
                facevalue = entry.get("facevalue", 0) or entry.get("initialfacevalue", 0)

                if not coupon_date:
                    continue

                result.append({
                    "ticker": entry.get("secid", ticker),
                    "isin": entry.get("isin", ""),
                    "name": entry.get("name", ""),
                    "coupon_date": coupon_date,
                    "record_date": record_date,
                    "value": float(value) if value else 0,
                    "value_rub": float(value_rub) if value_rub else 0,
                    "facevalue": float(facevalue) if facevalue else 1000,
                })

            # Extrapolate future coupons beyond MOEX data
            if extrapolate:
                future = extrapolate_future_coupons(result)
                result.extend(future)

            return result

        except Exception as e:
            logger.error(f"MOEX coupons fetch error for {ticker}: {e}")
            return []


async def get_portfolio_coupons(db: Session, portfolio_id: int, upcoming_only: bool = False) -> List[Dict]:
    """
    Get all coupons for OFZ/bond securities in a portfolio.
    Sorted by coupon_date descending (most recent first).
    If upcoming_only=True, only includes coupons with coupon_date >= today.
    """
    from .. import crud

    securities = crud.get_portfolio_securities(db, portfolio_id)
    today = date.today()
    all_coupons = []

    for sec in securities:
        # Only fetch for bonds and OFZ
        if sec.security_type not in ("bond", "ofz"):
            continue

        try:
            coupons = await get_coupons_for_ticker(sec.ticker)
            for coup in coupons:
                try:
                    coup_date = datetime.strptime(coup["coupon_date"], "%Y-%m-%d").date()
                    record_date = datetime.strptime(coup["record_date"], "%Y-%m-%d").date() if coup["record_date"] else None
                except (ValueError, TypeError):
                    continue

                if upcoming_only and coup_date < today:
                    continue

                # Calculate coupon value per bond
                value_per_bond = coup.get("value_rub", coup.get("value", 0))
                if value_per_bond == 0:
                    continue

                all_coupons.append({
                    "ticker": sec.ticker,
                    "name": sec.name,
                    "isin": coup.get("isin", ""),
                    "coupon_date": coup["coupon_date"],
                    "record_date": str(coup["record_date"]) if coup.get("record_date") else "",
                    "value_per_bond": value_per_bond,
                    "facevalue": coup.get("facevalue", 1000),
                    "quantity": getattr(sec, "quantity", 0),
                    "total_expected": value_per_bond * getattr(sec, "quantity", 0),
                })
        except Exception as e:
            logger.error(f"Error fetching coupons for {sec.ticker}: {e}")

    all_coupons.sort(key=lambda x: x["coupon_date"], reverse=True)
    return all_coupons