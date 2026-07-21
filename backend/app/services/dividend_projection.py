"""
Прогноз следующей дивидендной выплаты на основе исторических данных MOEX.

Используется как fallback, когда dohod.ru не публикует данные о выплате
на ближайшие 12 месяцев (например, для компаний, которые ещё не объявили
следующий дивиденд).

Правило регулярности: компания должна была платить дивиденды в каждом из
последних 2 полных календарных лет (год-1 и год-2 относительно сегодня).
Если хотя бы в одном из этих лет выплат не было - прогноз не строится.

Экстраполяция: простой YoY рост суммы дивидендов на акцию за календарный год
(год-1 к году-2), применённый к сумме за год-1.
"""
import logging
from datetime import date, datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from .moex_dividends import get_dividends_for_ticker

logger = logging.getLogger(__name__)


async def estimate_dividend_for_ticker(db: Session, ticker: str, quantity: float) -> Optional[Dict]:
    """
    Возвращает прогнозируемую выплату для тикера или None, если прогноз
    невозможен (нет истории или выплаты нерегулярны).

    Результат: {
        "registry_close_date": "YYYY-MM-DD",
        "value_per_share": float,
        "quantity": float,
        "total_expected": float,
        "source": "projected",
    }
    """
    try:
        history = await get_dividends_for_ticker(db, ticker)
    except Exception as e:
        logger.debug(f"Could not fetch dividend history for {ticker}: {e}")
        return None

    if not history:
        return None

    today = date.today()
    current_year = today.year

    yearly_totals: Dict[int, float] = {}
    yearly_last_date: Dict[int, date] = {}

    for entry in history:
        try:
            d = datetime.strptime(entry["registry_close_date"], "%Y-%m-%d").date()
            v = float(entry["value"])
        except (KeyError, ValueError, TypeError):
            continue
        y = d.year
        yearly_totals[y] = yearly_totals.get(y, 0) + v
        if y not in yearly_last_date or d > yearly_last_date[y]:
            yearly_last_date[y] = d

    if not yearly_totals:
        return None

    last_full_year = current_year - 1
    prev_full_year = current_year - 2

    total_last = yearly_totals.get(last_full_year, 0)
    total_prev = yearly_totals.get(prev_full_year, 0)

    # Регулярность: выплаты должны быть в обоих из последних 2 полных лет
    if total_last <= 0 or total_prev <= 0:
        return None

    growth = total_last / total_prev - 1
    # Ограничиваем экстраполяцию разумными пределами, чтобы избежать выбросов
    growth = max(-0.5, min(growth, 1.0))

    projected_value_per_share = total_last * (1 + growth)
    if projected_value_per_share <= 0:
        return None

    # Прогнозная дата: последняя известная дата выплаты + 1 год (при
    # необходимости продвигаем вперёд, пока не окажется в будущем)
    last_known_date = max(yearly_last_date.values())
    projected_date = last_known_date
    while projected_date < today:
        try:
            projected_date = date(projected_date.year + 1, projected_date.month, projected_date.day)
        except ValueError:
            # 29 февраля и т.п.
            projected_date = date(projected_date.year + 1, projected_date.month, 28)

    return {
        "registry_close_date": projected_date.strftime("%Y-%m-%d"),
        "value_per_share": round(projected_value_per_share, 4),
        "quantity": quantity,
        "total_expected": round(projected_value_per_share * quantity, 2),
        "source": "projected",
    }
