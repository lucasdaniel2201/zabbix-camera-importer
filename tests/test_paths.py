"""Testes da resolucao de caminhos (app/paths.py).

Protege o funcionamento do .exe: recursos devem sair do bundle (temporario) e
saidas (relatorios) devem ficar em pasta gravavel ao lado do executavel.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import paths  # noqa: E402


class TestModoFonte(unittest.TestCase):
    def test_nao_esta_congelado(self):
        self.assertFalse(paths.is_frozen())

    def test_recursos_na_raiz_do_projeto(self):
        esperado = paths.PROJECT_ROOT / "app" / "assets"
        self.assertEqual(paths.resource_path("app", "assets"), esperado)
        self.assertTrue(esperado.is_dir())

    def test_base_gravavel_e_a_raiz_do_projeto(self):
        self.assertEqual(paths.writable_base(), paths.PROJECT_ROOT)

    def test_assets_do_app_existem(self):
        for nome in ("app_icon.png", "app_icon.ico"):
            with self.subTest(arquivo=nome):
                self.assertTrue(paths.resource_path("app", "assets", nome).exists())

    def test_fontes_inter_existem(self):
        fontes = paths.resource_path("app", "assets", "fonts")
        self.assertTrue(fontes.is_dir())
        self.assertTrue(list(fontes.glob("Inter-*.ttf")))


class TestModoEmpacotado(unittest.TestCase):
    """Simula o ambiente do PyInstaller (sys.frozen / sys._MEIPASS)."""

    def _frozen(self, exe_dir: Path, meipass: str):
        return [
            mock.patch.object(sys, "frozen", True, create=True),
            mock.patch.object(sys, "executable", str(exe_dir / "ImportadorZabbix.exe")),
            mock.patch.object(sys, "_MEIPASS", meipass, create=True),
        ]

    def test_detecta_empacotado(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertTrue(paths.is_frozen())

    def test_recursos_vem_do_bundle_temporario(self):
        exe_dir = Path(r"C:\Apps\App")
        patches = self._frozen(exe_dir, r"C:\Temp\_MEI999")
        with patches[0], patches[1], patches[2]:
            caminho = paths.resource_path("app", "assets")
        self.assertEqual(caminho, Path(r"C:\Temp\_MEI999\app\assets"))

    def test_saidas_ficam_ao_lado_do_exe(self):
        """Instalacao por usuario (%LOCALAPPDATA%): a pasta do exe e gravavel."""
        with tempfile.TemporaryDirectory() as tmp:
            exe_dir = Path(tmp).resolve()
            patches = self._frozen(exe_dir, r"C:\Temp\_MEI999")
            with patches[0], patches[1], patches[2]:
                base = paths.writable_base()
            self.assertEqual(base, exe_dir)

    def test_relatorios_nunca_no_diretorio_temporario(self):
        """Se cair no _MEIPASS, os relatorios seriam apagados ao fechar o app."""
        exe_dir = Path(r"C:\Apps\App")
        meipass = r"C:\Temp\_MEI999"
        patches = self._frozen(exe_dir, meipass)
        with patches[0], patches[1], patches[2]:
            destino = paths.writable_base() / "reports"
        self.assertFalse(
            str(destino).startswith(meipass),
            "relatorios nao podem ir para a pasta temporaria do PyInstaller",
        )

    def test_cai_para_dados_do_usuario_quando_exe_nao_e_gravavel(self):
        """Ex.: instalado em Program Files - nao da para escrever ao lado do .exe."""
        exe_dir = Path(r"C:\Program Files\Importador Zabbix")
        patches = self._frozen(exe_dir, r"C:\Temp\_MEI999")
        with patches[0], patches[1], patches[2]:
            with mock.patch.object(paths, "is_writable", return_value=False):
                base = paths.writable_base()
        self.assertNotEqual(base, exe_dir)
        self.assertEqual(base.name, paths.APP_FOLDER_NAME)

    def test_nao_cai_para_usuario_quando_exe_e_gravavel(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe_dir = Path(tmp).resolve()
            patches = self._frozen(exe_dir, r"C:\Temp\_MEI999")
            with patches[0], patches[1], patches[2]:
                with mock.patch.object(paths, "is_writable", return_value=True):
                    self.assertEqual(paths.writable_base(), exe_dir)


class TestEscrita(unittest.TestCase):
    def test_is_writable_em_pasta_normal(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(paths.is_writable(Path(tmp)))

    def test_is_writable_cria_a_pasta_se_faltar(self):
        with tempfile.TemporaryDirectory() as tmp:
            nova = Path(tmp) / "sub" / "pasta"
            self.assertTrue(paths.is_writable(nova))
            self.assertTrue(nova.is_dir())

    def test_is_writable_nao_deixa_arquivo_de_teste(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths.is_writable(Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
