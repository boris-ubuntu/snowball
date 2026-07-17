"""
Script to check and load missing securities from MOEX.
Run inside container: python -m app.check_securities
"""
import asyncio
import httpx
import logging
from app.database import SessionLocal
from app import models
from app.load_moex_securities import load_all_securities, ensure_currency_securities

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com/iss"


async def search_missing_securities():
    """Search for specific known tickers that might be missing from standard boards."""
    # Known tickers that may be on special boards
    known_missing = {
        "NVTK": "Новатэк",
        "MOEX": "Московская Биржа",
        "NOVK": "Новатэк (др)",
        "VTBR": "Банк ВТБ",
        "TATN": "Татнефть",
        "TATNP": "Татнефть-п",
        "SNGS": "Сургутнефтегаз",
        "SNGSP": "Сургутнефтегаз-п",
        "ROSN": "Роснефть",
        "GAZP": "Газпром",
        "LKOH": "Лукойл",
        "YNDX": "Яндекс",
        "DIAS": "Диасофт",
        "SBERP": "Сбербанк-п",
        "MGNT": "Магнит",
        "FIXP": "Fix Price",
        "PLZL": "Полюс",
        "ALRS": "Алроса",
        "CHMF": "Северсталь",
        "NLMK": "НЛМК",
        "MAGN": "ММК",
        "RUAL": "Русал",
        "MTSS": "МТС",
        "AFKS": "Система",
        "TCSG": "TCS Group",
        "HYDR": "РусГидро",
        "IRAO": "Интер РАО",
        "UPRO": "Юнипро",
        "RTKM": "Ростелеком",
        "RSTI": "Россети",
        "FEES": "ФСК ЕЭС",
        "AFLT": "Аэрофлот",
        "BANE": "Башнефть",
        "BANEP": "Башнефть-п",
        "TRNFP": "Транснефть-п",
        "PIKK": "ПИК",
        "PHOR": "ФосАгро",
        "AKRN": "Акрон",
        "LSNG": "Ленэнерго",
        "LSNGP": "Ленэнерго-п",
        "MSNG": "Мосэнерго",
        "MRKS": "МРСК ЦП",
        "MRKZ": "МРСК Волги",
        "MRKV": "МРСК Центра",
        "MRKY": "МРСК Юга",
        "MRKU": "МРСК Урала",
        "MRKS": "МРСК Северо-Запада",
        "MRKP": "МРСК Сибири",
        "MRKC": "МРСК Северного Кавказа",
    }
    
    # First try to load all from MOEX
    db = SessionLocal()
    try:
        existing = {s.ticker for s in db.query(models.Security).all()}
        logger.info(f"Existing securities: {len(existing)}")
        
        missing = []
        for ticker, name in known_missing.items():
            if ticker not in existing:
                missing.append((ticker, name))
                
        if missing:
            logger.info(f"Missing {len(missing)} securities, trying to find them on MOEX...")
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                for ticker, name in missing:
                    try:
                        url = f"{MOEX_BASE}/securities/{ticker}.json?iss.meta=off"
                        resp = await client.get(url, timeout=10.0)
                        if resp.status_code == 200:
                            data = resp.json()
                            desc_data = data.get("description", {})
                            columns = desc_data.get("columns", [])
                            rows = desc_data.get("data", [])
                            if rows:
                                row = rows[0]
                                col_map = {col: i for i, col in enumerate(columns)}
                                shortname = str(row[col_map.get("shortname", len(row)-1)]) if len(row) > 0 else name
                                sectype = "stock"
                                isin = ""
                                if "isin" in col_map and len(row) > col_map["isin"]:
                                    isin = str(row[col_map["isin"]]) or ""
                                
                                # Check if it's a bond or stock
                                for r in rows:
                                    for i, col in enumerate(columns):
                                        if col.lower() == "group" and i < len(r):
                                            if str(r[i]).lower() in ("bond", "ofz"):
                                                sectype = "bond"
                                
                                sec = models.Security(
                                    ticker=ticker,
                                    name=name,
                                    short_name=shortname or name,
                                    security_type=sectype,
                                    isin=isin,
                                    exchange="MOEX",
                                )
                                db.add(sec)
                                logger.info(f"  Added missing: {ticker} - {name}")
                    except Exception as e:
                        logger.debug(f"  Error adding {ticker}: {e}")
            
            db.commit()
            logger.info("Missing securities added!")
        
        # Final count
        total = db.query(models.Security).count()
        logger.info(f"Total securities now: {total}")
        
        # Verify specific ones
        for t in ['NVTK', 'MOEX', 'SBER', 'SBERP']:
            s = db.query(models.Security).filter(models.Security.ticker == t).first()
            if s:
                logger.info(f"  ✓ {t}: {s.name}")
            else:
                logger.warning(f"  ✗ {t}: NOT FOUND")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(search_missing_securities())