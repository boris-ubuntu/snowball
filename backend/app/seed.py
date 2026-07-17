"""
Database seed script - populates initial data on first run.
Creates default user, portfolio, and loads securities from dump.
"""
import json
import os
from sqlalchemy.orm import Session
from . import models
from .database import SessionLocal
from .auth import get_password_hash

# Look for securities_dump.json in multiple locations
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DUMP_PATH = None
_candidates = [
    os.path.join(_SCRIPT_DIR, "..", "..", "..", "securities_dump.json"),  # project root
    os.path.join(_SCRIPT_DIR, "..", "..", "securities_dump.json"),        # backend/
    os.path.join(_SCRIPT_DIR, "..", "securities_dump.json"),              # app/
    "/app/securities_dump.json",                                          # Docker container
]
for _p in _candidates:
    _resolved = os.path.abspath(_p)
    if os.path.exists(_resolved):
        DUMP_PATH = _resolved
        break


def seed_database(db: Session):
    """Seed the database with initial data if empty."""
    changes = False

    # 1. Create default portfolio if none exists
    portfolio = db.query(models.Portfolio).first()
    if not portfolio:
        portfolio = models.Portfolio(
            name="Основной портфель",
            description="Основной инвестиционный портфель",
        )
        db.add(portfolio)
        db.flush()
        print("✅ Created default portfolio")
        changes = True

    # 2. Load securities from dump if none exist
    existing_count = db.query(models.Security).count()
    if existing_count == 0 and os.path.exists(DUMP_PATH):
        try:
            with open(DUMP_PATH, "r", encoding="utf-8") as f:
                securities_data = json.load(f)

            added = 0
            for sec_data in securities_data:
                # Check if already exists
                existing = db.query(models.Security).filter(
                    models.Security.ticker == sec_data["ticker"]
                ).first()
                if existing:
                    continue

                security = models.Security(
                    ticker=sec_data["ticker"],
                    name=sec_data.get("name", sec_data["ticker"]),
                    short_name=sec_data.get("short_name"),
                    security_type=sec_data.get("security_type", "stock"),
                    lot_size=sec_data.get("lot_size", 1),
                    currency=sec_data.get("currency", "RUB"),
                    isin=sec_data.get("isin"),
                    exchange=sec_data.get("exchange", "MOEX"),
                    current_price=sec_data.get("current_price"),
                )
                db.add(security)
                added += 1

            if added > 0:
                db.flush()
                print(f"✅ Loaded {added} securities from dump")
                changes = True
        except Exception as e:
            print(f"⚠️ Could not load securities dump: {e}")

    # 3. Ensure currency securities exist
    currencies = [
        {"ticker": "RUB", "name": "Российский рубль"},
        {"ticker": "USD", "name": "Доллар США"},
        {"ticker": "EUR", "name": "Евро"},
        {"ticker": "CNY", "name": "Китайский юань"},
        {"ticker": "AED", "name": "Дирхам ОАЭ"},
    ]
    existing_tickers = {s.ticker for s in db.query(models.Security).all()}
    for c in currencies:
        if c["ticker"] not in existing_tickers:
            db.add(models.Security(
                ticker=c["ticker"],
                name=c["name"],
                short_name=c["name"],
                security_type="currency",
                currency=c["ticker"],
                lot_size=1,
                exchange="CBR",
            ))
            existing_tickers.add(c["ticker"])
            print(f"✅ Added currency: {c['ticker']}")
            changes = True

    # 4. Ensure critical securities that may be missing from dump
    critical_securities = [
        # (ticker, name, security_type, isin)
        ("MDMG", "Мать и дитя", "stock", "RU000A106Y64"),
        ("LQDT", "LQDT Ликвидность", "etf", "RU000A108349"),
        ("MOEX", "Московская Биржа", "stock", "RU000A0JR4A3"),
        ("X5", "КЦ ИКС 5", "stock", "RU000A0JP7R0"),
        ("SIBN", "Газпром нефть", "stock", "RU000A0DKXV6"),
        ("RENI", "Ренессанс Страхование", "stock", "RU000A1037V7"),
        ("CNRU", "ЦИАН", "stock", "RU000A101ST3"),
        ("VSEH", "ВсеИнструменты", "stock", "RU000A1058S2"),
        ("GAZP", "Газпром", "stock", "RU0007661625"),
        ("SBERP", "Сбербанк-п", "stock", "RU0009029557"),
        ("VTBR", "Банк ВТБ", "stock", "RU000A0CC5M9"),
        ("TATN", "Татнефть", "stock", "RU0006944147"),
        ("TATNP", "Татнефть-п", "stock", "RU0006944154"),
        ("SNGS", "Сургутнефтегаз", "stock", "RU0009029524"),
        ("SNGSP", "Сургутнефтегаз-п", "stock", "RU0009100027"),
        ("ROSN", "Роснефть", "stock", "RU000A0DKXV6"),
        ("LKOH", "Лукойл", "stock", "RU0009024277"),
        ("NVTK", "Новатэк", "stock", "RU000A0DK0M0"),
        ("YNDX", "Яндекс", "stock", "NL0009805528"),
        ("MGNT", "Магнит", "stock", "RU000A0JKQU8"),
        ("PLZL", "Полюс", "stock", "RU000A0JNA90"),
        ("CHMF", "Северсталь", "stock", "RU0009046510"),
        ("NLMK", "НЛМК", "stock", "RU0009046452"),
        ("MAGN", "ММК", "stock", "RU0009084396"),
        ("RUAL", "Русал", "stock", "RU000A1025V3"),
        ("MTSS", "МТС", "stock", "RU0007775219"),
        ("AFKS", "Система", "stock", "RU000A0DQZE3"),
        ("HYDR", "РусГидро", "stock", "RU000A0JP0H0"),
        ("IRAO", "Интер РАО", "stock", "RU000A0JPNM1"),
        ("UPRO", "Юнипро", "stock", "RU000A0JSqA0"),
        ("RTKM", "Ростелеком", "stock", "RU0008943394"),
        ("FEES", "ФСК ЕЭС", "stock", "RU000A0JPLG3"),
        ("AFLT", "Аэрофлот", "stock", "RU0009062285"),
        ("BANE", "Башнефть", "stock", "RU0007976957"),
        ("BANEP", "Башнефть-п", "stock", "RU0007976965"),
        ("TRNFP", "Транснефть-п", "stock", "RU0009091573"),
        ("PIKK", "ПИК", "stock", "RU000A0JP7P4"),
        ("PHOR", "ФосАгро", "stock", "RU000A0JR5A8"),
        ("AKRN", "Акрон", "stock", "RU0009028674"),
        ("BELU", "НоваБев", "stock", "RU000A0HL5M1"),
    ]
    for ticker, name, sec_type, isin in critical_securities:
        if ticker not in existing_tickers:
            db.add(models.Security(
                ticker=ticker,
                name=name,
                short_name=name,
                security_type=sec_type,
                isin=isin,
                exchange="MOEX",
                lot_size=1,
                currency="RUB",
            ))
            existing_tickers.add(ticker)
            print(f"✅ Added critical security: {ticker} - {name}")
            changes = True

    if changes:
        db.commit()
        print("✅ Database seeded successfully")
    else:
        print("ℹ️ Database already has data, skipping seed")


def run_seed():
    """Run seed in a separate function for startup."""
    try:
        db = SessionLocal()
        seed_database(db)
        db.close()
    except Exception as e:
        print(f"⚠️ Seed error: {e}")