from __future__ import annotations

from typing import Literal

Lang = Literal["ru", "en", "de"]


def _int_grouped(n: object, lang: Lang) -> str | None:
    if n is None:
        return None
    try:
        v = int(float(n))
    except (TypeError, ValueError):
        return None
    s = f"{abs(v):,}".replace(",", " ")
    if lang == "ru":
        return s
    if lang == "en":
        return s.replace(" ", ",")
    return s.replace(" ", ".")


def _skins_title_phrase(n: int, lang: Lang) -> str:
    n = abs(int(n))
    if lang == "ru":
        return "1 скин" if n == 1 else f"{n} скинов"
    if lang == "en":
        return "1 skin" if n == 1 else f"{n} skins"
    return "1 Skin" if n == 1 else f"{n} Skins"


def build_sell_listing(
    _item_id: str,
    stats: dict | None,
    skin_names: list[str],
    lang: Lang = "ru",
) -> tuple[str, str]:
    n_skins = len(skin_names)

    if lang == "ru":
        parts = ["Brawl Stars аккаунт"]
        if stats:
            lv = _int_grouped(stats.get("brawl_level"), lang)
            if lv is not None:
                parts.append(f"ур {lv}")
            tr = _int_grouped(stats.get("trophies"), lang)
            if tr is not None:
                parts.append(f"{tr} кубков")
            br = _int_grouped(stats.get("brawlers"), lang)
            if br is not None:
                parts.append(f"{br} бр")
            leg_n = _safe_int(stats.get("legendary"))
            if leg_n > 0:
                parts.append(f"{leg_n} лег")
            hz_n = _safe_int(stats.get("hypercharges"))
            if hz_n > 0:
                parts.append(f"{hz_n} гз")
        if n_skins:
            parts.append(_skins_title_phrase(n_skins, lang))
    elif lang == "en":
        parts = ["Brawl Stars account"]
        if stats:
            lv = _int_grouped(stats.get("brawl_level"), lang)
            if lv is not None:
                parts.append(f"Lv {lv}")
            tr = _int_grouped(stats.get("trophies"), lang)
            if tr is not None:
                parts.append(f"{tr} cups")
            br = _int_grouped(stats.get("brawlers"), lang)
            if br is not None:
                parts.append(f"{br} br")
            leg_n = _safe_int(stats.get("legendary"))
            if leg_n > 0:
                parts.append(f"{leg_n} leg")
            hz_n = _safe_int(stats.get("hypercharges"))
            if hz_n > 0:
                parts.append(f"{hz_n} HC")
        if n_skins:
            parts.append(_skins_title_phrase(n_skins, lang))
    else:
        parts = ["Brawl Stars Konto"]
        if stats:
            lv = _int_grouped(stats.get("brawl_level"), lang)
            if lv is not None:
                parts.append(f"Lvl {lv}")
            tr = _int_grouped(stats.get("trophies"), lang)
            if tr is not None:
                parts.append(f"{tr} Pokale")
            br = _int_grouped(stats.get("brawlers"), lang)
            if br is not None:
                parts.append(f"{br} Br")
            leg_n = _safe_int(stats.get("legendary"))
            if leg_n > 0:
                parts.append(f"{leg_n} Leg")
            hz_n = _safe_int(stats.get("hypercharges"))
            if hz_n > 0:
                parts.append(f"{hz_n} Hyper")
        if n_skins:
            parts.append(_skins_title_phrase(n_skins, lang))

    title = " · ".join(parts)

    lines: list[str] = []
    if lang == "ru":
        lines.append("Аккаунт Brawl Stars")
    elif lang == "en":
        lines.append("Brawl Stars account")
    else:
        lines.append("Brawl-Stars-Konto")
    lines.append("")

    if stats:
        lv = _int_grouped(stats.get("brawl_level"), lang)
        tr = _int_grouped(stats.get("trophies"), lang)
        br = _int_grouped(stats.get("brawlers"), lang)
        leg_n = _safe_int(stats.get("legendary"))
        hz_n = _safe_int(stats.get("hypercharges"))
        if lang == "ru":
            if lv is not None:
                lines.append(f"• Уровень аккаунта: {lv}")
            if tr is not None:
                lines.append(f"• Трофеи (кубки): {tr}")
            if br is not None:
                lines.append(f"• Бравлеры: {br}")
            if leg_n > 0:
                lines.append(f"• Легендарные бравлеры: {leg_n}")
            if hz_n > 0:
                lines.append(f"• Гиперзаряды: {hz_n}")
        elif lang == "en":
            if lv is not None:
                lines.append(f"• Account level: {lv}")
            if tr is not None:
                lines.append(f"• Trophies (cups): {tr}")
            if br is not None:
                lines.append(f"• Brawlers: {br}")
            if leg_n > 0:
                lines.append(f"• Legendary brawlers: {leg_n}")
            if hz_n > 0:
                lines.append(f"• Hypercharges: {hz_n}")
        else:
            if lv is not None:
                lines.append(f"• Kontostand (Level): {lv}")
            if tr is not None:
                lines.append(f"• Trophäen (Pokale): {tr}")
            if br is not None:
                lines.append(f"• Brawler: {br}")
            if leg_n > 0:
                lines.append(f"• Legendäre Brawler: {leg_n}")
            if hz_n > 0:
                lines.append(f"• Hyperladungen: {hz_n}")
        lines.append("")
    elif not skin_names:
        if lang == "ru":
            lines.append("• Статистика в базе не заполнена — уточните у продавца.")
        elif lang == "en":
            lines.append("• Stats not in our snapshot — ask the seller.")
        else:
            lines.append("• Keine Statistik in der Datenbank — beim Verkäufer nachfragen.")
        lines.append("")

    if skin_names:
        if lang == "ru":
            lines.append("Скины на аккаунте")
        elif lang == "en":
            lines.append("Skins on the account")
        else:
            lines.append("Skins auf dem Konto")
        show = skin_names[:45]
        for sn in show:
            lines.append(f"• {sn}")
        if len(skin_names) > len(show):
            if lang == "ru":
                lines.append(f"• … и ещё {len(skin_names) - len(show)}")
            elif lang == "en":
                lines.append(f"• … +{len(skin_names) - len(show)} more")
            else:
                lines.append(f"• … +{len(skin_names) - len(show)} weitere")
        lines.append("")
    elif stats:
        if lang == "ru":
            lines.append("Скины на аккаунте")
            lines.append("• В базе не отмечены — уточните у продавца.")
        elif lang == "en":
            lines.append("Skins on the account")
            lines.append("• Not listed in our data — ask the seller.")
        else:
            lines.append("Skins auf dem Konto")
            lines.append("• In der Datenbank nicht vermerkt — beim Verkäufer nachfragen.")
        lines.append("")

    if lang == "ru":
        lines.append(
            "Данные аккаунта могут меняться и быть неточными, перед покупкой уточните "
            "интересующие статистики у продавца."
        )
    elif lang == "en":
        lines.append(
            "Account data may change and be inaccurate; before purchase confirm any stats "
            "that matter with the seller."
        )
    else:
        lines.append(
            "Die Angaben können sich ändern und ungenau sein; bitte alle wichtigen Werte "
            "vor dem Kauf beim Verkäufer bestätigen."
        )

    return title, "\n".join(lines).rstrip() + "\n"


def _safe_int(v: object) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def build_sell_bundle(
    item_id: str,
    stats: dict | None,
    skin_names: list[str],
) -> dict[str, str]:
    tr, dr = build_sell_listing(item_id, stats, skin_names, "ru")
    te, de = build_sell_listing(item_id, stats, skin_names, "en")
    tg, dg = build_sell_listing(item_id, stats, skin_names, "de")
    return {
        "title": tr,
        "description": dr,
        "title_en": te,
        "description_en": de,
        "title_de": tg,
        "description_de": dg,
    }
