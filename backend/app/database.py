from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import text
from .config import settings
from .models import Base

engine = create_engine(settings.DB_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables and apply migrations"""
    Base.metadata.create_all(bind=engine)
    # Migration: add total_accruals column if not exists
    try:
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("ALTER TABLE portfolio_positions ADD COLUMN total_accruals FLOAT NOT NULL DEFAULT 0"))
        db.commit()
        print("✅ Migration: added total_accruals column")
    except Exception:
        pass  # Column already exists
    finally:
        db.close()

    # Migration: add realized_profit column if not exists
    try:
        db = SessionLocal()
        db.execute(text("ALTER TABLE portfolio_positions ADD COLUMN realized_profit FLOAT NOT NULL DEFAULT 0"))
        db.commit()
        print("✅ Migration: added realized_profit column")
    except Exception:
        pass  # Column already exists
    finally:
        db.close()

    # Migration: add dohod_name column to securities if not exists
    try:
        db = SessionLocal()
        db.execute(text("ALTER TABLE securities ADD COLUMN dohod_name VARCHAR(255)"))
        db.commit()
        print("✅ Migration: added dohod_name column to securities")
    except Exception:
        pass  # Column already exists
    finally:
        db.close()


def get_db():
    """Dependency for getting DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection():
    """Check if database is connected"""
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except Exception:
        return False