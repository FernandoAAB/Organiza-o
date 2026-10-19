import os
import sys
import tempfile
import unittest
from pathlib import Path

import main


@unittest.skipIf(sys.platform.startswith("linux") and not os.environ.get("DISPLAY"),
                 "Requer uma sessão gráfica para exercitar a interface")
class InterfaceTests(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        anterior = Path.cwd()
        os.chdir(pasta.name)
        self.addCleanup(os.chdir, anterior)
        Path("a1.txt").write_text("Pagamento -100,00D\nCrédito 200,00C\n", encoding="utf-8")
        Path("a2.txt").write_text("", encoding="utf-8")
        self.app = main.App()
        self.addCleanup(self.fechar_app)
        self.erros = []
        self.app.report_callback_exception = lambda *args: self.erros.append(args)
        self.app.update()

    def tearDown(self):
        self.app.update()
        self.assertFalse(self.erros)

    def fechar_app(self):
        for callback in self.app.tk.call("after", "info"):
            self.app.tk.call("after", "cancel", callback)
        self.app.destroy()

    def duplo_clique(self, x, y):
        for evento, tempo in (("<ButtonPress-1>", 1000), ("<ButtonRelease-1>", 1010),
                              ("<ButtonPress-1>", 1100), ("<ButtonRelease-1>", 1110)):
            self.app.tree_busca.event_generate(evento, x=x, y=y, time=tempo)
        self.app.update()

    def test_duplo_clique_vazio_ou_cabecalho_nao_adiciona_selecao_antiga(self):
        for y in (10, self.app.tree_busca.winfo_height() - 30):
            self.app.tree_busca.selection_set("0")
            self.app.update()
            self.duplo_clique(300, y)
            self.assertEqual(main.carregar_linhas("a2.txt"), [])

    def test_duplo_clique_em_registro_adiciona_a_linha_clicada(self):
        self.app.tree_busca.selection_set("0")
        self.app.update()
        _, y, _, altura = self.app.tree_busca.bbox("1", "texto")
        self.duplo_clique(300, y + altura // 2)
        self.assertEqual(main.carregar_linhas("a2.txt"), ["[2] Crédito 200,00C"])
        self.assertEqual(self.app.var_falta.get(), "1")

    def test_limpar_selecao_sincroniza_os_dois_paineis(self):
        self.app.tree_busca.selection_set("0")
        self.app.update()
        self.assertTrue(self.app.tree_deb.selection())
        self.app.tree_busca.selection_remove("0")
        self.app.update()
        self.assertFalse(self.app.tree_deb.selection())
        self.assertEqual(self.app.botao_adicionar.cget("state"), "disabled")
        self.app.tree_deb.selection_set("1")
        self.app.update()
        self.assertTrue(self.app.tree_busca.selection())
        self.app.tree_deb.selection_remove("1")
        self.app.update()
        self.assertFalse(self.app.tree_busca.selection())

    def test_barras_aparecem_so_quando_ha_conteudo_fora_da_tabela(self):
        tree = self.app.tree_busca
        barras = [w for w in tree.master.winfo_children() if isinstance(w, main.ctk.CTkScrollbar)]
        self.assertTrue(all(not w.winfo_ismapped() for w in barras))
        Path("a1.txt").write_text(("Registro muito longo " * 40 + "100,00D\n") * 50, encoding="utf-8")
        self.app.buscar_a1()
        self.app.update()
        self.assertTrue(all(w.winfo_ismapped() for w in barras))
        tree.xview_moveto(1)
        tree.yview_moveto(1)
        self.app.update()
        self.assertEqual(tree.xview()[1], 1)
        self.assertEqual(tree.yview()[1], 1)
        self.app.busca_var.set("sem resultado")
        self.app.buscar_a1()
        self.app.update()
        self.assertTrue(all(not w.winfo_ismapped() for w in barras))

    def test_redimensionamento_mantem_tabelas_alinhadas_e_controles_visiveis(self):
        def conferir(widget):
            for filho in widget.winfo_children():
                if not filho.winfo_ismapped():
                    continue
                if isinstance(filho, (main.ctk.CTkButton, main.ctk.CTkEntry, main.ctk.CTkOptionMenu)):
                    self.assertGreater(filho.winfo_width(), 1)
                    self.assertGreaterEqual(filho.winfo_x(), 0)
                    self.assertLessEqual(filho.winfo_x() + filho.winfo_width(), widget.winfo_width())
                conferir(filho)

        for modo in ("Claro", "Escuro"):
            self.app.mudar_tema(modo)
            for tamanho in ("960x560", "1100x650", "1360x820"):
                self.app.geometry(tamanho)
                self.app.update()
                self.assertEqual(self.app.tree_busca.winfo_rooty(), self.app.tree_deb.winfo_rooty())
                self.assertGreater(self.app.tree_busca.winfo_height(), 100)
                conferir(self.app)
                self.app.alternar_aparencia()
                self.app.update()
                self.app.abas.set("Lista A2")
                self.app.update()
                conferir(self.app)
                self.app.abas.set("Buscar e comparar")
                self.app.update()
                conferir(self.app)
                self.app.alternar_aparencia()
                self.app.update()

    def test_status_longo_quebra_linha_sem_alargar_a_janela(self):
        self.app.geometry("960x560")
        self.app.update()
        altura = self.app.label_status.winfo_height()
        largura = self.app.winfo_width()
        self.app.status.set("Mensagem de operação com um caminho longo " * 8)
        self.app.update()
        self.assertGreater(self.app.label_status.winfo_height(), altura)
        self.assertEqual(self.app.winfo_width(), largura)


if __name__ == "__main__":
    unittest.main()
