"""
CBR Economy indicators service - key rate, inflation
"""
import httpx
import logging
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List
from datetime import date, datetime

logger = logging.getLogger(__name__)

# Актуальные значения на 07.2026:
# Ключевая ставка ЦБ: 14.25% (с 26.04.2026)
# Годовая инфляция: 6.02% (по данным ЦБ РФ на июнь 2026)
# https://www.cbr.ru/hd_base/infl/
DEFAULT_KEY_RATE = 14.25
DEFAULT_INFLATION = 6.02


async def fetch_key_rate() -> Optional[float]:
    """
    Fetch current CBR key rate.
    Пытается получить данные из XML_keyind.asp (старый endpoint),
    если не работает - возвращает None (используется fallback).
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Snowball/1.0",
            "Accept": "application/xml, text/xml, */*",
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get("https://www.cbr.ru/scripts/XML_keyind.asp", headers=headers)
            if resp.status_code != 200:
                logger.warning(f"CBR key rate API returned status {resp.status_code}")
                return None

            content_type = resp.headers.get("content-type", "")
            if "html" in content_type.lower():
                logger.warning("CBR returned HTML instead of XML (endpoint may be dead)")
                return None

            root = ET.fromstring(resp.content)
            for key_ind in root.findall("KeyInd"):
                code_el = key_ind.find("Code")
                value_el = key_ind.find("Value")
                if code_el is not None and value_el is not None and code_el.text == "KR":
                    try:
                        return float(value_el.text.strip())
                    except (ValueError, AttributeError):
                        pass

            rate_el = root.find(".//Rate")
            if rate_el is not None and rate_el.text:
                try:
                    return float(rate_el.text.strip())
                except ValueError:
                    pass

            return None
    except Exception as e:
        logger.error(f"Failed to fetch CBR key rate: {e}")
        return None


async def fetch_inflation_rate() -> Optional[float]:
    """
    Fetch current annual inflation rate from CBR.
    Пытается получить данные из XML API ЦБ,
    если не работает - возвращает None (используется fallback).
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Snowball/1.0",
            "Accept": "application/xml, text/xml, */*",
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get("https://www.cbr.ru/scripts/XML_ipc.asp", headers=headers)
            if resp.status_code != 200:
                logger.warning(f"CBR inflation API returned status {resp.status_code}")
                return None

            content_type = resp.headers.get("content-type", "")
            if "html" in content_type.lower():
                logger.warning("CBR returned HTML instead of XML (endpoint may be dead)")
                return None

            root = ET.fromstring(resp.content)
            last_value = None
            for item in root.iter():
                if item.tag == "Value" and item.text:
                    try:
                        last_value = float(item.text.strip().replace(",", "."))
                    except ValueError:
                        pass

            return last_value
    except Exception as e:
        logger.error(f"Failed to fetch CBR inflation rate: {e}")
        return None


async def fetch_economy_indicators() -> Dict:
    """
    Fetch both key rate and inflation from CBR.
    Returns dict with key_rate, inflation_rate, and fetch_date.
    Если CBR API недоступен, использует актуальные fallback-значения.
    """
    key_rate = await fetch_key_rate()
    inflation = await fetch_inflation_rate()

    if key_rate is None:
        key_rate = DEFAULT_KEY_RATE
        logger.info(f"Using fallback key rate: {key_rate}%")
    if inflation is None:
        inflation = DEFAULT_INFLATION
        logger.info(f"Using fallback inflation: {inflation}%")

    return {
        "key_rate": key_rate,
        "inflation_rate": inflation,
        "fetch_date": date.today().isoformat(),
    }