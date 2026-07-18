import httpx
import logging
import asyncio
from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from .cache_service import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"
OFZ_FACE_VALUE = 1000.0


async def get_current_price(db: Session, ticker: str, isin: Optional[str] = None, security_type: Optional[str] = None, force_refresh: bool = False) -> Optional[float]:
    """
    Fetch current market price for a security from MOEX ISS API with caching.
    """
    if not force_refresh:
        cached = get_cached_data(db, ticker, 'price')
        if cached is not None and len(cached) > 0:
            logger.debug(f"Using cached price for {ticker}")
            return cached[0].get('price')

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Для ОФЗ используем прямой запрос к securities с PREVPRICE
        if security_type in ("bond", "ofz"):
            url = f"{MOEX_BASE}/engines/stock/markets/bonds/boards/TQOB/securities/{ticker}.json?iss.meta=off&securities.columns=SECID,PREVPRICE,LAST,FACEVALUE"
            
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    sec_data = data.get("securities", {})
                    columns = sec_data.get("columns", [])
                    rows = sec_data.get("data", [])
                    
                    for row in rows:
                        entry = dict(zip(columns, row))
                        price = entry.get("PREVPRICE") or entry.get("LAST")
                        if price is not None:
                            try:
                                price_percent = float(price)
                                if price_percent > 0:
                                    # PREVPRICE/LAST для облигаций — это процент от номинала.
                                    # Реальная цена в рублях = процент / 100 * номинал.
                                    try:
                                        face_value = float(entry.get("FACEVALUE") or 0)
                                    except (ValueError, TypeError):
                                        face_value = 0
                                    if face_value <= 0:
                                        face_value = 1000.0  # значение по умолчанию
                                    price_rub = price_percent / 100.0 * face_value
                                    set_cached_data(db, ticker, 'price', [{'price': price_rub}], ttl_minutes=5)
                                    print(f"✅ Получена цена для ОФЗ {ticker}: {price_rub} ₽ ({price_percent}% от номинала {face_value})")
                                    logger.info(f"✅ Получена цена для ОФЗ {ticker}: {price_rub} ₽ ({price_percent}% от номинала {face_value})")
                                    return price_rub
                            except Exception as e:
                                print(f"⚠️ Ошибка конвертации цены для {ticker}: {e}")
                                logger.warning(f"⚠️ Ошибка конвертации цены для {ticker}: {e}")
                else:
                    print(f"⚠️ MOEX вернул {resp.status_code} для {ticker}")
                    logger.warning(f"⚠️ MOEX вернул {resp.status_code} для {ticker}")
                    
            except Exception as e:
                print(f"⚠️ Ошибка запроса для {ticker}: {e}")
                logger.warning(f"⚠️ Ошибка запроса для {ticker}: {e}")

        # Для акций/ETF
        else:
            market = "shares"
            board = "TQBR"
            if security_type == "etf":
                board = "TQTF"
            url = f"{MOEX_BASE}/engines/stock/markets/{market}/boards/{board}/securities/{ticker}.json?iss.meta=off&marketdata.columns=SECID,LAST,LCURRENTPRICE"
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    market_data = data.get("marketdata", {})
                    columns = market_data.get("columns", [])
                    rows = market_data.get("data", [])
                    for row in rows:
                        entry = dict(zip(columns, row))
                        price = entry.get("LAST") or entry.get("LCURRENTPRICE")
                        if price is not None:
                            try:
                                price_float = float(price)
                                if price_float > 0:
                                    set_cached_data(db, ticker, 'price', [{'price': price_float}], ttl_minutes=5)
                                    print(f"✅ Получена цена для {ticker}: {price_float}")
                                    logger.info(f"✅ Получена цена для {ticker}: {price_float}")
                                    return price_float
                            except:
                                pass
                    # Если цена не найдена в marketdata, пробуем securities с PREVPRICE
                    sec_data = data.get("securities", {})
                    sec_columns = sec_data.get("columns", [])
                    sec_rows = sec_data.get("data", [])
                    for row in sec_rows:
                        entry = dict(zip(sec_columns, row))
                        price = entry.get("PREVPRICE") or entry.get("LAST")
                        if price is not None:
                            try:
                                price_float = float(price)
                                if price_float > 0:
                                    set_cached_data(db, ticker, 'price', [{'price': price_float}], ttl_minutes=5)
                                    print(f"✅ Получена цена для {ticker} (securities): {price_float}")
                                    logger.info(f"✅ Получена цена для {ticker} (securities): {price_float}")
                                    return price_float
                            except:
                                pass
            except Exception as e:
                print(f"❌ Ошибка запроса для {ticker}: {e}")
                logger.debug(f"Error getting price for {ticker}: {e}")

            # Если не получили цену с TQBR, пробуем TQBD (для депозитарных расписок)
            if security_type != "etf":
                try:
                    url2 = f"{MOEX_BASE}/engines/stock/markets/{market}/boards/TQBD/securities/{ticker}.json?iss.meta=off&marketdata.columns=SECID,LAST,LCURRENTPRICE"
                    resp2 = await client.get(url2)
                    if resp2.status_code == 200:
                        data2 = resp2.json()
                        market_data2 = data2.get("marketdata", {})
                        columns2 = market_data2.get("columns", [])
                        rows2 = market_data2.get("data", [])
                        for row in rows2:
                            entry = dict(zip(columns2, row))
                            price = entry.get("LAST") or entry.get("LCURRENTPRICE")
                            if price is not None:
                                try:
                                    price_float = float(price)
                                    if price_float > 0:
                                        set_cached_data(db, ticker, 'price', [{'price': price_float}], ttl_minutes=5)
                                        print(f"✅ Получена цена для {ticker} с TQBD: {price_float}")
                                        return price_float
                                except:
                                    pass
                        # Пробуем securities с PREVPRICE для TQBD
                        sec_data2 = data2.get("securities", {})
                        sec_columns2 = sec_data2.get("columns", [])
                        sec_rows2 = sec_data2.get("data", [])
                        for row in sec_rows2:
                            entry = dict(zip(sec_columns2, row))
                            price = entry.get("PREVPRICE") or entry.get("LAST")
                            if price is not None:
                                try:
                                    price_float = float(price)
                                    if price_float > 0:
                                        set_cached_data(db, ticker, 'price', [{'price': price_float}], ttl_minutes=5)
                                        print(f"✅ Получена цена для {ticker} с TQBD/securities: {price_float}")
                                        return price_float
                                except:
                                    pass
                except Exception as e:
                    print(f"❌ Ошибка запроса TQBD для {ticker}: {e}")
                    logger.debug(f"Error getting price from TQBD for {ticker}: {e}")

        # Для валют (currency) берём официальный курс ЦБ РФ
        if security_type == "currency":
            try:
                from .cbr_service import fetch_cbr_rates
                rates = await fetch_cbr_rates()
                rate = rates.get(ticker)
                if rate is not None and rate > 0:
                    set_cached_data(db, ticker, 'price', [{'price': rate}], ttl_minutes=60 * 24)
                    print(f"✅ Курс ЦБ для {ticker}: {rate}")
                    logger.info(f"✅ Курс ЦБ для {ticker}: {rate}")
                    return rate
            except Exception as e:
                print(f"❌ Ошибка получения курса ЦБ для {ticker}: {e}")
                logger.debug(f"Error getting CBR rate for {ticker}: {e}")

        print(f"❌ Не удалось получить цену для {ticker}")
        logger.warning(f"❌ Не удалось получить цену для {ticker}")
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

    print(f"🔄 Обновляем цены для {len(securities)} бумаг в портфеле...")
    logger.info(f"🔄 Обновляем цены для {len(securities)} бумаг в портфеле...")

    for sec in securities:
        try:
            if sec.security_type in ("bond", "ofz"):
                print(f"🔍 Обновляем цену для ОФЗ {sec.ticker}")
                logger.info(f"🔍 Обновляем цену для ОФЗ {sec.ticker}")
            
            price = await get_current_price(db, sec.ticker, sec.isin, sec.security_type, force_refresh=True)
            if price is not None and price > 0:
                sec.current_price = price
                sec.price_updated_at = datetime.utcnow()
                updated += 1
                print(f"✅ Цена обновлена для {sec.ticker}: {price}")
                logger.info(f"✅ Цена обновлена для {sec.ticker}: {price}")
            else:
                print(f"❌ Не удалось получить цену для {sec.ticker}")
                logger.warning(f"❌ Не удалось получить цену для {sec.ticker}")

            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"❌ Ошибка обновления для {sec.ticker}: {e}")
            continue

    db.commit()
    print(f"✅ Обновлены цены для {updated}/{len(securities)} бумаг в портфеле")
    logger.info(f"✅ Обновлены цены для {updated}/{len(securities)} бумаг в портфеле")
    return updated