# analytics/validators.py
from decimal import Decimal
import re
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DMY = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

def validate_row_against_template(row: dict, template) -> list[str]:
    """
    Возвращает список ошибок валидации. Пусто — значит ок.
    """
    errors = []
    # индекс по canonical_key
    rules = {m.canonical_key: m for m in template.mappings.all()}

    for key, mapping in rules.items():
        val = row.get(key, None)

        if mapping.required and (val is None or str(val).strip() == ""):
            errors.append(f"{key}: обязателен")
            continue

        if val is None or str(val).strip() == "":
            continue

        # тип
        if mapping.dtype == "number":
            try:
                num = Decimal(str(val).replace(",", "."))
            except Exception:
                errors.append(f"{key}: должно быть числом")
                continue
            if mapping.min_value is not None and num < mapping.min_value:
                errors.append(f"{key}: меньше минимального {mapping.min_value}")
            if mapping.max_value is not None and num > mapping.max_value:
                errors.append(f"{key}: больше максимального {mapping.max_value}")

        if mapping.dtype == "date":
            s = str(val)
            if not (ISO.match(s) or DMY.match(s)):
                errors.append(f"{key}: неверный формат даты, нужен DD.MM.YYYY")

        # regex
        if mapping.regex:
            if not re.search(mapping.regex, str(val)):
                errors.append(f"{key}: не соответствует шаблону")

        # choices
        if mapping.choices and str(val) not in mapping.choices:
            errors.append(f"{key}: допустимые значения: {', '.join(mapping.choices)}")

    return errors
