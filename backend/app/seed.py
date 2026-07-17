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