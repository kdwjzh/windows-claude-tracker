"""儀表板「用量」頁的 ViewModel：用量歷史（services.history.Sample）→ 圖表要畫的資料。

純函式、不碰 Qt，可在 Linux 測試。時間一律 UTC aware，只有刻度文字轉成本地時間。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

from usage_monitor.core.i18n import Lang, t
from usage_monitor.core.levels import Level, level_of
from usage_monitor.core.models import ProviderState
from usage_monitor.services.history import Sample
from usage_monitor.ui.viewmodel import (
    DEFAULT_LABELS,
    HoverLineVM,
    ProviderInfo,
    build_column,
    long_label,
    percent_text,
)

LINE_DAYS = 7
GAP_BREAK = timedelta(hours=2)
"""兩筆紀錄相隔超過這麼久（程式沒開、睡眠）就斷開折線，不畫一條假的連線。"""
MAX_CYCLES = 8
AVERAGE_CYCLES = 4
MIN_AVERAGE_CYCLES = 2
"""只有一期時「平均」沒有意義，至少要兩期已結束的週期才顯示。"""

Point = tuple[datetime, float]


@dataclass(frozen=True)
class LineVM:
    start: datetime
    end: datetime
    segments: tuple[tuple[Point, ...], ...]
    """連續的幾段折線；只有一個點的段落畫成圓點。"""
    ticks: tuple[tuple[datetime, str], ...]
    """每天本地午夜的刻度與「11/03」文字。"""


@dataclass(frozen=True)
class BarVM:
    label: str
    """重置日期「11/08」；進行中的週期是「本期」。"""
    percent: float
    level: Level
    current: bool


@dataclass(frozen=True)
class ServiceUsageVM:
    provider_id: str
    title: str
    lines: tuple[HoverLineVM, ...]
    """目前數字＋重置時間（與懸停卡相同）。"""
    error: str | None
    line_title: str
    line: LineVM
    show_line: bool
    """服務沒有短週期（Codex 只有 30 天額度）且沒有紀錄時不畫折線。"""
    bars_title: str
    bars: tuple[BarVM, ...]
    average: str | None


def line_vm(samples: Sequence[Sample], now: datetime, tz: tzinfo | None = None) -> LineVM:
    start = now - timedelta(days=LINE_DAYS)
    segments: list[list[Point]] = []
    last: datetime | None = None
    for s in samples:
        if s.window != "session" or s.fetched_at < start:
            continue
        if last is None or s.fetched_at - last > GAP_BREAK:
            segments.append([])
        segments[-1].append((s.fetched_at, s.percent))
        last = s.fetched_at
    ticks: list[tuple[datetime, str]] = []
    day = start.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= now:
        if day >= start:
            ticks.append((day, f"{day:%m/%d}"))
        # 用日期往後推再重設午夜：遇到夏令時間也不會偏掉
        day = (day + timedelta(days=1, hours=2)).replace(hour=0)
    return LineVM(start, now, tuple(tuple(seg) for seg in segments), tuple(ticks))


def _cycle_key(resets_at: datetime) -> datetime:
    """重置時間四捨五入到整點：API 回的時間可能差幾秒，不能因此拆成兩個週期。"""
    return (resets_at + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)


def cycle_bars(
    samples: Sequence[Sample], now: datetime, tz: tzinfo | None = None, lang: Lang = Lang.ZH_TW
) -> tuple[BarVM, ...]:
    """長週期每一期的最高用量（同一個重置時間＝同一期），最多 MAX_CYCLES 期。"""
    peaks: dict[datetime, float] = {}
    for s in samples:
        if s.window == "long" and s.resets_at is not None:
            key = _cycle_key(s.resets_at)
            peaks[key] = max(peaks.get(key, 0.0), s.percent)
    bars: list[BarVM] = []
    for key in sorted(peaks)[-MAX_CYCLES:]:
        current = key > now
        label = t(lang, "usage_current") if current else f"{key.astimezone(tz):%m/%d}"
        bars.append(BarVM(label, peaks[key], level_of(peaks[key]), current))
    return tuple(bars)


def average_text(bars: Sequence[BarVM], lang: Lang = Lang.ZH_TW) -> str | None:
    done = [b.percent for b in bars if not b.current][-AVERAGE_CYCLES:]
    if len(done) < MIN_AVERAGE_CYCLES:
        return None
    return t(lang, "usage_average", n=len(done), percent=percent_text(sum(done) / len(done)))


def build_service_usage(
    provider: ProviderInfo,
    state: ProviderState | None,
    samples: Sequence[Sample],
    now: datetime,
    tz: tzinfo | None = None,
    lang: Lang = Lang.ZH_TW,
) -> ServiceUsageVM:
    hover = build_column(provider, state, now, tz, lang).hover
    usage = state.usage if state is not None else None
    session_label = (usage.session.label if usage else None) or DEFAULT_LABELS[0]
    long_labels = [s.label for s in samples if s.window == "long" and s.label]
    long = (usage.long.label if usage else None) or (long_labels[-1] if long_labels else None)
    bars = cycle_bars(samples, now, tz, lang)
    line = line_vm(samples, now, tz)
    reports_session = usage is not None and usage.session.available
    return ServiceUsageVM(
        provider_id=provider[0],
        title=provider[1],
        lines=hover.lines,
        error=hover.error,
        line_title=t(lang, "usage_line_title", period=long_label(session_label, lang)),
        line=line,
        show_line=reports_session or bool(line.segments),
        bars_title=t(lang, "usage_bars_title", period=long_label(long or DEFAULT_LABELS[1], lang)),
        bars=bars,
        average=average_text(bars, lang),
    )
