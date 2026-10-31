"""進入點：python -m usage_monitor。"""

from usage_monitor.platform import app_identity

# 工作列圖示與分組：必須在建立任何 Qt 視窗之前設定
app_identity.apply()

from usage_monitor.bootstrap import main  # noqa: E402 - 刻意放在 app_identity.apply() 之後

if __name__ == "__main__":
    raise SystemExit(main())
