from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text, JSON, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import enum
import pytz

Base = declarative_base()

moscow_tz = pytz.timezone("Europe/Moscow")


class SecurityType(str, enum.Enum):
    STOCK = "stock"         # Акция
    BOND = "bond"           # Облигация
    ETF = "etf"             # ETF / Фонд
    OFZ = "ofz"             # ОФЗ
    CURRENCY = "currency"   # Валюта
    OTHER = "other"         # Другое


class Security(Base):
    __tablename__ = "securities"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    short_name = Column(String(100), nullable=True)
    security_type = Column(String(20), nullable=False, default=SecurityType.STOCK.value)
    lot_size = Column(Integer, default=1)  # Размер лота
    currency = Column(String(10), default="RUB")  # Валюта торгов
    sector = Column(String(100), nullable=True)  # Сектор экономики
    isin = Column(String(20), nullable=True)  # ISIN код
    exchange = Column(String(20), default="MOEX")  # Биржа
    dohod_name = Column(String(255), nullable=True)  # Название для сопоставления с dohod.ru
    current_price = Column(Float, nullable=True)  # Текущая рыночная цена
    price_updated_at = Column(DateTime(timezone=True), nullable=True)  # Когда обновлена цена
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    positions = relationship("PortfolioPosition", back_populates="security")
    transactions = relationship("Transaction", back_populates="security")
    dividends = relationship("Dividend", back_populates="security")


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, default="Основной портфель")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    positions = relationship("PortfolioPosition", back_populates="portfolio")
    transactions = relationship("Transaction", back_populates="portfolio")
    snapshots = relationship("PortfolioSnapshot", back_populates="portfolio")


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    security_id = Column(Integer, ForeignKey("securities.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Float, nullable=False, default=0)  # Текущее количество
    avg_price = Column(Float, nullable=True)  # Средняя цена покупки
    total_accruals = Column(Float, nullable=False, default=0)  # Всего начислено (дивиденды, купоны и т.д.)
    realized_profit = Column(Float, nullable=False, default=0)  # Реализованная прибыль/убыток от продаж
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    portfolio = relationship("Portfolio", back_populates="positions")
    security = relationship("Security", back_populates="positions")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    security_id = Column(Integer, ForeignKey("securities.id", ondelete="CASCADE"), nullable=False)
    transaction_type = Column(String(10), nullable=False)  # buy / sell / accrual
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)  # Цена за единицу
    total_amount = Column(Float, nullable=False)  # Общая сумма
    commission = Column(Float, default=0)  # Комиссия
    transaction_date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    portfolio = relationship("Portfolio", back_populates="transactions")
    security = relationship("Security", back_populates="transactions")


class Dividend(Base):
    __tablename__ = "dividends"

    id = Column(Integer, primary_key=True, index=True)
    security_id = Column(Integer, ForeignKey("securities.id", ondelete="CASCADE"), nullable=False)
    dividend_type = Column(String(20), nullable=False, default="dividend")  # dividend / coupon
    amount_per_share = Column(Float, nullable=False)  # На одну бумагу
    total_amount = Column(Float, nullable=True)  # Общая сумма (если известно)
    ex_date = Column(Date, nullable=True)  # Дата отсечки
    payment_date = Column(Date, nullable=True)  # Дата выплаты
    declared_date = Column(Date, nullable=True)  # Дата объявления
    tax_rate = Column(Float, default=0.13)  # Ставка налога
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    security = relationship("Security", back_populates="dividends")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    snapshot_date = Column(Date, nullable=False)
    total_value = Column(Float, nullable=False)  # Общая стоимость портфеля
    total_invested = Column(Float, nullable=False)  # Всего вложено
    total_return = Column(Float, nullable=False)  # Абсолютная доходность
    total_return_percent = Column(Float, nullable=True)  # Доходность в %
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    portfolio = relationship("Portfolio", back_populates="snapshots")

class MoexCache(Base):
    __tablename__ = "moex_cache"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    cache_type = Column(String(20), nullable=False)  # dividends, coupons, price
    data = Column(JSON, nullable=False)  # Храним JSON с данными
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Время истечения кеша

    __table_args__ = (
        UniqueConstraint('ticker', 'cache_type', name='uq_moex_cache_ticker_type'),
    )