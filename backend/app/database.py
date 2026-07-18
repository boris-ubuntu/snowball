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

    # Migration: create performance indexes for frequent queries.
    # Note: indexes declared with index=True in models.py are already created by
    # Base.metadata.create_all above. Here we only ensure any that may be missing,
    # and we create them one-by-one (each in its own try/except) so a single
    # failure (e.g. a leftover INVALID index from a previously interrupted
    # CONCURRENTLY build) does not abort the rest.
    _index_defs = [
        ("ix_transactions_portfolio_id", "transactions", "portfolio_id"),
        ("ix_transactions_security_id", "transactions", "security_id"),
        ("ix_transactions_transaction_type", "transactions", "transaction_type"),
        ("ix_transactions_transaction_date", "transactions", "transaction_date"),
        ("ix_portfolio_positions_portfolio_id", "portfolio_positions", "portfolio_id"),
        ("ix_portfolio_positions_security_id", "portfolio_positions", "security_id"),
        ("ix_dividends_security_id", "dividends", "security_id"),
        ("ix_dividends_ex_date", "dividends", "ex_date"),
        ("ix_dividends_payment_date", "dividends", "payment_date"),
        ("ix_portfolio_snapshots_portfolio_id", "portfolio_snapshots", "portfolio_id"),
        ("ix_portfolio_snapshots_snapshot_date", "portfolio_snapshots", "snapshot_date"),
    ]
    try:
        db = SessionLocal()
        created = 0
        for idx_name, tbl, cols in _index_defs:
            # Only create if no index with this name already exists in pg_class.
            exists = db.execute(text(
                "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relname = :name AND c.relkind = 'i' LIMIT 1"
            ), {"name": idx_name}).scalar()
            if exists:
                continue
            try:
                db.execute(text(f"CREATE INDEX {idx_name} ON {tbl} ({cols})"))
                created += 1
            except Exception as e:
                print(f"⚠️  Could not create index {idx_name}: {e}")
        db.commit()
        print(f"✅ Migration: ensured performance indexes exist ({created} created)")
    except Exception as e:
        print(f"⚠️  Index migration warning: {e}")
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