"""
Сервис для парсинга дивидендов с сайта dohod.ru.

Адаптированная версия скрипта Learning/Dohod.py под структуру проекта snowball.
Возвращает список дивидендов по русскому названию акции (поле dohod_name в модели Security).
"""
import logging
import re
import difflib
from typing import List, Dict, Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from .. import models
from .cache_service import get_cached_data, set_cached_data

logger = logging.getLogger(__name__)

DOHOD_URL = "https://www.dohod.ru/ik/analytics/dividend"
CACHE_TYPE = "dohod_dividends"
CACHE_TTL = 60 * 24  # 24 часа

# Прямой маппинг тикеров → названия на dohod.ru для бумаг,
# у которых название на MOEX не совпадает с dohod.ru
TICKER_TO_DOHOD = {
    "MDMG": "Мать и дитя",
    "X5": "КЦ ИКС 5",
    "SIBN": "Газпром нефть",
    "VSEH": "ВсеИнструменты",
    "CNRU": "ЦИАН",
}


async def fetch_dohod_dividends(db: Optional[Session] = None, force_refresh: bool = False) -> List[Dict]:
    """
    Парсит таблицу дивидендов с dohod.ru.
    Возвращает список словарей: {"name", "dividend", "record_date"}.
    Результат кэшируется в таблице moex_cache (cache_type='dohod_dividends').
    """
    if not force_refresh and db is not None:
        cached = get_cached_data(db, "ALL", CACHE_TYPE)
        if cached is not None:
            logger.debug("Using cached dohod dividends")
            return cached

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(DOHOD_URL, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.error(f"Ошибка запроса к dohod.ru: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")

    # Ищем таблицу по заголовкам
    target_table = None
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if not header_row:
            continue
        header_texts = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
        header_line = " ".join(header_texts)
        if ("Акция" in header_line and
                "Выплата на акцию" in header_line and
                "Дата закрытия реестра" in header_line):
            target_table = table
            break

    if not target_table:
        logger.warning("Таблица дивидендов dohod.ru не найдена")
        return []

    # Определяем индексы нужных колонок
    header_row = target_table.find("tr")
    headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
    col_name = next((i for i, h in enumerate(headers) if "Акция" in h), None)
    col_dividend = next((i for i, h in enumerate(headers) if "Выплата на акцию" in h), None)
    col_record_date = next((i for i, h in enumerate(headers) if "Дата закрытия реестра" in h), None)

    if col_name is None or col_dividend is None or col_record_date is None:
        logger.warning("Не удалось найти все колонки в таблице dohod.ru")
        return []

    dividends = []
    for row in target_table.find_all("tr")[1:]:
        cols = row.find_all("td")
        if len(cols) < max(col_name, col_dividend, col_record_date) + 1:
            continue

        name = cols[col_name].get_text(strip=True)
        dividend_text = cols[col_dividend].get_text(strip=True)
        record_date_text = cols[col_record_date].get_text(strip=True)

        dividend_clean = re.sub(r"[^\d.,]", "", dividend_text.replace("RUB", "").strip())
        if dividend_clean == "":
            continue
        try:
            dividend = float(dividend_clean.replace(",", "."))
        except ValueError:
            continue

        record_date = "n/a"
        date_match = re.search(r"\d{2}\.\d{2}\.\d{4}", record_date_text)
        if date_match:
            record_date = date_match.group(0)

        if record_date == "n/a" or dividend is None:
            continue

        dividends.append({
            "name": name,
            "dividend": dividend,
            "record_date": record_date,
        })

    logger.info(f"Спарсено {len(dividends)} дивидендов с dohod.ru")

    if dividends and db is not None:
        try:
            set_cached_data(db, "ALL", CACHE_TYPE, dividends, ttl_minutes=CACHE_TTL)
        except Exception as e:
            logger.debug(f"Не удалось закэшировать dohod dividends: {e}")

    return dividends


def _normalize_name(name: str) -> str:
    """
    Нормализует название акции для сопоставления:
    убирает суффиксы типа '-ао', '-п', '-ап', лишние пробелы и приводит к нижнему регистру.
    Например: 'Сбербанк-ао' -> 'сбербанк', 'Башнефть-п' -> 'башнефть'.
    """
    if not name:
        return ""
    n = name.lower().strip()
    # Убираем суффиксы вида -ао / -п / -ап / -ao / -p в конце
    n = re.sub(r"[\-\s]+(ао|ап|п|ao|p)$", "", n)
    # Убираем всё, кроме букв и цифр
    n = re.sub(r"[^a-zа-я0-9]", "", n)
    return n


def _get_keywords(name: str) -> set:
    """Извлекает значимые ключевые слова из названия."""
    if not name:
        return set()
    # Убираем суффиксы, приводим к нижнему регистру
    n = name.lower().strip()
    n = re.sub(r"[\-\s]+(ао|ап|п|ao|p)$", "", n)
    # Убираем короткие и незначащие слова
    stop_words = {"ао", "ап", "п", "ao", "p", "оао", "пао", "зао", "ооо", "ао", "the", "inc", "ltd", "corp", "группа"}
    words = re.findall(r"[a-zа-я]+", n)
    return {w for w in words if len(w) >= 3 and w not in stop_words}


async def get_dohod_dividends_for_portfolio(
    db: Session, portfolio_id: int, force_refresh: bool = False
) -> List[Dict]:
    """
    Возвращает предстоящие дивиденды из dohod.ru, сопоставленные с бумагами портфеля
    по полю Security.dohod_name (или name/short_name, если dohod_name не задано).
    Сопоставление устойчиво к суффиксам типа '-ао'/'-п' благодаря нормализации.
    """
    from .. import crud
    from datetime import datetime, date

    securities = crud.get_portfolio_securities(db, portfolio_id)
    if not securities:
        return []

    # Прямой маппинг тикер -> dohod_name (for securities whose names don't match MOEX)
    ticker_to_dohod_name = {}
    for sec in securities:
        if getattr(sec, "quantity", 0) <= 0:
            continue
        # Use TICKER_TO_DOHOD mapping if available
        if sec.ticker in TICKER_TO_DOHOD:
            ticker_to_dohod_name[TICKER_TO_DOHOD[sec.ticker]] = sec
        # Also try dohod_name from DB
        if sec.dohod_name:
            ticker_to_dohod_name[sec.dohod_name] = sec

    # Строим карту: нормализованный ключ -> security
    name_to_sec = {}
    for sec in securities:
        if getattr(sec, "quantity", 0) <= 0:
            continue
        keys = []
        # Add dohod_name from DB
        if sec.dohod_name:
            keys.append(sec.dohod_name)
        if sec.name:
            keys.append(sec.name)
        if sec.short_name:
            keys.append(sec.short_name)
        for k in keys:
            nk = _normalize_name(k)
            if nk:
                name_to_sec[nk] = sec

    if not name_to_sec:
        return []

    all_dividends = await fetch_dohod_dividends(db, force_refresh)

    today = date.today()
    result = []
    for div in all_dividends:
        # Сначала проверяем прямой маппинг по названию с dohod.ru
        sec = ticker_to_dohod_name.get(div["name"])
        if sec is not None:
            # Found via direct mapping
            pass
        else:
            div_norm = _normalize_name(div["name"])
            if not div_norm:
                continue
            # Точное совпадение по нормализованному имени
            sec = name_to_sec.get(div_norm)
            # Если не нашли — пробуем частичное совпадение (префикс)
            if sec is None:
                for nk, s in name_to_sec.items():
                    if div_norm.startswith(nk) or nk.startswith(div_norm):
                        sec = s
                        break
            # Если не нашли — пробуем сопоставление по ключевым словам с нечётким сравнением
            if sec is None:
                div_keywords = _get_keywords(div_norm)
                best_match = None
                best_score = 0
                for nk, s in name_to_sec.items():
                    sec_keywords = _get_keywords(nk)
                    # Сначала точное совпадение
                    common = div_keywords & sec_keywords
                    # Затем нечёткое совпадение (difflib)
                    fuzzy_score = 0
                    for dw in div_keywords:
                        for sw in sec_keywords:
                            ratio = difflib.SequenceMatcher(None, dw, sw).ratio()
                            if ratio >= 0.8:
                                fuzzy_score += 1
                    score = len(common) + fuzzy_score * 0.5
                    if score > best_score:
                        best_score = score
                        best_match = s
                if best_match and best_score >= 0.5:
                    sec = best_match
        if sec is None:
            continue

        # Конвертируем дату dd.mm.yyyy -> YYYY-MM-DD
        registry_close_date = None
        try:
            registry_close_date = datetime.strptime(div["record_date"], "%d.%m.%Y").date().isoformat()
        except (ValueError, TypeError):
            continue

        if registry_close_date < today.isoformat():
            continue

        if div["dividend"] <= 0:
            continue

        result.append({
            "ticker": sec.ticker,
            "name": sec.name,
            "isin": sec.isin or "",
            "registry_close_date": registry_close_date,
            "value_per_share": div["dividend"],
            "currency": sec.currency or "RUB",
            "quantity": getattr(sec, "quantity", 0),
            "total_expected": div["dividend"] * getattr(sec, "quantity", 0),
            "source": "dohod.ru",
        })

    # Убираем дубли (например, Сбербанк-ао и Сбербанк-п могут указывать на одну бумагу)
    seen = set()
    unique = []
    for d in result:
        key = (d["ticker"], d["registry_close_date"], d["value_per_share"])
        if key not in seen:
            seen.add(key)
            unique.append(d)

    unique.sort(key=lambda x: x["registry_close_date"])
    return unique
