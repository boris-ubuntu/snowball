"""
LQDT Money Market Fund daily accrual service.
Formula: Daily accrual = quantity * current_price * (RUSFAR / 365 - 0.3% / 365)
RUSFAR ≈ CBR key rate (currently 14.25%)
"""
import logging
from datetime import date, datetime
from typing import Optional, List, Dict
from decimal import Decimal
from sqlalchemy.orm import Session

from .. import models, crud
from .cache_service import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)

LQDT_TICKER = "LQDT"
RUSFAR_CACHE_KEY = "RUSFAR_RATE"
CACHE_TTL = 60  # 1 hour

# Fallback: use CBR key rate if RUSFAR fetch fails
DEFAULT_RUSFAR = 14.25  # ~ CBR key rate as of 07.2026
FUND_COMMISSION = 0.30  # 0.3% annual


async def get_rusfar_rate(db: Session) -> float:
    """
    Get current RUSFAR rate.
    RUSFAR ≈ CBR key rate. We fetch from cache or use key rate as proxy.
    Always returns a float (defaults to DEFAULT_RUSFAR on failure).
    """
    try:
        # Try cache first
        cached = get_cached_data(db, RUSFAR_CACHE_KEY, "rusfar")
        if cached is not None and len(cached) > 0:
            rate = cached[0].get("rate")
            if rate is not None:
                logger.debug(f"Using cached RUSFAR: {rate}")
                return float(rate)

        # Fallback to CBR key rate from economy cache
        cached_economy = get_cached_data(db, "ECONOMY", "economy")
        if cached_economy and len(cached_economy) > 0:
            key_rate = cached_economy[0].get("key_rate")
            if key_rate is not None:
                key_rate = float(key_rate)
                # Cache it
                try:
                    set_cached_data(db, RUSFAR_CACHE_KEY, "rusfar", [{"rate": key_rate, "source": "cbr_key_rate"}], ttl_minutes=CACHE_TTL)
                except:
                    pass
                return key_rate
    except Exception as e:
        logger.debug(f"Error getting RUSFAR rate: {e}")

    # Last resort: default
    return DEFAULT_RUSFAR


def get_lqdt_quantity_and_avg_price(db: Session, portfolio_id: int) -> tuple:
    """
    Get LQDT position details from the portfolio.
    Returns (quantity, avg_price, current_price) or (0, 0, 0) if not found.
    """
    positions = crud.get_positions(db, portfolio_id)
    for pos in positions:
        if pos.security and pos.security.ticker == LQDT_TICKER:
            return pos.quantity, pos.avg_price or 0, pos.security.current_price or 0
    return 0, 0, 0


def get_lqdt_transactions(db: Session, portfolio_id: int) -> List[models.Transaction]:
    """
    Get all buy/sell transactions for LQDT in this portfolio.
    """
    security = crud.get_security_by_ticker(db, LQDT_TICKER)
    if not security:
        return []

    return db.query(models.Transaction).filter(
        models.Transaction.portfolio_id == portfolio_id,
        models.Transaction.security_id == security.id,
        models.Transaction.transaction_type.in_(["buy", "sell"]),
    ).order_by(models.Transaction.transaction_date, models.Transaction.id).all()


def get_existing_lqdt_accruals(db: Session, portfolio_id: int) -> set:
    """
    Get set of (date, amount) tuples for already accrued LQDT transactions.
    """
    security = crud.get_security_by_ticker(db, LQDT_TICKER)
    if not security:
        return set()

    accruals = db.query(models.Transaction).filter(
        models.Transaction.portfolio_id == portfolio_id,
        models.Transaction.security_id == security.id,
        models.Transaction.transaction_type == "accrual",
        models.Transaction.notes.like("LQDT daily accrual %"),
    ).all()

    return {(a.transaction_date, round(a.total_amount, 2)) for a in accruals}


async def calculate_lqdt_accruals(db: Session, portfolio_id: int) -> List[Dict]:
    """
    Calculate daily LQDT accruals from purchase date to today.
    Returns list of dicts with date, amount, quantity.
    """
    quantity, avg_price, current_price = get_lqdt_quantity_and_avg_price(db, portfolio_id)
    if quantity <= 0:
        logger.debug("No LQDT position found")
        return []

    # Get all LQDT transactions (buy/sell)
    transactions = get_lqdt_transactions(db, portfolio_id)
    if not transactions:
        logger.debug("No LQDT transactions found")
        return []

    # Build holding periods using FIFO
    # Track buys and sells to determine daily quantity
    # Simplified: use the overall position quantity from the first buy date
    first_buy = min(t.transaction_date for t in transactions if t.transaction_type == "buy")
    today = date.today()

    # Get RUSFAR rate
    rusfar = await get_rusfar_rate(db)
    logger.debug(f"RUSFAR rate: {rusfar}%")

    # Daily rate: RUSFAR / 365 - commission / 365
    daily_rate = (rusfar - FUND_COMMISSION) / 100 / 365  # As decimal

    # Get existing accruals to avoid duplicates
    existing = get_existing_lqdt_accruals(db, portfolio_id)

    # Calculate daily accruals from first buy to today
    # For each day, quantity = position quantity at that time
    # We'll use the FIFO approach to determine daily quantity

    # Build a timeline of quantity changes
    from collections import defaultdict
    from datetime import timedelta

    # Track buy/sell lots
    buys = []  # list of (date, qty, price)
    timeline = defaultdict(float)  # date -> quantity change

    for tx in transactions:
        if tx.transaction_type == "buy":
            timeline[tx.transaction_date] += tx.quantity
        elif tx.transaction_type == "sell":
            timeline[tx.transaction_date] -= tx.quantity

    # Sort dates
    sorted_dates = sorted(timeline.keys())

    new_accruals = []
    current_qty = 0
    current_date = sorted_dates[0] if sorted_dates else today

    # Process each day from first buy to today
    day = current_date
    while day <= today:
        # Apply quantity changes for this day
        if day in timeline:
            current_qty += timeline[day]
            if current_qty < 0:
                current_qty = 0

        if current_qty > 0:
            # Calculate daily accrual
            # Use current_price or avg_price as base
            base_price = current_price if current_price > 0 else avg_price
            daily_amount = current_qty * base_price * daily_rate

            if daily_amount > 0:
                key = (day, round(daily_amount, 2))
                if key not in existing:
                    new_accruals.append({
                        "date": day,
                        "amount": round(daily_amount, 2),
                        "quantity": current_qty,
                        "price": base_price,
                        "daily_rate": daily_rate * 100,  # in percent
                    })

        day += timedelta(days=1)

    logger.debug(f"LQDT: {len(new_accruals)} new daily accruals to create")
    return new_accruals


async def process_lqdt_accruals(db: Session, portfolio_id: int) -> int:
    """
    Create accrual transactions for LQDT daily yield.
    Returns number of new transactions created.
    """
    from .. import schemas

    security = crud.get_security_by_ticker(db, LQDT_TICKER)
    if not security:
        logger.debug("LQDT security not found in database")
        return 0

    accruals = await calculate_lqdt_accruals(db, portfolio_id)
    if not accruals:
        return 0

    created = 0
    for acc in accruals:
        try:
            # Create accrual transaction
            tx = models.Transaction(
                portfolio_id=portfolio_id,
                security_id=security.id,
                transaction_type="accrual",
                quantity=acc["quantity"],
                price=acc["amount"],  # price per total for this day
                total_amount=acc["amount"],
                commission=0,
                transaction_date=acc["date"],
                notes=f"LQDT daily accrual ({acc['daily_rate']:.4f}%)",
            )
            db.add(tx)
            created += 1
        except Exception as e:
            logger.error(f"Error creating LQDT accrual for {acc['date']}: {e}")

    if created > 0:
        db.commit()
        logger.info(f"Created {created} LQDT daily accrual transactions")

    return created


async def get_lqdt_projection(db: Session, portfolio_id: int) -> List[Dict]:
    """
    Get projected LQDT accruals for the next 12 months.
    Extrapolates daily accruals based on current RUSFAR rate.
    Returns list of monthly projections: [{month, year, total, items: [{date, amount}], ...}]
    """
    from collections import defaultdict
    from datetime import timedelta

    quantity, avg_price, current_price = get_lqdt_quantity_and_avg_price(db, portfolio_id)
    if quantity <= 0:
        return []

    # Get RUSFAR rate
    rusfar = await get_rusfar_rate(db)
    daily_rate = (rusfar - FUND_COMMISSION) / 100 / 365
    base_price = current_price if current_price > 0 else avg_price
    daily_amount = quantity * base_price * daily_rate

    if daily_amount <= 0:
        return []

    today = date.today()
    one_year = today + timedelta(days=365)

    # Group by month
    monthly = defaultdict(list)
    day = today + timedelta(days=1)  # Start from tomorrow (future)
    index = 0
    while day <= one_year:
        monthly[(day.year, day.month)].append({
            "date": day.isoformat(),
            "amount": round(daily_amount, 2),
            "ticker": LQDT_TICKER,
            "name": "LQDT Money Market",
            "total_expected": round(daily_amount, 2),
        })
        day += timedelta(days=1)
        index += 1
        # Safety limit
        if index > 400:
            break

    # Build result matching histogram format
    result = []
    for (year, month), items in sorted(monthly.items()):
        total = sum(i["amount"] for i in items)
        result.append({
            "date": date(year, month, 1),
            "total": round(total, 2),
            "items": items,
            "is_lqdt": True,
        })

    return result
