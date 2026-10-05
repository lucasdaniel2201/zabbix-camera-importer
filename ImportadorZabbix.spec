# -*- mode: python ; coding: utf-8 -*-
"""Build do executavel: pyinstaller ImportadorZabbix.spec

Gera um unico arquivo ImportadorZabbix.exe (sem console), com o icone da marca e
os assets embutidos (logo, icone e fonte Inter).
"""

from pathlib import Path

ROOT = Path(SPECPATH)

# Modulos grandes que o app nao usa - cortam bastante o tamanho do .exe.
#
# CUIDADO: nao excluir da stdlib o que as dependencias usam. Exemplos que ja
# quebraram o .exe: "email" (requests/urllib3) e "xml" (openpyxl le xlsx, que e
# um zip de XMLs).
EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "tkinter",
    "numpy",
    "scipy",
    "matplotlib",
    "pandas",
]

a = Analysis(
    ["run_app.py"],
    pathex=[str(ROOT)],
    binaries=[],
    # Assets embutidos: o codigo os procura em app/assets via app/paths.py.
    datas=[(str(ROOT / "app" / "assets"), "app/assets")],
    hiddenimports=[
        # Modulo da raiz importado pelo app (garantia explicita).
        "zabbix_importer",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ImportadorZabbix",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX desligado: compressao costuma disparar falso positivo de antivirus,
    # o que atrapalharia a distribuicao interna.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "app" / "assets" / "app_icon.ico"),
    version=str(ROOT / "version_info.txt"),
)
