# analytics/services.py
import base64
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional, Tuple

import requests
from django.conf import settings
from django.core.cache import cache


class EgovApiError(Exception):
    pass


@dataclass
class EgovToken:
    access_token: str
    expires_in: int = 300  # fallback


def _basic_auth_header(key: str, secret: str) -> str:
    raw = f"{key}:{secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def get_access_token() -> str:
    """
    Берём access_token и кэшируем до истечения (минус небольшой буфер).
    """
    cache_key = "egov_api_access_token"
    cached = cache.get(cache_key)
    if cached:
        return cached

    token_url = settings.EGOV_API_TOKEN_URL
    consumer_key = settings.EGOV_API_CONSUMER_KEY
    consumer_secret = settings.EGOV_API_CONSUMER_SECRET
    username = settings.EGOV_API_USERNAME
    password = settings.EGOV_API_PASSWORD
    timeout = getattr(settings, "EGOV_API_TIMEOUT", 20)

    if not all([token_url, consumer_key, consumer_secret, username, password]):
        raise EgovApiError("EGOV API credentials are not configured")

    headers = {
        "Authorization": _basic_auth_header(consumer_key, consumer_secret),
    }
    data = {
        "grant_type": "password",
        "username": username,
        "password": password,
    }

    resp = requests.post(token_url, headers=headers, data=data, timeout=timeout)
    if not resp.ok:
        raise EgovApiError(f"Token request failed {resp.status_code}: {resp.text[:500]}")

    payload = resp.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise EgovApiError(f"No access_token in response: {payload}")

    expires_in = int(payload.get("expires_in") or 300)
    # кэшируем чуть меньше, чтобы не ловить “истёк токен”
    cache.set(cache_key, access_token, timeout=max(30, expires_in - 15))
    return access_token


def get_person_by_pinpp(pinpp: str, birth_date: str, lang_id: int = 1) -> Dict[str, Any]:
    """
    Возвращает данные физлица (ФИО и пр.). Повторяет логику PHP:
    - POST json в EGOV_API_BASE_URL
    - ожидаем result == '1'
    - возвращаем response['data']
    """
    pinpp = (pinpp or "").strip()
    birth_date = (birth_date or "").strip()

    if not pinpp or not birth_date:
        raise EgovApiError("pinpp and birth_date are required")

    token = get_access_token()
    url = settings.EGOV_API_BASE_URL
    timeout = getattr(settings, "EGOV_API_TIMEOUT", 20)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    body = {
        "transaction_id": int(time.time()),
        "is_consent": "Y",
        "langId": int(lang_id),
        "is_photo": "N",
        "Sender": "M",
        "pinpp": pinpp,
        "birth_date": birth_date,  # формат обычно YYYY-MM-DD
    }

    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    if not resp.ok:
        raise EgovApiError(f"API request failed {resp.status_code}: {resp.text[:500]}")

    data = resp.json()

    if str(data.get("result")) == "1":
        payload = data.get("data")

        if isinstance(payload, list):
            return payload[0] if payload else {}

        if isinstance(payload, dict):
            return payload

        return {}

    raise EgovApiError("Incorrect data, enter correct pinpp and birth_date.")

def birth_date_from_pinpp(pinpp: str) -> str:
    """
    Извлекает дату рождения YYYY-MM-DD из ПИНФЛ (pinpp).
    Формат: 14 цифр.
      1-я цифра: век/пол (1-6)
      2-7: DDMMYY
    Пример: 30101800050014 -> 1980-01-01
    """
    s = re.sub(r"\D+", "", pinpp or "")
    if len(s) != 14:
        raise EgovApiError("pinpp must contain 14 digits")

    century_gender = int(s[0])
    ddmmyy = s[1:7]  # DDMMYY

    day = int(ddmmyy[0:2])
    month = int(ddmmyy[2:4])
    yy = int(ddmmyy[4:6])

    if century_gender in (1, 2):
        year = 1800 + yy
    elif century_gender in (3, 4):
        year = 1900 + yy
    elif century_gender in (5, 6):
        year = 2000 + yy
    else:
        raise EgovApiError("pinpp century/gender digit must be in 1..6")

    # провалидация даты
    try:
        d = date(year, month, day)
    except ValueError:
        raise EgovApiError("pinpp contains invalid birth date")

    return d.isoformat()  # YYYY-MM-DD
