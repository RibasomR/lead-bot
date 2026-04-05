"""
## Система локализации LeadHunter
Dict-based i18n с поддержкой RU/EN.
"""

from typing import Any

from shared.locales.ru import STRINGS as RU_STRINGS
from shared.locales.en import STRINGS as EN_STRINGS

_LOCALES = {
    "ru": RU_STRINGS,
    "en": EN_STRINGS,
}

DEFAULT_LANG = "ru"


def t(key: str, lang: str = DEFAULT_LANG, **kwargs: Any) -> str:
    """
    Получить перевод строки по ключу.

    Args:
        key: Ключ строки (точечная нотация: "start.welcome")
        lang: Код языка ("ru" / "en")
        **kwargs: Подстановки для format()

    Returns:
        Переведённая строка. Если ключ не найден — возвращает ключ.
    """
    strings = _LOCALES.get(lang, _LOCALES[DEFAULT_LANG])

    parts = key.split(".")
    value = strings
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = None
            break

    if value is None:
        ## Fallback на русский
        value = RU_STRINGS
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return key
        if value is None:
            return key

    if kwargs and isinstance(value, str):
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError):
            return value

    return value if isinstance(value, str) else key
