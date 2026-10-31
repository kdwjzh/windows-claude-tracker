"""時間的顯示文字（依語言）。內部一律 UTC aware，只有這裡（與 viewmodel）轉成本地時間。

`tz` 參數給測試固定時區用；None 表示系統本地時區。`lang` 預設繁體中文。
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo

from usage_monitor.core.i18n import Lang

_WEEKDAYS = {
    Lang.ZH_TW: "一二三四五六日",
    Lang.EN: ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}

DAYS_ONLY_FROM = 10
"""剩下 10 天以上只顯示天數（「29天」「29d」），以下顯示「4天3時」「4d 3h」。"""


def countdown(resets_at: datetime, now: datetime, lang: Lang = Lang.ZH_TW) -> str:
    """距離重置還有多久。

    中文「4天3時」「2時05分」「48分」「即將重置」；英文「4d 3h」「2h 5m」「48m」「soon」。
    """
    zh = lang is Lang.ZH_TW
    secs = int((resets_at - now).total_seconds())
    if secs < 60:
        return "即將重置" if zh else "soon"
    days, rem = divmod(secs, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes = rem // 60
    if days >= DAYS_ONLY_FROM:
        return f"{days}天" if zh else f"{days}d"
    if days:
        return f"{days}天{hours}時" if zh else f"{days}d {hours}h"
    if hours:
        return f"{hours}時{minutes:02d}分" if zh else f"{hours}h {minutes}m"
    return f"{minutes}分" if zh else f"{minutes}m"


def clock(moment: datetime, tz: tzinfo | None = None) -> str:
    """本地時刻「20:15」（兩種語言都用 24 小時制）。"""
    return moment.astimezone(tz).strftime("%H:%M")


def reset_moment(
    resets_at: datetime, now: datetime, tz: tzinfo | None = None, lang: Lang = Lang.ZH_TW
) -> str:
    """懸停卡用的重置時刻。

    中文「今天 20:20」「明天 08:00」「11/01（六）22:00」；英文「today 20:20」「Sun 11/01 22:00」。
    """
    zh = lang is Lang.ZH_TW
    local = resets_at.astimezone(tz)
    today = now.astimezone(tz).date()
    hm = local.strftime("%H:%M")
    if local.date() == today:
        return f"今天 {hm}" if zh else f"today {hm}"
    if local.date() == today + timedelta(days=1):
        return f"明天 {hm}" if zh else f"tomorrow {hm}"
    weekday = _WEEKDAYS[lang][local.weekday()]
    return f"{local:%m/%d}（{weekday}）{hm}" if zh else f"{weekday} {local:%m/%d} {hm}"


def ago(moment: datetime, now: datetime, lang: Lang = Lang.ZH_TW) -> str:
    """資料多久以前更新。

    中文「剛剛」「12 分鐘前」「3 小時前」「2 天前」；英文「just now」「12 min ago」「2 days ago」。
    """
    zh = lang is Lang.ZH_TW
    secs = int((now - moment).total_seconds())
    if secs < 60:
        return "剛剛" if zh else "just now"
    if secs < 3_600:
        return f"{secs // 60} 分鐘前" if zh else f"{secs // 60} min ago"
    if secs < 86_400:
        return f"{secs // 3_600} 小時前" if zh else f"{secs // 3_600} hr ago"
    days = secs // 86_400
    if zh:
        return f"{days} 天前"
    return f"{days} day ago" if days == 1 else f"{days} days ago"
