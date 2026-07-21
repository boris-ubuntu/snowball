import asyncio
import httpx
import logging
from typing import List, Dict, Optional
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"


def extrapolate_future_coupons(rows_data: List[Dict], max_years: int = 2) -> List[Dict]:
    """Extrapolate future coupon dates based on the pattern of last known coupons.
    Accounts for amortizations: after an amortization date, the facevalue decreases,
    so the coupon value is proportionally reduced."""
    if not rows_data:
        return []

    all_coupons = [r for r in rows_data if not r.get("is_amortization")]
    amortizations = [r for r in rows_data if r.get("is_amortization")]

    sorted_rows = sorted(all_coupons, key=lambda r: r.get("coupon_date", ""))
    today = date.today()

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

    if future_coupons:
        if future_coupons and amortizations:
            last_future_date = datetime.strptime(future_coupons[-1]["coupon_date"], "%Y-%m-%d").date()
            future_amorts = [a for a in amortizations
                             if datetime.strptime(a["coupon_date"], "%Y-%m-%d").date() > last_future_date]
            if not future_amorts:
                return []
            # If MOEX has some future coupons but not all (floating bonds), 
            # do not extrapolate — floating bonds have variable rates that MOEX cannot predict.
            # Detect floating: last future coupon value is close to last past coupon (floating estimate)
            if past_coupons and future_coupons:
                last_past_val = float(past_coupons[-1].get("value_rub", past_coupons[-1].get("value", 0)))
                first_future_val = float(future_coupons[0].get("value_rub", future_coupons[0].get("value", 0)))
                last_future_val = float(future_coupons[-1].get("value_rub", future_coupons[-1].get("value", 0)))
                # If future coupons all have same value and match past, it's fixed rate — extrapolate
                # If future values differ from past, it's floating — skip extrapolation
                if abs(last_future_val - first_future_val) < 0.01 and abs(first_future_val - last_past_val) > 0.01:
                    return []
        else:
            return []

    if len(past_coupons) >= 2:
        last = past_coupons[-1]
        prev = past_coupons[-2]
        try:
            last_date = datetime.strptime(last["coupon_date"], "%Y-%m-%d").date()
            prev_date = datetime.strptime(prev["coupon_date"], "%Y-%m-%d").date()
            period_days = (last_date - prev_date).days
        except:
            period_days = 183
    elif len(past_coupons) == 1:
        period_days = 183
        try:
            last_date = datetime.strptime(past_coupons[-1]["coupon_date"], "%Y-%m-%d").date()
        except:
            return []
    else:
        return []

    # If there are future coupons from MOEX, start extrapolation after the last one
    if future_coupons:
        last_future_date = datetime.strptime(future_coupons[-1]["coupon_date"], "%Y-%m-%d").date()
        if last_future_date > last_date:
            last_date = last_future_date

    amort_timeline = {}
    for am in amortizations:
        try:
            ad = datetime.strptime(am["coupon_date"], "%Y-%m-%d").date()
            fv = float(am.get("facevalue", 0))
            if fv > 0:
                amort_timeline[ad] = fv
        except:
            pass

    last_facevalue = float(past_coupons[-1].get("facevalue", 1000))
    if last_facevalue <= 0:
        last_facevalue = 1000

    coupon_value = float(past_coupons[-1].get("value_rub") or past_coupons[-1].get("value", 0))
    if coupon_value == 0:
        return []

    result = []
    next_date = last_date
    limit = today + timedelta(days=max_years * 365)
    current_facevalue = last_facevalue
    base_coupon_value = coupon_value

    while next_date <= limit:
        next_date += timedelta(days=period_days)
        if next_date >= today:
            for am_date, new_fv in sorted(amort_timeline.items()):
                if am_date <= next_date:
                    ratio = new_fv / current_facevalue if current_facevalue > 0 else 1.0
                    base_coupon_value = base_coupon_value * ratio
                    current_facevalue = new_fv
            amort_timeline = {k: v for k, v in amort_timeline.items() if k > next_date}

            if base_coupon_value <= 0:
                break

            row_copy = dict(past_coupons[-1])
            row_copy["coupon_date"] = next_date.strftime("%Y-%m-%d")
            row_copy["record_date"] = (next_date - timedelta(days=1)).strftime("%Y-%m-%d")
            row_copy["value"] = round(base_coupon_value, 2)
            row_copy["value_rub"] = round(base_coupon_value, 2)
            row_copy["facevalue"] = current_facevalue
            row_copy["is_extrapolated"] = True
            result.append(row_copy)

    return result


async def get_coupons_for_ticker(ticker: str, extrapolate: bool = True) -> List[Dict]:
    """Fetch coupon schedule AND amortizations for a bond/OFZ from MOEX ISS API."""
    urls_to_try = [
        f"{MOEX_BASE}/securities/{ticker}/bondization.json",
        f"{MOEX_BASE}/engines/stock/markets/bonds/boards/TQOB/securities/{ticker}.json",
        f"{MOEX_BASE}/securities/{ticker}.json",
    ]
    params = {"iss.meta": "off"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        for url in urls_to_try:
            try:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    continue

                data = resp.json()

                coupons_data = None
                columns = []
                rows = []

                if "coupons" in data:
                    coupons_data = data.get("coupons", {})
                    columns = coupons_data.get("columns", [])
                    rows = coupons_data.get("data", [])

                if not rows and "marketdata" in data:
                    market_data = data.get("marketdata", {})
                    columns = market_data.get("columns", [])
                    rows = market_data.get("data", [])

                if not rows and "securities" in data:
                    sec_data = data.get("securities", {})
                    columns = sec_data.get("columns", [])
                    rows = sec_data.get("data", [])

                if not rows and "description" in data:
                    desc_data = data.get("description", {})
                    columns = desc_data.get("columns", [])
                    rows = desc_data.get("data", [])

                if not rows:
                    continue

                result = []

                for row in rows:
                    entry = {}
                    for i, col in enumerate(columns):
                        if i < len(row):
                            entry[col.lower()] = row[i]

                    coupon_date = (entry.get("coupondate") or
                                  entry.get("recorddate") or
                                  entry.get("nextcoupondate") or
                                  entry.get("matdate") or
                                  "")
                    if not coupon_date:
                        continue

                    if isinstance(coupon_date, datetime):
                        coupon_date = coupon_date.strftime("%Y-%m-%d")

                    value = entry.get("value_rub") or entry.get("value") or entry.get("couponvalue") or 0
                    try:
                        value_float = float(value) if value else 0
                    except:
                        value_float = 0

                    if value_float == 0:
                        continue

                    facevalue = (entry.get("facevalue") or
                                entry.get("initialfacevalue") or
                                entry.get("facevalue") or
                                1000)
                    try:
                        facevalue_float = float(facevalue) if facevalue else 1000
                    except:
                        facevalue_float = 1000

                    result.append({
                        "ticker": entry.get("secid", ticker),
                        "isin": entry.get("isin", ""),
                        "name": entry.get("name") or entry.get("shortname", ""),
                        "coupon_date": str(coupon_date),
                        "record_date": str(entry.get("recorddate", "")),
                        "value": value_float,
                        "value_rub": value_float,
                        "facevalue": facevalue_float,
                        "is_amortization": False,
                    })

                if "amortizations" in data:
                    amort_data = data.get("amortizations", {})
                    amort_cols = amort_data.get("columns", [])
                    amort_rows = amort_data.get("data", [])
                    for row in amort_rows:
                        entry = {}
                        for i, col in enumerate(amort_cols):
                            if i < len(row):
                                entry[col.lower()] = row[i]
                        amort_date = entry.get("amortdate", "")
                        if not amort_date:
                            continue
                        if isinstance(amort_date, datetime):
                            amort_date = amort_date.strftime("%Y-%m-%d")
                        amort_value = entry.get("value_rub") or entry.get("value") or 0
                        try:
                            amort_float = float(amort_value) if amort_value else 0
                        except:
                            amort_float = 0
                        if amort_float == 0:
                            continue
                        result.append({
                            "ticker": entry.get("secid", ticker),
                            "isin": entry.get("isin", ""),
                            "name": entry.get("name") or "",
                            "coupon_date": str(amort_date),
                            "record_date": str(amort_date),
                            "value": amort_float,
                            "value_rub": amort_float,
                            "facevalue": entry.get("facevalue", 0),
                            "is_amortization": True,
                        })

                if result:
                    if extrapolate:
                        future = extrapolate_future_coupons(result)
                        result.extend(future)

                return result

            except Exception as e:
                logger.debug(f"MOEX coupons fetch error for {ticker} on {url}: {e}")
                continue

        return []


async def get_portfolio_coupons(portfolio_id: int, upcoming_only: bool = False) -> List[Dict]:
    """Get all coupons AND amortizations for OFZ/bond securities in a portfolio (parallel)."""
    from ..database import SessionLocal
    from .. import crud

    db = SessionLocal()
    try:
        securities = crud.get_portfolio_securities(db, portfolio_id)
    finally:
        db.close()

    today = date.today()

    async def _fetch(sec):
        if sec.security_type not in ("bond", "ofz"):
            return []
        quantity = getattr(sec, "quantity", 0)
        if quantity <= 0:
            return []
        try:
            coupons = await get_coupons_for_ticker(sec.ticker)
            result = []
            for coup in coupons:
                try:
                    coupon_date_str = coup["coupon_date"]
                    if isinstance(coupon_date_str, datetime):
                        coupon_date_str = coupon_date_str.strftime("%Y-%m-%d")
                    coup_date = datetime.strptime(coupon_date_str, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue
                if upcoming_only and coup_date < today:
                    continue
                value_per_bond = coup.get("value_rub", coup.get("value", 0))
                if value_per_bond == 0:
                    continue
                is_amort = coup.get("is_amortization", False)
                result.append({
                    "ticker": sec.ticker,
                    "name": sec.name,
                    "isin": coup.get("isin", ""),
                    "coupon_date": coup_date.strftime("%Y-%m-%d"),
                    "record_date": str(coup.get("record_date", "")),
                    "value_per_bond": value_per_bond,
                    "facevalue": coup.get("facevalue", 1000),
                    "quantity": quantity,
                    "total_expected": value_per_bond * quantity,
                    "is_amortization": is_amort,
                })
            return result
        except Exception as e:
            logger.debug(f"Error fetching coupons for {sec.ticker}: {e}")
            return []

    semaphore = asyncio.Semaphore(5)
    async def _fetch_limited(sec):
        async with semaphore:
            return await _fetch(sec)

    results = await asyncio.gather(*[_fetch_limited(sec) for sec in securities])
    all_coupons = [c for batch in results for c in batch]
    all_coupons.sort(key=lambda x: x["coupon_date"], reverse=True)
    return all_coupons