import os
import sys
import tempfile
import unittest
from unittest.mock import patch
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
        barras = {w.cget("orientation"): w for w in tree.master.winfo_children()
                  if isinstance(w, main.ctk.CTkScrollbar)}

        def conferir(horizontal, vertical):
            for orientacao, esperado in (("horizontal", horizontal), ("vertical", vertical)):
                self.assertEqual(bool(barras[orientacao].winfo_ismapped()), esperado,
                                 f"Barra {orientacao}: janela={self.app.geometry()}, "
                                 f"grade={tree.winfo_width()}x{tree.winfo_height()}, "
                                 f"xview={tree.xview()}, yview={tree.yview()}")

        # A largura inicial depende do monitor, da fonte e do DPI do Windows.
        # Dois textos curtos e o painel ampliado garantem conteúdo que cabe.
        Path("a1.txt").write_text("A\nB\n", encoding="utf-8")
        self.app.buscar_a1()
        self.app.update()
        self.app.divisao.sash_place(0, self.app.divisao.winfo_width(), 0)
        self.app.update()
        conferir(horizontal=False, vertical=False)

        # Mesmo com apenas duas linhas, estreitar o painel exige rolagem horizontal.
        self.app.divisao.sash_place(0, 0, 0)
        self.app.update()
        conferir(horizontal=True, vertical=False)
        self.app.divisao.sash_place(0, self.app.divisao.winfo_width(), 0)
        self.app.update()
        conferir(horizontal=False, vertical=False)

        Path("a1.txt").write_text(("Registro muito longo " * 40 + "100,00D\n") * 50, encoding="utf-8")
        self.app.buscar_a1()
        self.app.update()
        conferir(horizontal=True, vertical=True)
        tree.xview_moveto(1)
        tree.yview_moveto(1)
        self.app.update()
        self.assertEqual(tree.xview()[1], 1)
        self.assertEqual(tree.yview()[1], 1)
        self.app.busca_var.set("sem resultado")
        self.app.buscar_a1()
        self.app.update()
        conferir(horizontal=False, vertical=False)

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

        try:
            for escala in (1, 1.25):
                main.ctk.set_widget_scaling(escala)
                main.ctk.set_window_scaling(escala)
                # CustomTkinter libera min/max um segundo após trocar a escala.
                self.app.after(1100, self.app.quit)
                self.app.mainloop()
                for modo in ("Claro", "Escuro"):
                    self.app.mudar_tema(modo)
                    alturas = []
                    for largura, altura in ((960, 560), (1366, 768), (1600, 900), (1920, 1080)):
                        with self.subTest(escala=escala, modo=modo, resolucao=(largura, altura)):
                            # As medidas do briefing são físicas; geometry usa unidades lógicas.
                            self.app.geometry(f"{round(largura / escala)}x{round(altura / escala)}")
                            self.app.update()
                            self.assertEqual(self.app.tree_busca.winfo_rooty(), self.app.tree_deb.winfo_rooty())
                            alturas.append(self.app.tree_busca.winfo_height())
                            self.assertGreater(alturas[-1], 100)
                            self.assertLessEqual(self.app.rodape_global.winfo_height(), round(28 * escala))
                            self.assertLessEqual(self.app.rodape_global.winfo_rooty() -
                                                 (self.app.abas.winfo_rooty() + self.app.abas.winfo_height()), 2)
                            conferir(self.app)
                            self.app.alternar_aparencia()
                            self.app.update()
                            conferir(self.app)
                            self.app.trocar_aba("Lista A2")
                            self.app.update()
                            self.assertTrue(self.app.tree_a2.winfo_ismapped())
                            self.assertFalse(self.app.tree_busca.winfo_ismapped())
                            self.assertEqual(self.app.aba_selecionada.get(), "Lista A2")
                            conferir(self.app)
                            self.app.trocar_aba("Buscar e comparar")
                            self.app.update()
                            self.assertTrue(self.app.tree_busca.winfo_ismapped())
                            self.assertEqual(self.app.aba_selecionada.get(), "Buscar e comparar")
                            conferir(self.app)
                            self.app.alternar_aparencia()
                            self.app.update()
                    self.assertEqual(alturas, sorted(set(alturas)))
        finally:
            main.ctk.set_widget_scaling(1)
            main.ctk.set_window_scaling(1)

    def test_indicadores_acompanham_inclusao_pesquisa_e_filtro(self):
        def conferir(origem, ok, falta):
            self.assertEqual(self.app.indicador_origem.get(), str(origem))
            self.assertEqual(self.app.indicador_ok.get(), str(ok))
            self.assertEqual(self.app.indicador_falta.get(), str(falta))

        conferir(2, 0, 2)
        self.app.tree_busca.selection_set("0")
        self.app.update()
        self.app.adicionar_e_comparar()
        conferir(2, 1, 1)
        self.app.tipo_comparacao.set("Créditos")
        conferir(2, 0, 1)
        self.app.busca_var.set("Crédito")
        self.app.buscar_a1()
        conferir(1, 0, 1)
        self.app.mudar_tema("Claro")
        conferir(1, 0, 1)
        self.app.busca_var.set("inexistente")
        self.app.buscar_a1()
        conferir(0, 0, 0)
        self.app.mostrar_todos()
        self.app.tipo_comparacao.set("Todos")
        conferir(2, 1, 1)

    def test_teclado_seleciona_registro_e_confirma_pesquisa_com_enter(self):
        tree = self.app.tree_busca
        tree.focus_force()
        tree.focus("0")
        tree.selection_set("0")
        tree.event_generate("<Down>")
        self.app.update()
        self.assertEqual(tree.selection(), ("1",))
        self.assertEqual(self.app.botao_adicionar.cget("state"), "normal")
        entrada = self.app.entrada_busca._entry
        entrada.focus_force()
        self.app.busca_var.set("Crédito")
        entrada.event_generate("<Return>")
        self.app.update()
        self.assertEqual(self.app.focus_get(), entrada)
        self.assertEqual(self.app.termo_busca, "Crédito")
        self.assertEqual(len(tree.get_children()), 1)
        self.assertEqual(self.app.var_total.get(), "1")

    def test_status_longo_preserva_mensagem_em_rodape_de_uma_linha(self):
        self.app.geometry("960x560")
        self.app.update()
        altura = self.app.label_status.winfo_height()
        largura = self.app.winfo_width()
        mensagem = "Mensagem de operação com um caminho longo " * 8
        self.app.status.set(mensagem)
        self.app.update()
        self.assertEqual(self.app.label_status.winfo_height(), altura)
        self.assertLessEqual(self.app.rodape_global.winfo_height(), 28)
        self.assertEqual(self.app.status.get(), mensagem)
        self.assertTrue(self.app.status_visivel.get().endswith("…"))
        with patch("main.messagebox.showinfo") as detalhes:
            self.app.label_status._label.event_generate("<Button-1>")
            detalhes.assert_called_once_with("Status", mensagem, parent=self.app)
        self.assertEqual(self.app.winfo_width(), largura)


if __name__ == "__main__":
    unittest.main()
