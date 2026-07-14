import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models

logger = logging.getLogger(__name__)

# Время жизни кеша в минутах
CACHE_TTL = {
    'dividends': 60 * 24,  # 24 часа
    'coupons': 60 * 24,    # 24 часа
    'price': 5,            # 5 минут
}


def get_cached_data(db: Session, ticker: str, cache_type: str) -> Optional[List[Dict]]:
    """
    Получить данные из кеша, если они еще актуальны
    """
    cache_entry = db.query(models.MoexCache).filter(
        models.MoexCache.ticker == ticker,
        models.MoexCache.cache_type == cache_type
    ).first()

    if not cache_entry:
        return None

    # Проверяем, не истек ли кеш
    if cache_entry.expires_at and datetime.now(timezone.utc) > cache_entry.expires_at:
        logger.debug(f"Cache expired for {ticker}/{cache_type}")
        return None

    try:
        return json.loads(cache_entry.data) if isinstance(cache_entry.data, str) else cache_entry.data
    except Exception as e:
        logger.debug(f"Error parsing cache for {ticker}/{cache_type}: {e}")
        return None


def set_cached_data(db: Session, ticker: str, cache_type: str, data: List[Dict], ttl_minutes: Optional[int] = None):
    """
    Сохранить данные в кеш
    """
    if ttl_minutes is None:
        ttl_minutes = CACHE_TTL.get(cache_type, 60)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)

    # Ищем существующую запись
    cache_entry = db.query(models.MoexCache).filter(
        models.MoexCache.ticker == ticker,
        models.MoexCache.cache_type == cache_type
    ).first()

    data_json = json.dumps(data, default=str) if not isinstance(data, str) else data

    if cache_entry:
        cache_entry.data = data_json
        cache_entry.updated_at = datetime.now(timezone.utc)
        cache_entry.expires_at = expires_at
    else:
        cache_entry = models.MoexCache(
            ticker=ticker,
            cache_type=cache_type,
            data=data_json,
            expires_at=expires_at
        )
        db.add(cache_entry)

    db.commit()
    logger.debug(f"Cached {len(data)} items for {ticker}/{cache_type}, expires at {expires_at}")


def clear_expired_cache(db: Session):
    """
    Очистить просроченный кеш
    """
    deleted = db.query(models.MoexCache).filter(
        models.MoexCache.expires_at < datetime.now(timezone.utc)
    ).delete()
    db.commit()
    if deleted:
        logger.info(f"Cleared {deleted} expired cache entries")
    return deleted