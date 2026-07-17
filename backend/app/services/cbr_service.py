"""
CBR (Central Bank of Russia) exchange rate service.
Fetches daily official exchange rates from cbr.ru.
"""
import httpx
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Optional
from datetime import date, datetime

logger = logging.getLogger(__name__)

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

# Mapping: currency code -> RUB rate (how many RUB for 1 unit of currency)
# For most currencies it's direct, for RUB it's 1.0
CURRENCY_INFO = {
    "USD": {"name_ru": "Доллар США", "name_en": "US Dollar"},
    "EUR": {"name_ru": "Евро", "name_en": "Euro"},
    "CNY": {"name_ru": "Китайский юань", "name_en": "Chinese Yuan"},
    "AED": {"name_ru": "Дирхам ОАЭ", "name_en": "UAE Dirham"},
    "RUB": {"name_ru": "Российский рубль", "name_en": "Russian Ruble"},
}

# CBR uses different codes internally
CBR_CHAR_CODE_MAP = {
    "USD": "USD",
    "EUR": "EUR",
    "CNY": "CNY",
    "AED": "AED",
}


async def fetch_cbr_rates() -> Dict[str, float]:
    """
    Fetch exchange rates from CBR API.
    Returns dict mapping currency code -> RUB rate.
    Rate is how many RUB for 1 unit of the currency.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Snowball/1.0",
            "Accept": "application/xml, text/xml, */*",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(CBR_URL, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"CBR returned status {resp.status_code}")
                return _get_default_rates()

            root = ET.fromstring(resp.content)
            rates = {"RUB": 1.0}

            for valute in root.findall("Valute"):
                char_code_el = valute.find("CharCode")
                value_el = valute.find("Value")
                nominal_el = valute.find("Nominal")

                if char_code_el is None or value_el is None:
                    continue

                char_code = char_code_el.text
                if char_code not in CBR_CHAR_CODE_MAP.values():
                    continue

                try:
                    nominal = int(nominal_el.text) if nominal_el is not None and nominal_el.text else 1
                    value_str = value_el.text.replace(",", ".")
                    rate_per_unit = float(value_str) / nominal
                    rates[char_code] = rate_per_unit
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Failed to parse rate for {char_code}: {e}")

            logger.info(f"Fetched CBR rates: { {k: round(v, 4) for k, v in rates.items()} }")
            return rates

    except Exception as e:
        logger.error(f"Failed to fetch CBR rates: {e}")
        return _get_default_rates()


def _get_default_rates() -> Dict[str, float]:
    """Fallback rates if CBR is unavailable (approximate, last-resort values)."""
    return {
        "USD": 90.0,
        "EUR": 98.0,
        "CNY": 12.0,
        "AED": 24.0,
        "RUB": 1.0,
    }


def convert_to_rub(amount: float, from_currency: str, rates: Dict[str, float]) -> float:
    """Convert amount from any supported currency to RUB"""
    if from_currency == "RUB":
        return amount
    rate = rates.get(from_currency)
    if rate is None:
        logger.warning(f"No exchange rate for {from_currency}, assuming 1:1")
        return amount
    return amount * rate


def convert_from_rub(amount_rub: float, to_currency: str, rates: Dict[str, float]) -> float:
    """Convert RUB to target currency"""
    if to_currency == "RUB":
        return amount_rub
    rate = rates.get(to_currency)
    if rate is None or rate == 0:
        logger.warning(f"No exchange rate for {to_currency}, assuming 1:1")
        return amount_rub
    return amount_rub / rate