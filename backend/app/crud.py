from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal

from . import models, schemas


# === Securities ===
def get_security(db: Session, security_id: int) -> Optional[models.Security]:
    return db.query(models.Security).filter(models.Security.id == security_id).first()


def get_security_by_ticker(db: Session, ticker: str) -> Optional[models.Security]:
    return db.query(models.Security).filter(models.Security.ticker == ticker).first()


def get_securities(db: Session, skip: int = 0, limit: int = 1000) -> List[models.Security]:
    return db.query(models.Security).offset(skip).limit(limit).all()


def get_portfolio_securities(db: Session, portfolio_id: int) -> List[schemas.PortfolioSecurityResponse]:
    """Get securities with position data for this portfolio"""
    from sqlalchemy import union
    # Get security IDs from positions and transactions
    pos_ids = (
        db.query(models.PortfolioPosition.security_id)
        .filter(models.PortfolioPosition.portfolio_id == portfolio_id)
        .distinct()
    )
    tx_ids = (
        db.query(models.Transaction.security_id)
        .filter(models.Transaction.portfolio_id == portfolio_id)
        .distinct()
    )
    all_ids = pos_ids.union(tx_ids).subquery()
    
    securities = (
        db.query(models.Security)
        .filter(models.Security.id.in_(all_ids))
        .all()
    )
    
    # Get position data for each security
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
    # Delete related records first to avoid FK issues
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
    """Recalculate total_accruals for a position from all accrual transactions"""
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
    # Use provided total_amount for accruals, else auto-calc
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

    # Update position
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
            # Update average price
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
            position.quantity -= data.quantity
            if position.quantity <= 0:
                db.delete(position)
    elif data.transaction_type == "accrual":
        # Начисление (дивиденд, купон) - увеличивает баланс, не меняет количество
        accrual_amount = total_amount  # total_amount = quantity * price + commission
        if position:
            position.total_accruals = (position.total_accruals or 0) + accrual_amount
        else:
            # Если нет позиции, создаём с нулевым количеством
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
    db.delete(transaction)
    db.commit()
    return True


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


# === Dashboard ===
def get_dashboard(db: Session, portfolio_id: int) -> dict:
    positions = get_positions(db, portfolio_id)
    
    # Calculate total accruals from ALL accrual transactions (including closed positions)
    total_accruals_all = db.query(func.sum(models.Transaction.total_amount)).filter(
        models.Transaction.portfolio_id == portfolio_id,
        models.Transaction.transaction_type == "accrual",
    ).scalar() or 0
    
    total_invested = 0
    total_value = 0
    position_list = []

    for pos in positions:
        if not pos.security:
            continue
        
        cost = (pos.avg_price or 0) * pos.quantity
        current_price = pos.security.current_price or pos.avg_price or 0
        value = current_price * pos.quantity
        
        total_invested += cost
        total_value += value
        
        accruals = pos.total_accruals or 0
        profit = value - cost + accruals
        profit_percent = ((current_price - (pos.avg_price or 0)) / (pos.avg_price or 1)) * 100 if pos.avg_price else 0

        position_list.append(schemas.DashboardPosition(
            id=pos.id,
            ticker=pos.security.ticker,
            name=pos.security.name,
            security_type=pos.security.security_type,
            quantity=pos.quantity,
            avg_price=pos.avg_price,
            current_price=current_price,
            total_cost=round(cost, 2),
            total_value=round(value, 2),
            total_accruals=round(accruals, 2),
            profit=round(profit, 2),
            profit_percent=round(profit_percent, 2),
            share=0,  # Will calculate after total
        ))

    # Calculate shares
    for p in position_list:
        p.share = round((p.total_value / total_value * 100), 2) if total_value > 0 else 0

    total_return = total_value - total_invested + total_accruals_all
    total_return_percent = ((total_value + total_accruals_all) / total_invested - 1) * 100 if total_invested > 0 else 0

    recent_txns = get_transactions(db, portfolio_id, limit=10)

    return schemas.DashboardResponse(
        portfolio=schemas.PortfolioSummary(
            total_value=round(total_value, 2),
            total_invested=round(total_invested, 2),
            total_return=round(total_return, 2),
            total_return_percent=round(total_return_percent, 2),
            total_accruals=round(total_accruals_all, 2),
            position_count=len(position_list),
        ),
        positions=position_list,
        recent_transactions=recent_txns,
    )
