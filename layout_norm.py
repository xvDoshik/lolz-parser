from __future__ import annotations

RU_LOWER = "йцукенгшщзхъфывапролджэячсмитьбю"
EN_LOWER = "qwertyuiop[]asdfghjkl;'zxcvbnm,."
RU_UPPER = "ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ"
EN_UPPER = 'QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>'

RU_TO_EN = str.maketrans(RU_LOWER + RU_UPPER, EN_LOWER + EN_UPPER)
EN_TO_RU = str.maketrans(EN_LOWER + EN_UPPER, RU_LOWER + RU_UPPER)


def query_variants(q: str) -> set[str]:
    q = q.strip()
    if not q:
        return set()
    out = {q, q.lower(), q.upper(), q.casefold()}
    flipped_ru = q.translate(RU_TO_EN)
    flipped_en = q.translate(EN_TO_RU)
    out.update({flipped_ru, flipped_en, flipped_ru.lower(), flipped_en.lower()})
    return {x for x in out if x}


def skin_matches_filters(skin_name: str, variants: set[str]) -> bool:
    if not variants:
        return True
    hay = skin_name.casefold()
    for v in variants:
        if not v:
            continue
        if v.casefold() in hay:
            return True
    return False
