from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


# === Security ===
class SecurityBase(BaseModel):
    ticker: str
    name: str
    short_name: Optional[str] = None
    security_type: str = "stock"
    lot_size: int = 1
    currency: str = "RUB"
    sector: Optional[str] = None
    isin: Optional[str] = None
    exchange: str = "MOEX"
    dohod_name: Optional[str] = None


class SecurityCreate(SecurityBase):
    pass


class SecurityUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    security_type: Optional[str] = None
    lot_size: Optional[int] = None
    currency: Optional[str] = None
    sector: Optional[str] = None
    isin: Optional[str] = None
    exchange: Optional[str] = None
    dohod_name: Optional[str] = None
    current_price: Optional[float] = None


class SecurityResponse(SecurityBase):
    id: int
    current_price: Optional[float] = None
    price_updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PortfolioSecurityResponse(SecurityResponse):
    """Security with portfolio position data"""
    quantity: float = 0
    avg_price: Optional[float] = None
    total_accruals: float = 0
    realized_profit: float = 0


# === Portfolio ===
class PortfolioBase(BaseModel):
    name: str = "Основной портфель"
    description: Optional[str] = None


class PortfolioCreate(PortfolioBase):
    pass


class PortfolioResponse(PortfolioBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# === Portfolio Position ===
class PositionBase(BaseModel):
    security_id: int
    quantity: float = 0
    avg_price: Optional[float] = None


class PositionCreate(PositionBase):
    pass


class PositionUpdate(BaseModel):
    quantity: Optional[float] = None
    avg_price: Optional[float] = None


class PositionResponse(BaseModel):
    id: int
    portfolio_id: int
    security_id: int
    quantity: float
    avg_price: Optional[float] = None
    total_accruals: float = 0
    realized_profit: float = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    security: Optional[SecurityResponse] = None

    class Config:
        from_attributes = True


# === Transaction ===
class TransactionBase(BaseModel):
    security_id: int
    transaction_type: str  # buy / sell / accrual
    quantity: float
    price: float
    commission: float = 0
    transaction_date: date
    notes: Optional[str] = None


class TransactionCreate(TransactionBase):
    total_amount: Optional[float] = None  # Override auto-calc for accruals


class TransactionUpdate(BaseModel):
    quantity: Optional[float] = None
    price: Optional[float] = None
    commission: Optional[float] = None
    transaction_date: Optional[date] = None
    notes: Optional[str] = None
    transaction_type: Optional[str] = None


class TransactionResponse(TransactionBase):
    id: int
    portfolio_id: int
    total_amount: float
    created_at: Optional[datetime] = None
    security: Optional[SecurityResponse] = None

    class Config:
        from_attributes = True


# === Dividend ===
class DividendBase(BaseModel):
    security_id: int
    dividend_type: str = "dividend"
    amount_per_share: float
    total_amount: Optional[float] = None
    ex_date: Optional[date] = None
    payment_date: Optional[date] = None
    declared_date: Optional[date] = None
    tax_rate: float = 0.13
    notes: Optional[str] = None


class DividendCreate(DividendBase):
    pass


class DividendResponse(DividendBase):
    id: int
    created_at: Optional[datetime] = None
    security: Optional[SecurityResponse] = None

    class Config:
        from_attributes = True


# === Portfolio Snapshot ===
class SnapshotResponse(BaseModel):
    id: int
    portfolio_id: int
    snapshot_date: date
    total_value: float
    total_invested: float
    total_return: float
    total_return_percent: Optional[float] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# === Dashboard ===
class PortfolioSummary(BaseModel):
    total_value: float = 0
    total_invested: float = 0
    total_return: float = 0
    total_return_percent: float = 0
    total_accruals: float = 0
    expected_annual_income: float = 0  # Expected dividends + coupons for next 12 months
    expected_income_yield: float = 0  # Доходность в % от вложенных средств
    position_count: int = 0
    currency: str = "RUB"
    # 12-month metrics for Доходность card
    total_return_12m: float = 0  # Total profit from transactions in last 12 months
    total_invested_12m: float = 0  # Total invested (buy) in last 12 months
    realized_profit_12m: float = 0  # Profit from buy/sell (without accruals) in last 12 months
    actual_monthly_income_avg: float = 0  # Факт: средний доход в месяц (дивиденды+купоны за 12 мес / кол-во месяцев)



class DashboardPosition(BaseModel):
    id: int
    security_id: int = 0
    ticker: str
    name: str
    security_type: str
    quantity: float
    avg_price: Optional[float] = None
    current_price: Optional[float] = None
    total_cost: float = 0  # Вложено
    total_value: float = 0  # Текущая стоимость
    total_accruals: float = 0  # Начислено (дивиденды, купоны)
    realized_profit: float = 0  # Реализованная прибыль/убыток от продаж
    profit: float = 0
    profit_percent: float = 0
    share: float = 0  # Доля в портфеле


class DashboardResponse(BaseModel):
    portfolio: PortfolioSummary
    positions: List[DashboardPosition] = []
    recent_transactions: List[TransactionResponse] = []