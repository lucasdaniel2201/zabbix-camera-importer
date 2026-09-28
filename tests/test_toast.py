"""Testes das notificacoes (app/toast.py).

Rodam em modo offscreen (sem janela real). Cobrem as regras de UX que
implementamos: empilhamento, limite de itens, pausa no hover, fechamento.
"""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from app import toast as toast_mod  # noqa: E402

_app = QApplication.instance() or QApplication([])


class ToastTestCase(unittest.TestCase):
    def setUp(self):
        self.host = QWidget()
        self.host.resize(1240, 900)
        self.host.show()
        self.manager = toast_mod.ToastManager(self.host)
        self.manager.set_top_offset(90)
        QApplication.processEvents()

    def tearDown(self):
        for item in list(self.manager._items):
            item._timer.stop()
        self.host.close()
        QApplication.processEvents()

    def test_notificacao_aparece(self):
        self.manager.notify("Teste", "info")
        QApplication.processEvents()
        self.assertEqual(len(self.manager._items), 1)
        # isHidden() reflete o estado explicito do widget (nao depende do pai).
        self.assertFalse(self.manager._items[0].isHidden())

    def test_empilha_sem_sobrepor(self):
        for i in range(3):
            self.manager.notify(f"Mensagem {i}", "info")
        QApplication.processEvents()

        itens = self.manager._items
        self.assertEqual(len(itens), 3)
        for anterior, seguinte in zip(itens, itens[1:], strict=False):
            self.assertGreaterEqual(
                seguinte.y(),
                anterior.y() + anterior.height(),
                "itens nao podem se sobrepor",
            )

    def test_limite_de_itens_visiveis(self):
        for i in range(toast_mod.MAX_VISIBLE + 3):
            self.manager.notify(f"Mensagem {i}", "info")
        QApplication.processEvents()
        self.assertEqual(len(self.manager._items), toast_mod.MAX_VISIBLE)

    def test_altura_consistente_para_mesmo_texto(self):
        for _ in range(3):
            self.manager.notify("Mesmo texto em todas as notificacoes.", "info")
        QApplication.processEvents()
        alturas = {item.height() for item in self.manager._items}
        self.assertEqual(len(alturas), 1)

    def test_altura_minima_respeitada(self):
        self.manager.notify("Ok.", "success")
        QApplication.processEvents()
        self.assertGreaterEqual(self.manager._items[0].height(), toast_mod.TOAST_MIN_HEIGHT)

    def test_posicionado_no_canto_superior_direito(self):
        self.manager.notify("Teste", "info")
        QApplication.processEvents()
        esperado_x = self.host.width() - toast_mod.TOAST_WIDTH - toast_mod.MARGIN
        self.assertEqual(self.manager.x(), esperado_x)
        self.assertEqual(self.manager.y(), 90)

    def test_top_offset_atualiza_posicao(self):
        self.manager.set_top_offset(204)
        QApplication.processEvents()
        self.assertEqual(self.manager.y(), 204)

    def test_hover_pausa_o_auto_fechamento(self):
        self.manager.notify("Teste", "info")
        QApplication.processEvents()
        item = self.manager._items[0]
        self.assertTrue(item._timer.isActive())

        item.enterEvent(None)
        self.assertFalse(item._timer.isActive(), "hover deve pausar o fechamento")

        item.leaveEvent(None)
        self.assertTrue(item._timer.isActive(), "sair deve retomar o fechamento")

    def test_fechar_remove_o_item(self):
        self.manager.notify("Teste", "info")
        QApplication.processEvents()
        item = self.manager._items[0]

        item.close_now()
        QApplication.processEvents()
        self.assertEqual(len(self.manager._items), 0)

    def test_duracao_por_gravidade(self):
        """Erro deve permanecer mais tempo que informacao."""
        self.assertGreater(
            toast_mod.KIND_STYLES["error"]["duration"],
            toast_mod.KIND_STYLES["info"]["duration"],
        )
        self.assertGreater(
            toast_mod.KIND_STYLES["warning"]["duration"],
            toast_mod.KIND_STYLES["success"]["duration"],
        )

    def test_tipos_tem_icone_e_cor(self):
        for kind in ("success", "error", "warning", "info"):
            with self.subTest(kind=kind):
                estilo = toast_mod.KIND_STYLES[kind]
                self.assertTrue(estilo["icon"])
                self.assertTrue(estilo["accent"].startswith("#"))

    def test_duracao_explicita_sobrepoe_o_padrao(self):
        self.manager.notify("Teste", "info", duration_ms=12000)
        QApplication.processEvents()
        self.assertEqual(self.manager._items[0]._duration, 12000)

    def test_icones_existem_na_fonte_da_ui(self):
        """Simbolo fora da fonte cai em fallback e renderiza deformado.

        Bug real: o icone de erro usava U+2715, ausente na Inter, e aparecia
        como uma linha vertical no lugar de um X.
        """
        from PySide6.QtGui import QFont, QRawFont

        import app.main as main_mod

        family = main_mod.load_brand_fonts()
        raw = QRawFont.fromFont(QFont(family, 12))

        for kind, estilo in toast_mod.KIND_STYLES.items():
            with self.subTest(kind=kind):
                caracteres = [estilo["icon"]]
                glyphs = raw.glyphIndexesForString("".join(caracteres))
                self.assertTrue(
                    all(g != 0 for g in glyphs),
                    f"icone de '{kind}' ({estilo['icon']!r}) nao existe na fonte {family}",
                )

    def test_botao_fechar_nao_depende_de_glyph(self):
        """O X de fechar e desenhado, entao nao usa texto (imune a fonte)."""
        self.manager.notify("Teste", "info")
        QApplication.processEvents()
        botoes = self.manager._items[0].findChildren(toast_mod.CloseButton)
        self.assertEqual(len(botoes), 1)
        self.assertEqual(botoes[0].text(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
