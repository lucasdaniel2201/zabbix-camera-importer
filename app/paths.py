"""Resolucao de caminhos para rodar tanto do codigo-fonte quanto do .exe.

Quando empacotado com PyInstaller:
- os arquivos embutidos (fontes, imagens) ficam em sys._MEIPASS (temporario);
- os arquivos gerados (relatorios, log de erro) NAO podem ir para la - seriam
  apagados ao fechar.

Onde gravar as saidas, em ordem de preferencia:
1. pasta do proprio .exe (instalacao por usuario, ex.: %LOCALAPPDATA%);
2. pasta de dados do usuario (%LOCALAPPDATA%\\ImportadorZabbix), quando a do
   .exe for somente leitura (ex.: instalado em Program Files ou rodando de
   unidade de rede / midia somente leitura).
"""

import os
import sys
from pathlib import Path

# Raiz do projeto no modo codigo-fonte (pasta que contem app/ e os scripts).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Nome da pasta de dados do usuario, usada quando a pasta do .exe nao e gravavel.
APP_FOLDER_NAME = "ImportadorZabbix"


def is_frozen() -> bool:
    """True quando rodando como executavel empacotado."""
    return bool(getattr(sys, "frozen", False))


def resource_path(*parts: str) -> Path:
    """Caminho de um recurso embutido (somente leitura).

    No .exe aponta para a pasta de extracao do PyInstaller; no codigo-fonte,
    para a raiz do projeto.
    """
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    else:
        base = PROJECT_ROOT
    return base.joinpath(*parts)


def is_writable(directory: Path) -> bool:
    """Testa de verdade se da para escrever na pasta (cria e apaga um arquivo).

    os.access(..., W_OK) no Windows nao e confiavel para pastas, entao testa
    na pratica.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".escrita_teste"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def user_data_dir() -> Path:
    """Pasta de dados do usuario (fallback quando a do .exe nao e gravavel)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_FOLDER_NAME


def writable_base() -> Path:
    """Diretorio base gravavel para saidas.

    - codigo-fonte: raiz do projeto;
    - .exe: a pasta do executavel, se der para escrever nela;
    - .exe em local somente leitura: pasta de dados do usuario.
    """
    if not is_frozen():
        return PROJECT_ROOT

    exe_dir = Path(sys.executable).resolve().parent
    if is_writable(exe_dir):
        return exe_dir
    return user_data_dir()


def output_dir(name: str = "reports") -> Path:
    """Pasta gravavel para saidas (relatorios), criada se necessario."""
    target = writable_base() / name
    target.mkdir(parents=True, exist_ok=True)
    return target
