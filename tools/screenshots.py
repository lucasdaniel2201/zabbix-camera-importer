"""Utilitario de desenvolvimento: gera screenshots reais do app sem abrir janela.

Roda a interface com `QT_QPA_PLATFORM=offscreen`, reproduzindo a configuracao do
`app/main.py` (tema Fusion, fonte da marca e paleta clara) e salva PNGs prontos
para o README em `docs/screenshots/`.

Como rodar:

    python tools/screenshots.py

E um utilitario de desenvolvimento, nao um teste: instancia a `MainWindow` de
verdade e simula a sessao com dados inteiramente ficticios (nenhum host, IP ou
nome de cliente real). Os PNGs sao sobrescritos a cada execucao.

Atencao: `import app.main` instala um `sys.excepthook` global (efeito colateral
do modulo, usado para exibir erros mesmo rodando sem console). Aqui isso e
aceitavel e inofensivo para o proposito do script.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

# Precisa vir ANTES de qualquer import do PySide6: o Qt decide a plataforma de
# janela na inicializacao, e o offscreen garante que nada apareca na tela.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import app.main as main_mod  # noqa: E402
from app.main_window import MainWindow  # noqa: E402

OUT_DIR = ROOT / "docs" / "screenshots"

# Endereco ficticio do Zabbix. Nao aparece na tela de login, mas mantem a janela
# coerente caso algum estado futuro exiba a URL.
FICTITIOUS_URL = "https://zabbix.exemplo.local"

# Listas do servidor, inventadas: nenhum grupo, template ou proxy real.
GRUPOS = [("10", "CFTV - Matriz"), ("11", "CFTV - Filiais")]
PROXIES = [("20", "Proxy - Unidade SP"), ("21", "Proxy - Unidade RJ")]
TEMPLATES = [("30", "Template ICMP Ping"), ("31", "Template Module Generic")]

# Planilha ficticia no formato que o app gera (rotulos em portugues). Todas as
# linhas sao validas de proposito: o preview aparece com o botao de importar
# liberado, que e o estado que interessa mostrar no README.
PLANILHA_FICTICIA = """\
Nome do host,IP,Fabricante,Modelo,Firmware,Endereço MAC,Unidade,Etiqueta,Descrição
CAM-ENTRADA-PRINCIPAL,10.0.0.10,Hikvision,DS-2CD2043G2-I,V5.7.5,AA-BB-CC-00-00-01,AME-STP2,site:MATRIZ,Camera do portao principal
CAM-ESTACIONAMENTO,10.0.0.11,Dahua,IPC-HFW1234E-Z,V2.800.0,AA-BB-CC-00-00-02,AME-STP2,site:MATRIZ,Camera do estacionamento
CAM-CORREDOR-FUNDO,10.0.0.12,Dahua,IPC-HFW1234E-Z,V2.800.0,AA-BB-CC-00-00-03,AME-STP2,site:MATRIZ,Corredor de fundo
CAM-PORTARIA-SERVICOS,10.0.0.13,Hikvision,DS-2CD2143G2-I,V5.7.5,AA-BB-CC-00-00-04,AME-STP2,site:MATRIZ,Portaria de servicos
CAM-RECEPCAO,10.0.0.14,Hikvision,DS-2CD2043G2-I,V5.7.5,AA-BB-CC-00-00-05,AME-STP2,site:MATRIZ,Recepcao
CAM-DOCA-01,10.0.0.15,Intelbras,VIP-1230-B,V1.0.0,AA-BB-CC-00-00-06,CD-LOG,site:CD,Doca de carga 1
"""


def settle(app: QApplication, seconds: float = 0.5) -> None:
    """Processa eventos por alguns instantes para layout e animacoes assentarem.

    O `window.grab()` de uma janela recem-exibida pode sair em branco; chamar
    `processEvents()` em loop (em vez de uma unica vez) deixa o Qt desenhar e
    concluir as animacoes de entrada dos avisos.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def clear_toasts(window: MainWindow, app: QApplication) -> None:
    """Remove os avisos da tela para o print sair limpo."""
    for item in list(window._toast._items):
        item.close_now()
    app.processEvents()


def capture(window: MainWindow, filename: str, app: QApplication) -> None:
    """Exibe a janela, aguarda o layout e salva o PNG em docs/screenshots/."""
    window.resize(1240, 900)
    window.show()
    settle(app, 0.5)

    pixmap = window.grab()
    destino = OUT_DIR / filename
    if not pixmap.save(str(destino), "PNG"):
        raise RuntimeError(f"Nao consegui gravar o screenshot: {destino}")

    print(f"Gerado: {destino} ({pixmap.width()}x{pixmap.height()})")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    # Mesma configuracao do app/main.py: Fusion, fonte da marca, paleta e QSS.
    app.setApplicationName("Importador Zabbix")
    app.setStyle("Fusion")
    family = main_mod.load_brand_fonts()
    app.setFont(QFont(family, 10))
    app.setPalette(main_mod.build_light_palette())
    app.setStyleSheet(main_mod.APP_STYLE.replace("__UI_FONT__", family))

    icon = main_mod.app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    window: MainWindow | None = None
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "cameras_exemplo.csv"
        csv_path.write_text(PLANILHA_FICTICIA, encoding="utf-8")

        try:
            window = MainWindow()
            window._url = FICTITIOUS_URL

            # 1) Login: estado inicial, usuario e senha em branco.
            capture(window, "login.png", app)

            # 2) Planilha carregada: sessao conectada, listas do servidor
            # preenchidas, um grupo e um template marcados e o preview validado.
            window._on_connected("analista.exemplo")
            window._on_options_ready(GRUPOS, PROXIES, TEMPLATES)
            window.group_combo.set_items(GRUPOS, [GRUPOS[0][0]], select_first_if_empty=False)
            window.template_combo.set_items(
                TEMPLATES, [TEMPLATES[0][0]], select_first_if_empty=False
            )
            window._load_file(csv_path)
            settle(app, 0.4)
            clear_toasts(window, app)
            capture(window, "planilha.png", app)

            # 3) Importacao em andamento: barra de progresso e botao de cancelar
            # visiveis, com o aviso do resumo em andamento no canto.
            window._set_importing_state(True)
            window._on_progress(3, 6, "CAM-CORREDOR-FUNDO", "criando")
            window._notify("Importando 6 cameras...", "info", duration_ms=8000)
            settle(app, 0.5)
            capture(window, "importacao.png", app)
        finally:
            if window is not None:
                # Volta ao estado ocioso antes de fechar: com `_importing` ligado
                # o `closeEvent` abriria um QMessageBox modal de confirmacao, que
                # nunca seria respondido no modo offscreen.
                window._set_importing_state(False)
                window.close()
                app.processEvents()

    return 0


if __name__ == "__main__":
    sys.exit(main())
