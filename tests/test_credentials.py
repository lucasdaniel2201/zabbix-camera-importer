"""Testes de credenciais: nada de senha em disco, nada de senha em codigo.

Protege a decisao de nao guardar credenciais em arquivo (.env) e garante que
nenhuma senha fique embutida no codigo.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestSemArquivoDeCredenciais(unittest.TestCase):
    def test_nao_existe_env(self):
        self.assertFalse((ROOT / ".env").exists())
        self.assertFalse((ROOT / ".env.example").exists())

    def test_nenhum_script_usa_dotenv(self):
        for script in ROOT.glob("*.py"):
            with self.subTest(script=script.name):
                self.assertNotIn("dotenv", script.read_text(encoding="utf-8"))

    def test_nenhuma_senha_embutida_no_codigo(self):
        """Nenhum .py deve conter password= seguido de string literal."""
        import re

        padrao = re.compile(r"""password\s*[=:]\s*["'][^"']+["']""")
        for script in list(ROOT.glob("*.py")) + list((ROOT / "app").glob("*.py")):
            with self.subTest(script=script.name):
                for linha in script.read_text(encoding="utf-8").splitlines():
                    if linha.strip().startswith("#"):
                        continue
                    self.assertIsNone(
                        padrao.search(linha),
                        f"credencial embutida em {script.name}: {linha.strip()}",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
