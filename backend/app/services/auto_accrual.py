import logging
from typing import List, Dict
from datetime import date, datetime
from sqlalchemy.orm import Session

from .moex_dividends import get_portfolio_dividends_all
from .moex_coupons import get_portfolio_coupons
from .lqdt_service import process_lqdt_accruals
from .. import crud, schemas

logger = logging.getLogger(__name__)


async def check_and_process_accruals(db: Session, portfolio_id: int) -> Dict:
    """
    Check historical dividends, coupons, and LQDT daily accruals
    that have not been processed yet.

    Returns summary of what was processed.
    """
    from .. import models

    processed = {"dividends": 0, "coupons": 0, "lqdt": 0, "total_amount": 0}

    # Process LQDT daily accruals first
    try:
        lqdt_count = await process_lqdt_accruals(db, portfolio_id)
        processed["lqdt"] = lqdt_count
        if lqdt_count > 0:
            logger.info(f"Processed {lqdt_count} LQDT daily accruals")
    except Exception as e:
        logger.error(f"LQDT accrual processing failed: {e}")

    # Get all existing accrual transactions to avoid duplicates
    existing_accruals = crud.get_transactions(db, portfolio_id, tx_type="accrual", limit=10000)
    # Build a set of (security_id, date_string, amount) to detect duplicates
    existing_keys = set()
    for tx in existing_accruals:
        # Key: security_id + transaction_date + amount
        key = f"{tx.security_id}_{tx.transaction_date}_{tx.total_amount}"
        existing_keys.add(key)

    # Process historical dividends
    dividends = await get_portfolio_dividends_all(db, portfolio_id)
    for div in dividends:
        try:
            close_date = datetime.strptime(div["registry_close_date"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        # Skip future dividends (accrue on the registry close date itself)
        if close_date > date.today():
            continue

        # Find the security in DB
        sec = crud.get_security_by_ticker(db, div["ticker"])
        if not sec:
            continue

        # Calculate amount user should get
        amount = div["value_per_share"] * div["quantity"]
        if amount <= 0:
            continue

        # Check if already accrued
        key = f"{sec.id}_{div['registry_close_date']}_{amount}"
        if key in existing_keys:
            continue

        # Check if user held the security on the registry close date
        held = _was_held_on_date(db, portfolio_id, sec.id, close_date)
        if not held:
            logger.debug(f"Skipping {div['ticker']}: not held on {close_date}")
            continue

        # Create accrual transaction
        tx_data = schemas.TransactionCreate(
            security_id=sec.id,
            transaction_type="accrual",
            quantity=div["quantity"],
            price=div["value_per_share"],
            total_amount=amount,
            commission=0,
            transaction_date=close_date,
            notes=f"Дивиденды {div['ticker']} ({div['registry_close_date']})",
        )

        try:
            crud.create_transaction(db, portfolio_id, tx_data)
            # Update portfolio position's total_accruals
            crud.update_position_accruals(db, portfolio_id, sec.id)
            processed["dividends"] += 1
            processed["total_amount"] += amount
            existing_keys.add(key)
            logger.info(f"Auto-accrued dividend: {div['ticker']} {amount} RUB on {close_date}")
        except Exception as e:
            logger.error(f"Failed to accrue dividend for {div['ticker']}: {e}")

    # Process historical coupons for bonds/OFZ
    coupons = await get_portfolio_coupons(db, portfolio_id, upcoming_only=False)
    for coup in coupons:
        try:
            coup_date = datetime.strptime(coup["coupon_date"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        # Skip future coupons (accrue on the coupon date itself)
        if coup_date > date.today():
            continue

        sec = crud.get_security_by_ticker(db, coup["ticker"])
        if not sec:
            continue

        amount = coup["value_per_bond"] * coup["quantity"]
        if amount <= 0:
            continue

        key = f"{sec.id}_{coup['coupon_date']}_{amount}"
        if key in existing_keys:
            continue

        # Check if held on the coupon date
        held = _was_held_on_date(db, portfolio_id, sec.id, coup_date)
        if not held:
            logger.debug(f"Skipping coupon {coup['ticker']}: not held on {coup_date}")
            continue

        tx_data = schemas.TransactionCreate(
            security_id=sec.id,
            transaction_type="accrual",
            quantity=coup["quantity"],
            price=coup["value_per_bond"],
            total_amount=amount,
            commission=0,
            transaction_date=coup_date,
            notes=f"Купон {coup['ticker']} ({coup['coupon_date']})",
        )

        try:
            crud.create_transaction(db, portfolio_id, tx_data)
            crud.update_position_accruals(db, portfolio_id, sec.id)
            processed["coupons"] += 1
            processed["total_amount"] += amount
            existing_keys.add(key)
            logger.info(f"Auto-accrued coupon: {coup['ticker']} {amount} RUB on {coup_date}")
        except Exception as e:
            logger.error(f"Failed to accrue coupon for {coup['ticker']}: {e}")

    return processed


def _was_held_on_date(db: Session, portfolio_id: int, security_id: int, target_date: date) -> bool:
    """
    Check if the user held the security on a given date by looking at transactions
    before or on that date.
    """
    from .. import models

    # Get all buy/sell transactions for this security up to target_date
    buys = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.portfolio_id == portfolio_id,
            models.Transaction.security_id == security_id,
            models.Transaction.transaction_type == "buy",
            models.Transaction.transaction_date <= target_date,
        )
        .all()
    )
    sells = (
        db.query(models.Transaction)
        .filter(
            models.Transaction.portfolio_id == portfolio_id,
            models.Transaction.security_id == security_id,
            models.Transaction.transaction_type == "sell",
            models.Transaction.transaction_date <= target_date,
        )
        .all()
    )

    total_bought = sum(t.quantity for t in buys)
    total_sold = sum(t.quantity for t in sells)

    return (total_bought - total_sold) > 0