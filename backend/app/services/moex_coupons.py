import httpx
import logging
from typing import List, Dict, Optional
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session

from .cache_service import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"


def extrapolate_future_coupons(rows_data: List[Dict], max_years: int = 2) -> List[Dict]:
    """Extrapolate future coupon dates based on the pattern of last known coupons."""
    if not rows_data:
        return []
    
    sorted_rows = sorted(rows_data, key=lambda r: r.get("coupon_date", ""))
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
        return future_coupons
    
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


async def get_coupons_for_ticker(db: Session, ticker: str, extrapolate: bool = True, force_refresh: bool = False) -> List[Dict]:
    """
    Fetch coupon schedule for a bond/OFZ from MOEX ISS API with caching.
    """
    # Пытаемся получить из кеша
    if not force_refresh:
        cached = get_cached_data(db, ticker, 'coupons')
        if cached is not None:
            logger.debug(f"Using cached coupons for {ticker}")
            return cached

    # Если нет в кеше или нужно обновить - запрашиваем из MOEX
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
                col_map = {col.lower(): i for i, col in enumerate(columns)}
                
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
                    
                    # ✅ Обрабатываем дату - приводим к строке
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
                    })

                if result:
                    if extrapolate:
                        future = extrapolate_future_coupons(result)
                        result.extend(future)
                    
                    # Сохраняем в кеш
                    set_cached_data(db, ticker, 'coupons', result)
                    return result

            except Exception as e:
                logger.debug(f"MOEX coupons fetch error for {ticker} on {url}: {e}")
                continue

        return []


async def get_portfolio_coupons(db: Session, portfolio_id: int, upcoming_only: bool = False, force_refresh: bool = False) -> List[Dict]:
    """
    Get all coupons for OFZ/bond securities in a portfolio.
    """
    from .. import crud

    securities = crud.get_portfolio_securities(db, portfolio_id)
    today = date.today()
    all_coupons = []

    print(f"📊 get_portfolio_coupons: portfolio_id={portfolio_id}, securities={len(securities)}")

    for sec in securities:
        if sec.security_type not in ("bond", "ofz"):
            print(f"   ⏭️ {sec.ticker}: не bond/ofz (тип={sec.security_type})")
            continue
        
        quantity = getattr(sec, "quantity", 0)
        print(f"   🔍 {sec.ticker}: проверяем купоны, quantity={quantity}")

        try:
            coupons = await get_coupons_for_ticker(db, sec.ticker, force_refresh=force_refresh)
            print(f"   ✅ {sec.ticker}: получено {len(coupons)} купонов")

            for coup in coupons:
                try:
                    # ✅ Обрабатываем дату - приводим к строке
                    coupon_date_str = coup["coupon_date"]
                    if isinstance(coupon_date_str, datetime):
                        coupon_date_str = coupon_date_str.strftime("%Y-%m-%d")
                    coup_date = datetime.strptime(coupon_date_str, "%Y-%m-%d").date()
                except (ValueError, TypeError) as e:
                    print(f"   ⚠️ Ошибка парсинга даты для {sec.ticker}: {e}")
                    continue

                if upcoming_only and coup_date < today:
                    continue

                value_per_bond = coup.get("value_rub", coup.get("value", 0))
                if value_per_bond == 0:
                    continue

                total_expected = value_per_bond * quantity

                all_coupons.append({
                    "ticker": sec.ticker,
                    "name": sec.name,
                    "isin": coup.get("isin", ""),
                    "coupon_date": coup_date.strftime("%Y-%m-%d"),
                    "record_date": str(coup.get("record_date", "")),
                    "value_per_bond": value_per_bond,
                    "facevalue": coup.get("facevalue", 1000),
                    "quantity": quantity,
                    "total_expected": total_expected,
                })
        except Exception as e:
            print(f"   ❌ Ошибка для {sec.ticker}: {e}")
            continue

    print(f"📊 Итоговое количество купонов: {len(all_coupons)}")
    all_coupons.sort(key=lambda x: x["coupon_date"], reverse=True)
    return all_coupons