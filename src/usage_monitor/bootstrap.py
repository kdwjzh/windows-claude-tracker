"""組裝根：建立所有物件並接線，唯一可以 import 所有層的地方。

啟動順序：單一執行個體 → log → 設定 → 服務 → 排程 → Qt（小工具＋系統匣）。
"""

from __future__ import annotations

import logging
import sys
import threading
from types import TracebackType
from typing import TYPE_CHECKING

from usage_monitor import __version__, diagnose
from usage_monitor.core.interfaces import Provider
from usage_monitor.platform import app_identity, autostart, paths, relaunch
from usage_monitor.platform.cli_refresh import ClaudeCliRefresher
from usage_monitor.platform.clock import SystemClock
from usage_monitor.platform.http import RequestsTransport, inject_truststore
from usage_monitor.platform.single_instance import SingleInstance
from usage_monitor.providers import registry
from usage_monitor.providers.claude.provider import ClaudeProvider
from usage_monitor.services.history import History
from usage_monitor.services.logging_setup import setup_logging
from usage_monitor.services.scheduler import Scheduler
from usage_monitor.services.self_update import download_update
from usage_monitor.services.settings.schema import Settings
from usage_monitor.services.settings.store import SettingsStore
from usage_monitor.services.state_store import StateStore
from usage_monitor.services.update_check import UpdateChecker

if TYPE_CHECKING:
    from PySide6.QtCore import QCoreApplication

log = logging.getLogger("usage_monitor.bootstrap")


def _log_uncaught(
    exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
) -> None:
    log.critical("未處理的例外", exc_info=(exc_type, exc, tb))


def _log_thread_exception(args: threading.ExceptHookArgs) -> None:
    log.critical(
        "執行緒 %s 未處理的例外",
        args.thread.name if args.thread else "?",
        exc_info=(args.exc_type, args.exc_value or args.exc_type(), args.exc_traceback),
    )


def quit_app(app: QCoreApplication) -> None:
    """結束程式。不用 app.quit()：它會先請所有視窗關閉，儀表板「關閉只是隱藏」會讓 Qt
    取消結束（看視窗順序，時好時壞；2026-11-05「立即更新」後舊版沒結束）。收尾在 main 的 finally。
    """
    app.exit(0)


def create_all_providers(clock: SystemClock) -> dict[str, Provider]:
    """所有已註冊的服務都先建立（建構時不做 I/O），設定視窗開關服務時直接取用。"""
    transport = RequestsTransport()
    return {pid: registry.create(pid, transport, clock) for pid in registry.available()}


def enabled_providers(settings: Settings, all_providers: dict[str, Provider]) -> list[Provider]:
    result: list[Provider] = []
    for pid in settings.providers:
        if pid in all_providers:
            result.append(all_providers[pid])
        else:
            log.warning("設定中的服務 %r 不存在，略過（可用：%s）", pid, list(all_providers))
    return result


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    replaced = relaunch.replaced_path(argv)  # 「立即更新」啟動的新版：舊版的 exe 路徑
    instance = SingleInstance()
    if not instance.acquire(wait=15.0 if replaced is not None else 0.0):
        return 0  # 已經在執行：不開第二份（新版等不到舊版結束也一樣）

    setup_logging(paths.log_file(), debug="--debug" in argv)
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_thread_exception
    log.info("啟動 v%s", __version__)
    app_identity.report()
    autostart.sync_command()  # 換新版 exe 後，開機啟動跟著指向新的檔案
    current_exe = relaunch.frozen_exe()
    if replaced is not None and current_exe is not None:
        threading.Thread(
            target=relaunch.remove_replaced, args=(replaced, current_exe),
            name="remove-old-exe", daemon=True,
        ).start()  # fmt: skip
    inject_truststore()

    settings_store = SettingsStore(paths.settings_file())
    settings = settings_store.load()
    clock = SystemClock()
    all_providers = create_all_providers(clock)
    claude = all_providers.get(ClaudeProvider.id)
    if isinstance(claude, ClaudeProvider):
        # 階段 7：設定 allow_cli_refresh 開啟時，CLI token 過期才讓 claude 自己更新
        claude.configure_cli_refresh(
            ClaudeCliRefresher(clock), lambda: settings_store.current.allow_cli_refresh
        )
    states = StateStore()
    history = History(paths.history_file(), clock)
    states.subscribe(history.record)  # 只存百分比與時間（ROADMAP 第 5a 項）
    scheduler = Scheduler(
        enabled_providers(settings, all_providers),
        states,
        clock,
        interval_minutes=settings.interval_minutes,
    )

    current_ids = set(settings.providers)

    def on_settings_changed(s: Settings) -> None:
        nonlocal current_ids
        scheduler.set_interval(s.interval_minutes)
        if set(s.providers) != current_ids:
            for removed in current_ids - set(s.providers):
                states.remove(removed)
            current_ids = set(s.providers)
            scheduler.set_providers(enabled_providers(s, all_providers))

    settings_store.subscribe(on_settings_changed)
    # 更新檢查：只連 api.github.com，不帶 token（CLAUDE.md §3.9）
    update_transport = RequestsTransport()
    updates = UpdateChecker(update_transport, clock, settings_store, __version__)

    # Qt 放在最後才 import：診斷工具與測試不需要載入 Qt
    from PySide6.QtWidgets import QApplication

    from usage_monitor.ui.controller import Controller
    from usage_monitor.ui.tray.icon import app_icon

    app = QApplication(argv)
    app.setApplicationName("用量監控")
    app.setWindowIcon(app_icon(paths.app_icon_file()))  # 設定視窗的標題列與工作列圖示
    app.setQuitOnLastWindowClosed(False)
    controller = Controller(
        app,
        settings_store,
        states,
        [(p.id, p.display_name) for p in all_providers.values()],
        clock,
        refresh=scheduler.refresh_now,
        log_file=paths.log_file(),
        on_quit=lambda: quit_app(app),
        settings_file=paths.settings_file(),
        updates=updates,
        history=history,
        diagnose=diagnose.report_text,  # 在主程式裡跑診斷（不再另外發 diagnose.exe）
        download_update=lambda state, folder: download_update(update_transport, state, folder),
    )
    controller.start()
    scheduler.start()
    updates.start()
    try:
        code = app.exec()
    finally:
        log.info("結束")
        controller.shutdown()
        scheduler.stop()
        updates.stop()
        instance.release()
    return code
