# utils/excel_templates.py
import re
from typing import Dict, List, Optional, Tuple
from django.apps import apps

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def _compile_alias(a: str):
    if a.startswith("re:"):
        return re.compile(a[3:], flags=re.IGNORECASE), True
    return _norm(a), False

def build_template_index(template) -> Dict[str, dict]:
    """
    Возвращает индекс: canonical_key -> {"aliases":[(pattern,is_regex),...], "dtype":..., "required":...}
    """
    out = {}
    for m in template.mappings.all():
        out[m.canonical_key] = {
            "aliases": [_compile_alias(a) for a in m.aliases],
            "dtype": m.dtype,
            "required": m.required,
        }
    return out

def match_headers(headers: List[str], template) -> Tuple[Dict[int,str], List[str], List[str]]:
    """
    Возвращает (map_idx_to_key, missing_keys, extra_headers)
    map_idx_to_key: индекс колонки -> canonical_key
    missing_keys: обязательные canonical_key, которые не нашлись
    extra_headers: заголовки без сопоставления (на будущее — лог/диагностика)
    """
    idx = build_template_index(template)
    hnorm = [(_norm(h), h) for h in headers]
    mapping: Dict[int,str] = {}
    used_keys = set()

    for col, (h_norm, h_raw) in enumerate(hnorm):
        matched_key = None
        for key, info in idx.items():
            if key in used_keys:
                continue
            for patt, is_rx in info["aliases"]:
                if (is_rx and patt.search(h_raw)) or (not is_rx and patt == h_norm):
                    matched_key = key; break
            if matched_key: break
        if matched_key:
            mapping[col] = matched_key
            used_keys.add(matched_key)

    required = {k for k,info in idx.items() if info["required"]}
    missing = sorted(required - used_keys)
    extras = [raw for (n,raw) in hnorm if n and n not in [ _norm(a) for k in idx for a,_ in idx[k]["aliases"] ]]

    return mapping, missing, extras

def detect_best_template(headers: List[str], candidates) -> Optional[Tuple[object,Dict[int,str],List[str]]]:
    """
    Перебирает шаблоны, выбирает тот, где:
      - missing_keys пуст или минимален,
      - покрытие (кол-во совпавших полей) максимальное.
    """
    best = None
    best_score = (-10, -10)  # ( -missing_count, matched_count )
    for t in candidates:
        mapping, missing, _ = match_headers(headers, t)
        score = (-len(missing), len(mapping))
        if score > best_score:
            best_score, best = score, (t, mapping, missing)
    return best
