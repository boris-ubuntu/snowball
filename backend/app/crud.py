import logging
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, select
from typing import Optional, List
from datetime import date, datetime, timedelta
from decimal import Decimal

from . import models, schemas

logger = logging.getLogger(__name__)


def _fifo_realized_by_security(txns, window_start=None):
    """Compute per-security realized P&L using FIFO matching of buy/sell
    transactions (shared by get_dashboard's all-time and 12-month passes,
    avoiding duplicated FIFO loops).

    Args:
        txns: transactions ordered by transaction_date, id (ascending).
        window_start: if given, only sells with transaction_date >= window_start
            contribute to the returned realized P&L/total_sold. Buys and sells
            before the window are still consumed from the FIFO queue so cost
            basis for in-window sells stays correct.

    Returns:
        (sec_realized, sec_buys, total_sold):
            sec_realized: dict[security_id -> realized P&L (float)]
            sec_buys: dict[security_id -> remaining [(qty, price), ...] FIFO queue]
            total_sold: sum of sell revenue for in-window sells (float)
    """
    from collections import defaultdict

    sec_buys = defaultdict(list)
    sec_realized = defaultdict(float)
    total_sold = 0.0

    for tx in txns:
        if tx.transaction_type == "buy":
            sec_buys[tx.security_id].append((tx.quantity, tx.price))
        elif tx.transaction_type == "sell":
            in_window = window_start is None or tx.transaction_date >= window_start
            remaining_sell = tx.quantity
            sell_revenue = tx.quantity * tx.price - tx.commission
            cost_of_sold = 0
            buys = sec_buys[tx.security_id]
            while remaining_sell > 0 and buys:
                buy_qty, buy_price = buys[0]
                used = min(buy_qty, remaining_sell)
                cost_of_sold += used * buy_price
                remaining_sell -= used
                if used >= buy_qty:
                    buys.pop(0)
                else:
                    buys[0] = (buy_qty - used, buy_price)
            if in_window:
                sec_realized[tx.security_id] += sell_revenue - cost_of_sold
                total_sold += sell_revenue

    return sec_realized, sec_buys, total_sold


# === Securities ===
def get_security(db: Session, security_id: int) -> Optional[models.Security]:
    return db.query(models.Security).filter(models.Security.id == security_id).first()


def get_security_by_ticker(db: Session, ticker: str) -> Optional[models.Security]:
    return db.query(models.Security).filter(models.Security.ticker == ticker).first()


def get_securities(db: Session, skip: int = 0, limit: int = 1000) -> List[models.Security]:
    return db.query(models.Security).offset(skip).limit(limit).all()


def get_portfolio_securities(db: Session, portfolio_id: int) -> List[schemas.PortfolioSecurityResponse]:
    """Get securities with position data for this portfolio"""
    from sqlalchemy import select, union
    
    pos_ids = select(models.PortfolioPosition.security_id).where(
        models.PortfolioPosition.portfolio_id == portfolio_id
    ).distinct()
    
    tx_ids = select(models.Transaction.security_id).where(
        models.Transaction.portfolio_id == portfolio_id
    ).distinct()
    
    all_ids = pos_ids.union(tx_ids).subquery()
    
    securities = (
        db.query(models.Security)
        .filter(models.Security.id.in_(select(all_ids)))
        .all()
    )
    
    positions = {
        p.security_id: p
        for p in db.query(models.PortfolioPosition)
        .filter(models.PortfolioPosition.portfolio_id == portfolio_id)
        .all()
    }
    
    result = []
    for sec in securities:
        pos = positions.get(sec.id)
        result.append(schemas.PortfolioSecurityResponse(
            id=sec.id,
            ticker=sec.ticker,
            name=sec.name,
            short_name=sec.short_name,
            security_type=sec.security_type,
            lot_size=sec.lot_size,
            currency=sec.currency,
            sector=sec.sector,
            isin=sec.isin,
            exchange=sec.exchange,
            current_price=sec.current_price,
            price_updated_at=sec.price_updated_at,
            created_at=sec.created_at,
            quantity=pos.quantity if pos else 0,
            avg_price=pos.avg_price if pos else None,
            total_accruals=pos.total_accruals if pos else 0,
            realized_profit=pos.realized_profit if pos else 0,
        ))
    
    return result


def create_security(db: Session, data: schemas.SecurityCreate) -> models.Security:
    security = models.Security(**data.model_dump())
    db.add(security)
    db.commit()
    db.refresh(security)
    return security


def update_security(db: Session, security_id: int, data: schemas.SecurityUpdate) -> Optional[models.Security]:
    security = get_security(db, security_id)
    if not security:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(security, key, value)
    db.commit()
    db.refresh(security)
    return security


def delete_security(db: Session, security_id: int) -> bool:
    security = get_security(db, security_id)
    if not security:
        return False
    db.query(models.PortfolioPosition).filter(models.PortfolioPosition.security_id == security_id).delete()
    db.query(models.Transaction).filter(models.Transaction.security_id == security_id).delete()
    db.query(models.Dividend).filter(models.Dividend.security_id == security_id).delete()
    db.flush()
    db.delete(security)
    db.commit()
    return True


# === Portfolio ===
def get_portfolio(db: Session, portfolio_id: int) -> Optional[models.Portfolio]:
    return db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id).first()


def get_default_portfolio(db: Session) -> Optional[models.Portfolio]:
    portfolio = db.query(models.Portfolio).order_by(models.Portfolio.id).first()
    if not portfolio:
        portfolio = models.Portfolio(name="Основной портфель")
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
    return portfolio


def get_portfolios(db: Session) -> List[models.Portfolio]:
    return db.query(models.Portfolio).all()


def create_portfolio(db: Session, data: schemas.PortfolioCreate = None) -> models.Portfolio:
    if data is None:
        data = schemas.PortfolioCreate()
    portfolio = models.Portfolio(**data.model_dump())
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio


# === Positions ===
def get_positions(db: Session, portfolio_id: int) -> List[models.PortfolioPosition]:
    return (
        db.query(models.PortfolioPosition)
        .filter(models.PortfolioPosition.portfolio_id == portfolio_id)
        .options(joinedload(models.PortfolioPosition.security))
        .all()
    )


def get_position(db: Session, position_id: int) -> Optional[models.PortfolioPosition]:
    return (
        db.query(models.PortfolioPosition)
        .filter(models.PortfolioPosition.id == position_id)
        .options(joinedload(models.PortfolioPosition.security))
        .first()
    )


def create_position(db: Session, portfolio_id: int, data: schemas.PositionCreate) -> models.PortfolioPosition:
    position = models.PortfolioPosition(
        portfolio_id=portfolio_id,
        security_id=data.security_id,
        quantity=data.quantity,
        avg_price=data.avg_price,
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


def update_position(db: Session, position_id: int, data: schemas.PositionUpdate) -> Optional[models.PortfolioPosition]:
    position = get_position(db, position_id)
    if not position:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(position, key, value)
    db.commit()
    db.refresh(position)
    return position


def delete_position(db: Session, position_id: int) -> bool:
    position = db.query(models.PortfolioPosition).filter(models.PortfolioPosition.id == position_id).first()
    if not position:
        return False
    db.delete(position)
    db.commit()
    return True


def update_position_accruals(db: Session, portfolio_id: int, security_id: int):
    total = db.query(func.sum(models.Transaction.total_amount)).filter(
        models.Transaction.portfolio_id == portfolio_id,
        models.Transaction.security_id == security_id,
        models.Transaction.transaction_type == "accrual",
    ).scalar() or 0

    position = (
        db.query(models.PortfolioPosition)
        .filter(
            models.PortfolioPosition.portfolio_id == portfolio_id,
            models.PortfolioPosition.security_id == security_id,
        )
        .first()
    )
    if position:
        position.total_accruals = total
        db.commit()


# === Transactions ===
def get_transactions(db: Session, portfolio_id: int, skip: int = 0, limit: int = 50, tx_type: Optional[str] = None) -> List[models.Transaction]:
    query = (
        db.query(models.Transaction)
        .filter(models.Transaction.portfolio_id == portfolio_id)
    )
    if tx_type:
        query = query.filter(models.Transaction.transaction_type == tx_type)
    return (
        query
        .options(joinedload(models.Transaction.security))
        .order_by(desc(models.Transaction.transaction_date), desc(models.Transaction.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_transaction(db: Session, transaction_id: int) -> Optional[models.Transaction]:
    return (
        db.query(models.Transaction)
        .filter(models.Transaction.id == transaction_id)
        .options(joinedload(models.Transaction.security))
        .first()
    )


def create_transaction(db: Session, portfolio_id: int, data: schemas.TransactionCreate) -> models.Transaction:
    if data.total_amount is not None:
        total_amount = data.total_amount
    else:
        total_amount = data.quantity * data.price + data.commission
        if data.transaction_type == "sell":
            total_amount = data.quantity * data.price - data.commission

    transaction = models.Transaction(
        portfolio_id=portfolio_id,
        security_id=data.security_id,
        transaction_type=data.transaction_type,
        quantity=data.quantity,
        price=data.price,
        total_amount=total_amount,
        commission=data.commission,
        transaction_date=data.transaction_date,
        notes=data.notes,
    )
    db.add(transaction)

    position = (
        db.query(models.PortfolioPosition)
        .filter(
            models.PortfolioPosition.portfolio_id == portfolio_id,
            models.PortfolioPosition.security_id == data.security_id,
        )
        .first()
    )

    if data.transaction_type == "buy":
        if position:
            old_total = position.avg_price * position.quantity if position.avg_price else 0
            new_total = old_total + data.quantity * data.price + data.commission
            new_qty = position.quantity + data.quantity
            position.avg_price = new_total / new_qty if new_qty > 0 else data.price
            position.quantity = new_qty
        else:
            position = models.PortfolioPosition(
                portfolio_id=portfolio_id,
                security_id=data.security_id,
                quantity=data.quantity,
                avg_price=data.price + (data.commission / data.quantity if data.quantity > 0 else 0),
            )
            db.add(position)
    elif data.transaction_type == "sell":
        if position:
            # Calculate realized profit/loss on this sale
            sell_revenue = data.quantity * data.price - data.commission
            cost_of_sold = position.avg_price * data.quantity if position.avg_price else 0
            realized = sell_revenue - cost_of_sold
            position.realized_profit = (position.realized_profit or 0) + realized
            
            position.quantity -= data.quantity
            if position.quantity <= 0:
                # Keep position with quantity=0 to preserve realized_profit
                position.quantity = 0
                position.avg_price = 0
    elif data.transaction_type == "accrual":
        accrual_amount = total_amount
        if position:
            position.total_accruals = (position.total_accruals or 0) + accrual_amount
        else:
            position = models.PortfolioPosition(
                portfolio_id=portfolio_id,
                security_id=data.security_id,
                quantity=0,
                avg_price=0,
                total_accruals=accrual_amount,
            )
            db.add(position)

    db.commit()
    db.refresh(transaction)
    return transaction


def delete_transaction(db: Session, transaction_id: int) -> bool:
    transaction = get_transaction(db, transaction_id)
    if not transaction:
        return False
    portfolio_id = transaction.portfolio_id
    security_id = transaction.security_id
    db.delete(transaction)
    db.commit()
    # Recalculate position after deletion
    recalculate_position(db, portfolio_id, security_id)
    return True


def recalculate_position(db: Session, portfolio_id: int, security_id: int):
    """Recalculate position (quantity, avg_price, total_accruals, realized_profit) from all transactions."""
    all_txns = db.query(models.Transaction).filter(
        models.Transaction.portfolio_id == portfolio_id,
        models.Transaction.security_id == security_id,
    ).order_by(models.Transaction.transaction_date, models.Transaction.id).all()
    
    position = db.query(models.PortfolioPosition).filter(
        models.PortfolioPosition.portfolio_id == portfolio_id,
        models.PortfolioPosition.security_id == security_id,
    ).first()
    
    if not all_txns:
        # No transactions left - delete position
        if position:
            db.query(models.PortfolioPosition).filter(
                models.PortfolioPosition.portfolio_id == portfolio_id,
                models.PortfolioPosition.security_id == security_id,
            ).delete()
        db.commit()
        return
    
    total_qty = 0
    total_cost = 0.0
    total_accruals = 0.0

    for tx in all_txns:
        if tx.transaction_type == "buy":
            total_qty += tx.quantity
            total_cost += tx.quantity * tx.price + tx.commission
        elif tx.transaction_type == "sell":
            total_qty -= tx.quantity
            if total_qty < 0:
                total_qty = 0
        elif tx.transaction_type == "accrual":
            total_accruals += tx.total_amount

    avg_price = total_cost / total_qty if total_qty > 0 else 0

    # Realized P&L via the shared FIFO helper (avoids a duplicate buy/sell
    # matching loop here). `all_txns` is already scoped to this security.
    sec_realized, _, _ = _fifo_realized_by_security(all_txns)
    realized_profit = sec_realized.get(security_id, 0.0)

    
    if position:
        position.quantity = total_qty
        position.avg_price = avg_price
        position.total_accruals = total_accruals
        position.realized_profit = realized_profit
    elif total_qty > 0 or total_accruals > 0:
        position = models.PortfolioPosition(
            portfolio_id=portfolio_id,
            security_id=security_id,
            quantity=total_qty,
            avg_price=avg_price,
            total_accruals=total_accruals,
            realized_profit=realized_profit,
        )
        db.add(position)
    
    db.commit()


def update_transaction(db: Session, transaction_id: int, data: schemas.TransactionUpdate) -> Optional[models.Transaction]:
    transaction = get_transaction(db, transaction_id)
    if not transaction:
        return None
    old_qty = transaction.quantity
    old_price = transaction.price
    old_type = transaction.transaction_type
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(transaction, field, value)
    
    # Recalculate total_amount if quantity or price changed
    if 'quantity' in update_data or 'price' in update_data or 'transaction_type' in update_data:
        if transaction.transaction_type == "sell":
            transaction.total_amount = transaction.quantity * transaction.price - transaction.commission
        elif transaction.transaction_type == "accrual":
            pass  # keep original total_amount for accruals
        else:
            transaction.total_amount = transaction.quantity * transaction.price + transaction.commission
    
    db.commit()
    db.refresh(transaction)
    
    # Recalculate position for this security from scratch
    recalculate_position(db, transaction.portfolio_id, transaction.security_id)
    
    return transaction


def delete_transactions_by_security(db: Session, portfolio_id: int, security_id: int) -> int:
    """Delete all transactions for a security in a portfolio. Returns count of deleted transactions."""
    from sqlalchemy import func
    deleted = db.query(models.Transaction).filter(
        models.Transaction.portfolio_id == portfolio_id,
        models.Transaction.security_id == security_id,
    ).delete(synchronize_session='fetch')
    
    # Also delete the position for this security
    db.query(models.PortfolioPosition).filter(
        models.PortfolioPosition.portfolio_id == portfolio_id,
        models.PortfolioPosition.security_id == security_id,
    ).delete(synchronize_session='fetch')
    
    db.commit()
    return deleted


# === Dividends ===
def get_dividends(db: Session, security_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[models.Dividend]:
    query = db.query(models.Dividend).options(joinedload(models.Dividend.security))
    if security_id:
        query = query.filter(models.Dividend.security_id == security_id)
    return query.order_by(desc(models.Dividend.payment_date)).offset(skip).limit(limit).all()


def create_dividend(db: Session, data: schemas.DividendCreate) -> models.Dividend:
    dividend = models.Dividend(**data.model_dump())
    db.add(dividend)
    db.commit()
    db.refresh(dividend)
    return dividend


# === Portfolio Snapshots ===
def get_snapshot_before_date(db: Session, portfolio_id: int, before_date: date) -> Optional[models.PortfolioSnapshot]:
    """Get the latest snapshot strictly before the given date."""
    return (
        db.query(models.PortfolioSnapshot)
        .filter(
            models.PortfolioSnapshot.portfolio_id == portfolio_id,
            models.PortfolioSnapshot.snapshot_date < before_date,
        )
        .order_by(desc(models.PortfolioSnapshot.snapshot_date))
        .first()
    )


def upsert_snapshot(db: Session, portfolio_id: int, snapshot_date: date,
                    total_value: float, total_invested: float,
                    total_return: float, total_return_percent: float) -> models.PortfolioSnapshot:
    """Create or update a snapshot for the given date."""
    snapshot = (
        db.query(models.PortfolioSnapshot)
        .filter(
            models.PortfolioSnapshot.portfolio_id == portfolio_id,
            models.PortfolioSnapshot.snapshot_date == snapshot_date,
        )
        .first()
    )
    if snapshot:
        snapshot.total_value = total_value
        snapshot.total_invested = total_invested
        snapshot.total_return = total_return
        snapshot.total_return_percent = total_return_percent
    else:
        snapshot = models.PortfolioSnapshot(
            portfolio_id=portfolio_id,
            snapshot_date=snapshot_date,
            total_value=total_value,
            total_invested=total_invested,
            total_return=total_return,
            total_return_percent=total_return_percent,
        )
        db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


# === Dashboard ===
async def get_dashboard(db: Session, portfolio_id: int) -> dict:
    positions = get_positions(db, portfolio_id)
    
    total_accruals_all = db.query(func.sum(models.Transaction.total_amount)).filter(
        models.Transaction.portfolio_id == portfolio_id,
        models.Transaction.transaction_type == "accrual",
    ).scalar() or 0
    
    # Fetch CBR exchange rates for currency conversion.
    # IMPORTANT: never block the dashboard request on a network call. Use the
    # cached rates if available; otherwise fall back to last-known/default rates
    # immediately. The background refresh task populates fresh rates shortly after.
    from .services.cache_service import get_cached_data
    cached_rates = get_cached_data(db, "CBR_ALL", "cbr_rates")
    if cached_rates:
        cbr_rates = {r["currency"]: r["rate"] for r in cached_rates}
    else:
        # No cache yet (e.g. fresh deploy) — use safe defaults, no await.
        cbr_rates = {"RUB": 1.0, "USD": 90.0, "EUR": 98.0, "CNY": 12.0, "AED": 24.0}
    
    total_invested = 0  # in RUB
    total_value = 0  # in RUB
    total_invested_income_assets = 0
    total_realized_profit = 0  # Sum of all realized P&L from sold positions
    position_list = []

    # Calculate realized P&L from all buy/sell pairs using FIFO
    all_txns = db.query(models.Transaction).filter(
        models.Transaction.portfolio_id == portfolio_id,
    ).order_by(models.Transaction.transaction_date, models.Transaction.id).all()
    
    # Calculate realized P&L per security using FIFO (shared helper)
    sec_realized, sec_buys, _ = _fifo_realized_by_security(all_txns)

    from .services.cbr_service import convert_to_rub

    for pos in positions:
        if not pos.security:
            continue
        
        # Track realized profit/loss: use stored field OR calculated from transactions
        stored_realized = pos.realized_profit or 0
        calculated_realized = sec_realized.get(pos.security_id, 0)
        # Use the larger (more complete) value - calculated from transactions is authoritative
        realized = calculated_realized if calculated_realized != 0 else stored_realized
        total_realized_profit += realized
        
        # Determine currency for this position
        sec_currency = pos.security.currency or "RUB"
        
        cost_in_currency = (pos.avg_price or 0) * pos.quantity
        market_price_currency = pos.security.current_price or pos.avg_price or 0
        value_in_currency = market_price_currency * pos.quantity
        
        # For currency type securities, show profit/loss based on exchange rate change
        if pos.security.security_type == "currency":
            # Current CBR rate is the "current price" for currencies
            cbr_rate = cbr_rates.get(sec_currency, 1.0)
            cost_rub = cost_in_currency  # avg_price * quantity (already in RUB)
            # Current value = quantity * current CBR rate (in RUB)
            value_rub = pos.quantity * cbr_rate
            # Override current_price to show CBR rate
            market_price_currency = cbr_rate
        else:
            # Convert to RUB
            cost_rub = convert_to_rub(cost_in_currency, sec_currency, cbr_rates)
            value_rub = convert_to_rub(value_in_currency, sec_currency, cbr_rates)
        
        total_invested += cost_rub
        total_value += value_rub
        
        if pos.security.security_type in ("stock", "bond", "ofz"):
            total_invested_income_assets += cost_rub
        
        accruals = pos.total_accruals or 0
        # Profit = current value - cost + accruals + realized_profit
        unrealized_profit = value_rub - cost_rub
        profit = unrealized_profit + accruals + realized
        
        if (cost_rub + abs(realized)) > 0:
            total_invested_for_percent = cost_rub + abs(realized) if realized < 0 else cost_rub
            profit_percent = ((value_rub + accruals + realized) / total_invested_for_percent - 1) * 100
        else:
            profit_percent = 0

        position_list.append(schemas.DashboardPosition(
            id=pos.id,
            security_id=pos.security.id,
            ticker=pos.security.ticker,
            name=pos.security.name,
            security_type=pos.security.security_type,
            quantity=pos.quantity,
            avg_price=pos.avg_price,
            current_price=market_price_currency,
            total_cost=round(cost_rub, 2),
            total_value=round(value_rub, 2),
            total_accruals=round(accruals, 2),
            realized_profit=round(realized, 2),
            profit=round(profit, 2),
            profit_percent=round(profit_percent, 2),
            share=0,
        ))

    for p in position_list:
        p.share = round((p.total_value / total_value * 100), 2) if total_value > 0 else 0

    # Total return = current value - current invested + accruals + realized profit/loss from sales
    total_return = total_value - total_invested + total_accruals_all + total_realized_profit
    
    # For percentage, use total invested including what was spent on sold positions
    total_invested_for_percent = total_invested + abs(total_realized_profit) if total_realized_profit < 0 else total_invested
    if total_invested_for_percent > 0:
        total_return_percent = ((total_value + total_accruals_all + total_realized_profit) / total_invested_for_percent - 1) * 100
    else:
        total_return_percent = 0

    expected_annual_income = 0
    expected_income_yield = 0
    
    try:
        from datetime import timedelta
        from .services.cache_service import get_cached_data
        
        today = date.today()
        one_year = today + timedelta(days=365)
        
        # === Fast path: only use cached data, no MOEX API calls ===
        # The background refresh service will populate the cache
        all_divs = []
        all_coups = []
        
        # Try dohod.ru cache first (it has future dividends for SBER, MDMG, etc.)
        dohod_cache = get_cached_data(db, "ALL", "dohod_dividends")
        if dohod_cache:
            from .services.dohod_service import get_dohod_dividends_for_portfolio
            try:
                dohod_divs = await get_dohod_dividends_for_portfolio(db, portfolio_id, force_refresh=False)
                for d in dohod_divs:
                    try:
                        dd = datetime.strptime(d["registry_close_date"], "%Y-%m-%d").date()
                        if today <= dd <= one_year:
                            all_divs.append({
                                "ticker": d["ticker"],
                                "name": d["name"],
                                "registry_close_date": d["registry_close_date"],
                                "value_per_share": d["value_per_share"],
                                "quantity": d["quantity"],
                                "total_expected": d["total_expected"],
                            })
                    except (KeyError, ValueError, TypeError) as e:
                        logger.debug(f"Skipping malformed dohod dividend entry: {e}")
            except Exception as e:
                logger.debug(f"Could not fetch dohod dividends for portfolio: {e}")
        
        # Тикеры, для которых dohod.ru уже дал прогноз на ближайшие 12 месяцев -
        # для остальных акций пробуем построить прогноз по истории MOEX (YoY).
        dohod_tickers_covered = {d["ticker"] for d in all_divs}

        from .services.dividend_projection import estimate_dividend_for_ticker

        for sec_ref in positions:
            sec = sec_ref.security
            if not sec or sec_ref.quantity <= 0:
                continue

            # Прогноз дивиденда по акции, если dohod.ru не покрывает эту акцию
            if sec.security_type == "stock" and sec.ticker not in dohod_tickers_covered:
                try:
                    projected = await estimate_dividend_for_ticker(db, sec.ticker, sec_ref.quantity)
                    if projected:
                        all_divs.append({
                            "ticker": sec.ticker,
                            "name": sec.name,
                            "registry_close_date": projected["registry_close_date"],
                            "value_per_share": projected["value_per_share"],
                            "quantity": projected["quantity"],
                            "total_expected": projected["total_expected"],
                            "source": "projected",
                        })
                except Exception as e:
                    logger.debug(f"Could not project dividend for {sec.ticker}: {e}")
            
            # Get coupons from cache only
            if sec.security_type in ("bond", "ofz"):

                sec_coups = get_cached_data(db, sec.ticker, 'coupons')
                if sec_coups:
                    for coup in sec_coups:
                        try:
                            cd_str = coup["coupon_date"]
                            if isinstance(cd_str, datetime):
                                cd_str = cd_str.strftime("%Y-%m-%d")
                            cd = datetime.strptime(cd_str, "%Y-%m-%d").date()
                            if today <= cd <= one_year:
                                value_per = coup.get("value_rub", coup.get("value", 0))
                                # Detect amortizations in old cache entries (no is_amortization field)
                                # Amortization is typically > 30% of facevalue, coupon is < 20%
                                facevalue = coup.get("facevalue", 1000)
                                is_amort = coup.get("is_amortization", False)
                                if not is_amort and facevalue > 0 and value_per > facevalue * 0.3:
                                    is_amort = True
                                all_coups.append({
                                    "ticker": sec.ticker,
                                    "name": sec.name,
                                    "isin": coup.get("isin", ""),
                                    "coupon_date": cd_str,
                                    "value_per_bond": value_per,
                                    "quantity": sec_ref.quantity,
                                    "total_expected": value_per * sec_ref.quantity,
                                    "is_amortization": is_amort,
                                })
                        except (KeyError, ValueError, TypeError) as e:
                            logger.debug(f"Skipping malformed coupon entry for {sec.ticker}: {e}")
        
        # Исключаем уже начисленные (прошедшие) выплаты из ожидаемого дохода
        accrued_keys = set()
        accrued_txns = db.query(models.Transaction).filter(
            models.Transaction.portfolio_id == portfolio_id,
            models.Transaction.transaction_type == "accrual",
        ).all()
        for tx in accrued_txns:
            accrued_keys.add((tx.security_id, str(tx.transaction_date)))

        for d in all_divs:
            try:
                d_date = datetime.strptime(d["registry_close_date"], "%Y-%m-%d").date()
                if today <= d_date <= one_year:
                    sec = get_security_by_ticker(db, d.get("ticker"))
                    if sec and (sec.id, d["registry_close_date"]) in accrued_keys:
                        continue  # уже начислено -> не ждём
                    expected_annual_income += d.get("total_expected", 0)
            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Skipping malformed dividend entry in income calc: {e}")

        for c in all_coups:
            try:
                c_date = datetime.strptime(c["coupon_date"], "%Y-%m-%d").date()
                if today <= c_date <= one_year:
                    sec = get_security_by_ticker(db, c.get("ticker"))
                    if sec and (sec.id, c["coupon_date"]) in accrued_keys:
                        continue  # уже начислено -> не ждём
                    # Skip amortizations — they are return of capital, not income
                    if c.get("is_amortization"):
                        continue
                    expected_annual_income += c.get("total_expected", 0)
            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Skipping malformed coupon entry in income calc: {e}")

        # Добавляем LQDT projection в expected_annual_income
        lqdt_proj = []
        try:
            from .services.lqdt_service import get_lqdt_projection
            lqdt_proj = await get_lqdt_projection(db, portfolio_id)
            for mp in lqdt_proj:
                expected_annual_income += mp.get("total", 0)
        except Exception as e:
            logger.debug(f"Could not add LQDT projection to expected income: {e}")

        # Рассчитываем доходность от стоимости только тех активов, которые платят
        # дивиденды/купоны в следующие 12 месяцев
        paying_security_ids = set()
        # LQDT уже учтён в expected_annual_income, добавляем его в знаменатель доходности
        if lqdt_proj:
            lqdt_sec = get_security_by_ticker(db, "LQDT")
            if lqdt_sec:
                paying_security_ids.add(lqdt_sec.id)
        for d in all_divs:
            try:
                d_date = datetime.strptime(d["registry_close_date"], "%Y-%m-%d").date()
                if today <= d_date <= one_year:
                    sec = get_security_by_ticker(db, d.get("ticker"))
                    if sec:
                        paying_security_ids.add(sec.id)
            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Skipping malformed dividend entry in yield calc: {e}")
        for c in all_coups:
            try:
                c_date = datetime.strptime(c["coupon_date"], "%Y-%m-%d").date()
                if today <= c_date <= one_year:
                    # Skip amortizations — they are return of capital, not income
                    if c.get("is_amortization"):
                        continue
                    sec = get_security_by_ticker(db, c.get("ticker"))
                    if sec:
                        paying_security_ids.add(sec.id)
            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Skipping malformed coupon entry in yield calc: {e}")

        # Суммируем стоимость только тех позиций, которые платят
        paying_value = 0
        for p in position_list:
            if p.security_id in paying_security_ids:
                paying_value += p.total_value

        portfolio_value_for_yield = paying_value if paying_value > 0 else total_value
        if portfolio_value_for_yield > 0 and expected_annual_income > 0:
            expected_income_yield = (expected_annual_income / portfolio_value_for_yield) * 100
            
    except Exception as e:
        logger.error(f"Error calculating expected annual income: {e}")

    # === Calculate 12-month metrics ===
    # Reuse the already-loaded `all_txns` list and the shared FIFO helper
    # instead of a second hand-rolled FIFO loop.
    twelve_months_ago = date.today() - timedelta(days=365)

    sec_realized_12m, _, total_sold_12m = _fifo_realized_by_security(all_txns, window_start=twelve_months_ago)
    realized_profit_12m = sum(sec_realized_12m.values())

    total_accruals_12m = sum(
        tx.total_amount for tx in all_txns
        if tx.transaction_type == "accrual" and tx.transaction_date >= twelve_months_ago
    )

    total_invested_12m = sum(
        tx.total_amount for tx in all_txns
        if tx.transaction_type == "buy" and tx.transaction_date >= twelve_months_ago
    )

    total_return_12m = total_accruals_12m + realized_profit_12m

    recent_txns = get_transactions(db, portfolio_id, limit=10)

    # === Build monthly histogram (13 buckets) ===
    monthly_histogram = []
    upcoming_payments = []

    try:
        from collections import defaultdict
        from datetime import timedelta

        # Collect all items: dividends + coupons (non-amort) + LQDT
        all_items = []

        # Dividends
        for d in all_divs:
            try:
                dd = datetime.strptime(d["registry_close_date"], "%Y-%m-%d").date()
                if today <= dd <= one_year:
                    sec = get_security_by_ticker(db, d.get("ticker"))
                    if sec and (sec.id, d["registry_close_date"]) in accrued_keys:
                        continue
                    all_items.append({
                        "date": dd,
                        "ticker": d["ticker"],
                        "name": d["name"],
                        "total_expected": d.get("total_expected", 0),
                        "is_amortization": False,
                        "source": d.get("source", "dividend"),
                        "type": "dividend",
                    })
            except:
                pass

        # Coupons (non-amort)
        for c in all_coups:
            try:
                cd = datetime.strptime(c["coupon_date"], "%Y-%m-%d").date()
                if today <= cd <= one_year:
                    sec = get_security_by_ticker(db, c.get("ticker"))
                    if sec and (sec.id, c["coupon_date"]) in accrued_keys:
                        continue
                    if c.get("is_amortization"):
                        continue
                    all_items.append({
                        "date": cd,
                        "ticker": c["ticker"],
                        "name": c["name"],
                        "total_expected": c.get("total_expected", 0),
                        "is_amortization": False,
                        "source": "coupon",
                        "type": "coupon",
                    })
            except:
                pass

        # LQDT projection — one entry per month (last day of month)
        try:
            from .services.lqdt_service import get_lqdt_projection
            from calendar import monthrange
            lqdt_proj = await get_lqdt_projection(db, portfolio_id)
            for mp in lqdt_proj:
                try:
                    month_first = mp["date"]
                    if isinstance(month_first, str):
                        month_first = datetime.strptime(month_first, "%Y-%m-%d").date()
                    # Last day of month
                    last_day = monthrange(month_first.year, month_first.month)[1]
                    ld = date(month_first.year, month_first.month, last_day)
                    if today <= ld <= one_year:
                        all_items.append({
                            "date": ld,
                            "ticker": "LQDT",
                            "name": "LQDT Money Market",
                            "total_expected": mp.get("total", 0),
                            "is_amortization": False,
                            "source": "lqdt",
                            "type": "dividend",
                        })
                except:
                    pass
        except Exception as e:
            logger.debug(f"Could not add LQDT to histogram: {e}")

        # Also add amortizations for histogram (shown separately)
        for c in all_coups:
            try:
                cd = datetime.strptime(c["coupon_date"], "%Y-%m-%d").date()
                if today <= cd <= one_year and c.get("is_amortization"):
                    all_items.append({
                        "date": cd,
                        "ticker": c["ticker"],
                        "name": c["name"],
                        "total_expected": c.get("total_expected", 0),
                        "is_amortization": True,
                        "source": "amortization",
                        "type": "amortization",
                    })
            except:
                pass

        # Build 13 buckets
        buckets = []
        for i in range(13):
            month_start = today.replace(day=1) + timedelta(days=32 * i)
            month_start = month_start.replace(day=1)
            if i == 0:
                month_start = today
            month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            if i == 12:
                month_end = today + timedelta(days=365)
            buckets.append({
                "month": month_start.strftime("%Y-%m"),
                "start": month_start,
                "end": month_end,
                "total": 0,
                "items": [],
            })

        for item in all_items:
            for bucket in buckets:
                if bucket["start"] <= item["date"] <= bucket["end"]:
                    bucket["total"] += item["total_expected"]
                    bucket["items"].append(schemas.HistogramItem(
                        ticker=item["ticker"],
                        name=item["name"],
                        total_expected=item["total_expected"],
                        is_amortization=item["is_amortization"],
                        source=item["source"],
                    ))
                    break

        monthly_histogram = [
            schemas.HistogramBucket(month=b["month"], total=round(b["total"], 2), items=b["items"])
            for b in buckets
        ]

        # Flat list of upcoming payments (for dividends page)
        for item in sorted(all_items, key=lambda x: x["date"]):
            upcoming_payments.append(schemas.UpcomingPayment(
                ticker=item["ticker"],
                name=item["name"],
                date=item["date"].strftime("%Y-%m-%d"),
                total_expected=item["total_expected"],
                type=item["type"],
                source=item["source"],
            ))

    except Exception as e:
        logger.error(f"Error building monthly histogram: {e}")

    # === Daily P&L ===
    today = date.today()
    daily_pl = 0.0
    try:
        # Upsert snapshot for today
        upsert_snapshot(db, portfolio_id, today,
                        total_value=round(total_value, 2),
                        total_invested=round(total_invested, 2),
                        total_return=round(total_return, 2),
                        total_return_percent=round(total_return_percent, 2))
        # Get yesterday's snapshot (strictly before today)
        yesterday_snap = get_snapshot_before_date(db, portfolio_id, today)
        if yesterday_snap:
            daily_pl = round(total_value - yesterday_snap.total_value, 2)
    except Exception as e:
        logger.error(f"Error calculating daily P&L: {e}")

    return schemas.DashboardResponse(
        portfolio=schemas.PortfolioSummary(
            total_value=round(total_value, 2),
            total_invested=round(total_invested, 2),
            total_return=round(total_return, 2),
            total_return_percent=round(total_return_percent, 2),
            total_accruals=round(total_accruals_all, 2),
            expected_annual_income=round(expected_annual_income, 2),
            expected_income_yield=round(expected_income_yield, 2),
            position_count=len(position_list),
            total_return_12m=round(total_return_12m, 2),
            total_invested_12m=round(total_invested_12m, 2),
            realized_profit_12m=round(realized_profit_12m, 2),
            daily_pl=daily_pl,
        ),
        positions=position_list,
        recent_transactions=recent_txns,
        monthly_histogram=monthly_histogram,
        upcoming_payments=upcoming_payments,
    )
