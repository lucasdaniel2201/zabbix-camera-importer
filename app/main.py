"""Ponto de entrada do app: python -m app.main (ou pythonw -m app.main)."""

import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main_window import MainWindow  # noqa: E402
from app.paths import resource_path, writable_base  # noqa: E402

FONTS_DIR = resource_path("app", "assets", "fonts")
ICON_PNG = resource_path("app", "assets", "app_icon.png")

# Fonte da interface. "Inter" e empacotada em app/assets/fonts; se por algum motivo
# nao carregar, cai para fontes do sistema.
UI_FONT_FAMILY = "Segoe UI"


def error_log_path():
    """Log de erros: ao lado do .exe quando empacotado; na raiz em desenvolvimento."""
    return writable_base() / "app_error.log"


ERROR_LOG = error_log_path()


def load_brand_fonts() -> str:
    """Registra as fontes Inter empacotadas. Retorna a familia a usar na UI."""
    global UI_FONT_FAMILY
    if not FONTS_DIR.is_dir():
        return UI_FONT_FAMILY

    loaded_families: list[str] = []
    for font_file in sorted(FONTS_DIR.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        if font_id >= 0:
            loaded_families.extend(QFontDatabase.applicationFontFamilies(font_id))

    if "Inter" in loaded_families:
        UI_FONT_FAMILY = "Inter"
        return UI_FONT_FAMILY

    # variavel (Inter Variable) tambem serve
    for family in loaded_families:
        if family.lower().startswith("inter"):
            UI_FONT_FAMILY = family
            return UI_FONT_FAMILY

    return UI_FONT_FAMILY


def app_icon() -> QIcon:
    """Icone do app (assets/app_icon.png), com fallback silencioso."""
    return QIcon(str(ICON_PNG)) if ICON_PNG.exists() else QIcon()


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    """Garante que erros aparecam mesmo rodando sem console (pythonw)."""
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        ERROR_LOG.write_text(details, encoding="utf-8")
    except Exception:
        pass
    try:
        QMessageBox.critical(
            None,
            "Erro inesperado",
            f"Ocorreu um erro inesperado. Detalhes salvos em:\n{ERROR_LOG}\n\n{exc_value}",
        )
    except Exception:
        pass


sys.excepthook = _excepthook

APP_STYLE = """
* {
    font-family: "__UI_FONT__", "Segoe UI", "Inter", sans-serif;
}
QWidget {
    color: #1f2937;
    font-size: 13px;
}
QMainWindow, QStackedWidget, QDialog {
    background: #eef1f6;
}
QLabel {
    background: transparent;
    color: #1f2937;
}
QFrame#brandBanner {
    background: #2563eb;
    border: none;
}
QLabel#brandTitle {
    color: #ffffff;
    font-size: 21px;
    font-weight: 700;
    letter-spacing: -0.2px;
}
QLabel#brandSubtitle {
    color: rgba(255, 255, 255, 0.82);
    font-size: 11px;
    letter-spacing: 0.3px;
}
QLabel#brandSession {
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
}
QLabel#loginFooter {
    color: #8b93a3;
    font-size: 11px;
    letter-spacing: 0.2px;
}
QFrame#card {
    background: #ffffff;
    border: 1px solid #dfe3ea;
    border-radius: 14px;
}
QLabel#cardTitle {
    font-size: 20px;
    font-weight: 700;
    color: #111827;
    letter-spacing: -0.2px;
}
QLabel#cardSubtitle {
    color: #6b7280;
    font-size: 12px;
}
QLabel#fieldLabel {
    color: #374151;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 0.2px;
}
QPushButton#bannerButton {
    background: rgba(255, 255, 255, 0.16);
    border: 1px solid rgba(255, 255, 255, 0.55);
    border-radius: 6px;
    color: #ffffff;
    padding: 6px 12px;
    font-weight: 600;
    letter-spacing: 0.2px;
}
QPushButton#bannerButton:hover {
    background: rgba(255, 255, 255, 0.28);
}
QPushButton#bannerButton:disabled {
    background: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.55);
    border-color: rgba(255, 255, 255, 0.25);
}
QPushButton#flatButton {
    background: transparent;
    border: none;
    color: #6b7280;
    padding: 4px 6px;
    font-weight: 600;
}
QPushButton#flatButton:hover {
    color: #2563eb;
}
QGroupBox {
    background: #ffffff;
    border: 1px solid #dfe3ea;
    border-radius: 10px;
    /* A faixa do titulo precisa ser mais alta que o texto (senao ele corta a borda). */
    margin-top: 26px;
    padding: 10px 12px 12px 12px;
    font-weight: 600;
    font-size: 13px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 4px 6px 0 6px;
    color: #111827;
    letter-spacing: 0.2px;
}
QLineEdit, QSpinBox, QComboBox {
    background: #ffffff;
    color: #1f2937;
    border: 1px solid #c9cfda;
    border-radius: 7px;
    padding: 7px 9px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #2563eb;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #1f2937;
    border: 1px solid #c9cfda;
    selection-background-color: #dbeafe;
    selection-color: #1f2937;
    outline: none;
}
QCheckBox {
    color: #1f2937;
}
QToolTip {
    background: #1f2937;
    color: #ffffff;
    border: 1px solid #111827;
    padding: 5px 7px;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #c9cfda;
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 600;
    color: #374151;
}
QPushButton:hover {
    background: #f3f5f9;
    border-color: #b6bdcb;
}
QPushButton:disabled {
    background: #f1f3f7;
    color: #a2a8b4;
    border-color: #e1e5ec;
}
QPushButton#primaryButton {
    background: #2563eb;
    border: none;
    color: #ffffff;
}
QPushButton#primaryButton:hover {
    background: #1d4ed8;
}
QPushButton#primaryButton:pressed {
    background: #1e40af;
}
QPushButton#primaryButton:disabled {
    background: #e9ecf2;
    color: #98a0ad;
    border: 1px solid #dfe3ea;
}
QTableWidget {
    background: #ffffff;
    color: #1f2937;
    alternate-background-color: #f4f6fa;
    border: 1px solid #dfe3ea;
    border-radius: 10px;
    gridline-color: #eaedf2;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QTableWidget::item {
    color: #1f2937;
    padding: 5px;
}
QTableWidget::item:selected {
    background: #2563eb;
    color: #ffffff;
}
QHeaderView::section {
    background: #f4f6fa;
    border: none;
    border-bottom: 1px solid #dfe3ea;
    padding: 7px;
    font-weight: 700;
    color: #374151;
}
QProgressBar {
    background: #e3e7ee;
    border: none;
    border-radius: 7px;
    text-align: center;
    min-height: 20px;
    color: #1f2937;
}
QProgressBar::chunk {
    background: #2563eb;
    border-radius: 7px;
}
QDialog {
    background: #eef1f6;
}
"""


def build_light_palette() -> QPalette:
    """Paleta clara fixa: nao depende do tema (claro/escuro) do Windows."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#eef1f6"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1f2937"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f4f6fa"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1f2937"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9aa1ad"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#374151"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1f2937"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2563eb"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#a2a8b4"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#a2a8b4"))
    return palette


def main() -> int:
    app = QApplication(sys.argv)
    # Nao usar setApplicationDisplayName: o Qt anexa esse nome ao titulo de cada
    # janela, gerando titulos duplicados (ex.: "Importador Zabbix - Importador Zabbix").
    app.setApplicationName("Importador Zabbix")
    app.setStyle("Fusion")

    family = load_brand_fonts()
    app.setFont(QFont(family, 10))
    app.setPalette(build_light_palette())
    app.setStyleSheet(APP_STYLE.replace("__UI_FONT__", family))

    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
