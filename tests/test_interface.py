# Testes dos controles e interações da interface usando dados temporários; exigem sessão gráfica.
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
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

    def duplo_clique_conferencia(self, item="0", y=None):
        tree = self.app.tree_deb
        if y is None:
            _, topo, _, altura = tree.bbox(item, "situacao")
            y = topo + altura // 2
        tempo = getattr(self, "_tempo_atencao", 3000)
        self._tempo_atencao = tempo + 1000
        for evento, instante in (("<ButtonPress-1>", tempo), ("<ButtonRelease-1>", tempo + 10),
                                 ("<ButtonPress-1>", tempo + 100), ("<ButtonRelease-1>", tempo + 110)):
            tree.event_generate(evento, x=180, y=y, time=instante)
        self.app.update()

    def test_atencao_duplo_clique_salva_reabre_e_remove_sem_alterar_a1_a2(self):
        antes = [Path(nome).read_bytes() for nome in ("a1.txt", "a2.txt")]
        self.duplo_clique_conferencia("1")
        self.assertIn("atencao", self.app.tree_deb.item("1", "tags"))
        self.assertNotIn("atencao", self.app.tree_deb.item("0", "tags"))
        self.assertEqual(self.app.indicador_atencao.get(), "1")
        self.assertEqual(self.app.tree_deb.set("1", "situacao"), "FALTA NO A2")
        self.assertTrue(Path("No/atencao.json").is_file())
        self.fechar_app()
        self.app = main.App()
        self.app.report_callback_exception = lambda *args: self.erros.append(args)
        self.app.update()
        self.assertIn("atencao", self.app.tree_deb.item("1", "tags"))
        self.assertEqual(self.app.indicador_atencao.get(), "1")
        self.duplo_clique_conferencia("1")
        self.assertNotIn("atencao", self.app.tree_deb.item("1", "tags"))
        self.assertEqual(main.carregar_atencoes(), set())
        self.assertEqual([Path(nome).read_bytes() for nome in ("a1.txt", "a2.txt")], antes)

    def test_atencao_acompanha_filtros_e_temas_mas_nao_muda_conferencia(self):
        antes = main.calcular_lancamentos()
        self.duplo_clique_conferencia("1")
        for modo in ("Claro", "Escuro"):
            self.app.mudar_tema(modo)
            self.app.busca_var.set("Crédito")
            self.app.buscar_a1()
            self.assertIn("atencao", self.app.tree_deb.item("0", "tags"))
            self.assertEqual(self.app.indicador_atencao.get(), "1")
            self.assertEqual(str(self.app.tree_deb.tag_configure("atencao", "foreground")),
                             main.cm("atencao", modo))
            self.app.tipo_comparacao.set("Débitos")
            self.assertEqual(self.app.indicador_atencao.get(), "0")
            self.app.mostrar_todos()
            self.app.tipo_comparacao.set("Todos")
            self.assertEqual(self.app.indicador_atencao.get(), "1")
        self.assertEqual(main.calcular_lancamentos(), antes)

    def test_atencao_nao_transfere_marcacao_a_texto_alterado(self):
        self.duplo_clique_conferencia("0")
        Path("a1.txt").write_text("Outro pagamento 999,99D\n", encoding="utf-8")
        self.app.atualizar_tudo()
        self.assertNotIn("atencao", self.app.tree_deb.item("0", "tags"))
        self.assertEqual(self.app.indicador_atencao.get(), "0")

    def test_atencao_rejeita_linha_desatualizada(self):
        Path("a1.txt").write_text("Outro pagamento 999,99D\n", encoding="utf-8")
        self.duplo_clique_conferencia("0")
        self.assertFalse(Path("No/atencao.json").exists())
        self.assertIn("A1 foi alterado", self.app.status.get())

    def test_atencao_cabecalho_e_vazio_nao_marcam_selecao_anterior(self):
        self.app.tree_deb.selection_set("0")
        for y in (5, self.app.tree_deb.winfo_height() - 5):
            self.duplo_clique_conferencia(y=y)
        self.assertFalse(Path("No/atencao.json").exists())
        self.assertEqual(self.app.indicador_atencao.get(), "0")

    def test_atencao_falha_de_gravacao_preserva_marcacoes_anteriores(self):
        self.duplo_clique_conferencia("1")
        antes = Path("No/atencao.json").read_bytes()
        with patch.object(main, "salvar_atencoes", side_effect=PermissionError("Sem acesso")), \
                patch.object(main.messagebox, "showerror") as mensagem:
            self.duplo_clique_conferencia("0")
        mensagem.assert_called_once()
        self.assertEqual(Path("No/atencao.json").read_bytes(), antes)
        self.assertNotIn("atencao", self.app.tree_deb.item("0", "tags"))
        self.assertIn("atencao", self.app.tree_deb.item("1", "tags"))
        self.assertEqual(self.app.indicador_atencao.get(), "1")

    def test_atencao_arquivo_invalido_nao_e_sobrescrito(self):
        Path("No").mkdir(exist_ok=True)
        Path("No/atencao.json").write_text("arquivo incompleto", encoding="utf-8")
        with patch.object(main.messagebox, "showerror") as mensagem:
            self.duplo_clique_conferencia("0")
        mensagem.assert_called_once()
        self.assertEqual(Path("No/atencao.json").read_text(), "arquivo incompleto")
        self.assertEqual(self.app.indicador_atencao.get(), "0")
        self.assertNotIn("atencao", self.app.tree_deb.item("0", "tags"))

    def test_servidor_de_captura_pode_iniciar_parar_e_iniciar_novamente(self):
        self.app.iniciar_servidor_captura()
        self.app.update()
        self.assertIsNotNone(self.app.servidor_captura)
        self.assertIsNotNone(self.app.qr_imagem)
        self.app.parar_servidor_captura()
        self.app.update()
        self.assertIsNone(self.app.servidor_captura)
        self.app.iniciar_servidor_captura()
        self.app.update()
        self.assertIsNotNone(self.app.servidor_captura)
        self.assertIsNotNone(self.app.qr_imagem)

    def test_captura_valida_automaticamente_os_dados_do_ocr(self):
        Path("a1.txt").write_text(
            "03/11/2026 Mercado Teste 123,45D\n", encoding="utf-8")
        self.app.atualizar_tudo()
        with patch.object(main, "executar_ocr", return_value=(
                    "Mercado Teste\n03/11/2026\nTotal a pagar R$ 123,45\n",
                    "")):
            self.app.receber_captura(b"imagem ficticia", ".png")
            self.aguardar_ocr()
            self.app.update_idletasks()
            self.app.update()
        self.assertEqual(main.carregar_linhas("a2.txt"),
                         ["[1] 03/11/2026 Mercado Teste 123,45D"])
        self.assertIsNone(self.app.captura_pendente)

    def test_captura_incerta_aguarda_confirmacao_manual(self):
        Path("a1.txt").write_text(
            "04/11/2026 Mercado 123,45D\n", encoding="utf-8")
        self.app.atualizar_tudo()
        with patch.object(main, "executar_ocr", return_value=(
                "Mercado\n04/11/2026\nTotal a pagar R$ 123,45", "Leitura incerta")):
            self.app.receber_captura(b"imagem ficticia", ".png")
            self.aguardar_ocr()
            self.app.update()
        self.assertEqual(main.carregar_linhas("a2.txt"), [])
        self.assertIsNotNone(self.app.captura_pendente)
        self.assertIn("Leitura incerta", self.app.captura_aviso.get())
        self.app.confirmar_captura()
        self.assertEqual(main.carregar_linhas("a2.txt"),
                         ["[1] 04/11/2026 Mercado 123,45D"])

    def test_captura_nao_adiciona_valor_parcial(self):
        Path("a1.txt").write_text("04/11/2026 Mercado 1.100,00D\n", encoding="utf-8")
        self.app.atualizar_tudo()
        with patch.object(main, "executar_ocr", return_value=(
                "Mercado\n04/11/2026\nTotal a pagar R$ 100,00", "")):
            self.app.receber_captura(b"imagem ficticia", ".png")
            self.aguardar_ocr()
            self.app.update()
        self.assertEqual(main.carregar_linhas("a2.txt"), [])
        self.assertIn("não encontrado", self.app.captura_aviso.get())

    def aguardar_ocr(self):
        limite = time.monotonic() + 4
        while self.app.captura_processando and time.monotonic() < limite:
            self.app.update()
            time.sleep(0.01)
        self.app.update()
        self.assertFalse(self.app.captura_processando)

    def test_tesseract_recebe_segunda_foto_sem_bloquear_a_janela(self):
        liberar = threading.Event()
        chamadas = []
        def leitura(*args):
            chamadas.append(threading.get_ident())
            liberar.wait(timeout=1)
            return "", "imagem sem campos"
        with patch.object(main, "executar_ocr_motor", side_effect=leitura):
            try:
                self.app.receber_captura(b"foto um", ".png")
                self.app.receber_captura(b"foto dois", ".png")
                self.assertTrue(self.app.captura_processando)
                self.assertEqual(len(self.app.capturas_fila), 1)
                eventos = []
                self.app.after_idle(lambda: eventos.append("responsiva"))
                self.app.update()
                self.assertEqual(eventos, ["responsiva"])
            finally:
                liberar.set()
                self.aguardar_ocr()
                self.aguardar_ocr()
        self.assertEqual(len(chamadas), 2)
        self.assertNotIn(threading.get_ident(), chamadas)

    def test_recebimento_pelo_servidor_nao_depende_da_interface(self):
        self.app.iniciar_servidor_captura()
        recebidos, erros = [], []
        def receber():
            try:
                self.app.servidor_captura.captura_callback(b"foto", ".png")
                recebidos.append(True)
            except Exception as erro:
                erros.append(erro)
        with patch.object(self.app, "after", side_effect=AssertionError("Rede acessou Tk")):
            thread = threading.Thread(target=receber, daemon=True)
            thread.start()
            thread.join(timeout=1)
        self.app.parar_servidor_captura()
        self.assertFalse(thread.is_alive())
        self.assertEqual(erros, [])
        self.assertEqual(recebidos, [True])
        self.assertEqual(self.app.entradas_captura.get_nowait(), (b"foto", ".png"))

    def test_upload_de_outra_foto_responde_enquanto_ocr_esta_ocupado(self):
        liberar = threading.Event()
        respostas, erros, leituras = [], [], []
        def leitura(caminho, motor):
            leituras.append(Path(caminho).read_bytes())
            liberar.wait(timeout=4)
            return "", "sem campos"
        self.app.iniciar_servidor_captura()
        endereco = f"http://127.0.0.1:{self.app.servidor_captura.server_port}"
        def enviar():
            corpo = (b'--foto\r\nContent-Disposition: form-data; name="documento"; '
                     b'filename="foto.png"\r\nContent-Type: image/png\r\n\r\nsegunda\r\n--foto--\r\n')
            requisicao = urllib.request.Request(endereco, data=corpo, headers={
                "Content-Type": "multipart/form-data; boundary=foto"})
            try:
                with urllib.request.urlopen(requisicao, timeout=2) as resposta:
                    respostas.append(resposta.status)
            except Exception as erro:
                erros.append(erro)
        with patch.object(main, "executar_ocr_motor", side_effect=leitura):
            try:
                self.app.receber_captura(b"primeira", ".png")
                thread = threading.Thread(target=enviar, daemon=True)
                thread.start()
                thread.join(timeout=1)
                self.assertFalse(thread.is_alive(), "O telefone ficou esperando o OCR.")
                self.assertEqual(erros, [])
                self.assertEqual(respostas, [200])
                # Consome os envios sem deixar a primeira leitura terminar.
                self.app.receber_fotos_enfileiradas()
                self.assertTrue(self.app.captura_processando)
                self.assertEqual(len(self.app.capturas_fila), 1)
            finally:
                liberar.set()
                self.aguardar_ocr()
                self.app.parar_servidor_captura()
        self.assertEqual(leituras, [b"primeira", b"segunda"])

    def test_fila_processa_tres_fotos_em_ordem_com_todos_os_motores(self):
        origem = [f"04/11/2026 Loja {n} {n}00,00D" for n in (1, 2, 3)]
        Path("a1.txt").write_text("\n".join(origem), encoding="utf-8")
        for motor in ("Tesseract", "PaddleOCR", "Comparar"):
            with self.subTest(motor=motor):
                Path("a2.txt").write_text("", encoding="utf-8")
                self.app.motor_ocr.set(motor)
                chamadas = []
                def leitura(caminho, escolhido):
                    n = Path(caminho).read_bytes().decode()
                    chamadas.append((n, escolhido))
                    return f"Loja {n}\n04/11/2026\nTotal a pagar {n}00,00D", ""
                with patch.object(main, "executar_ocr_motor", side_effect=leitura):
                    for n in (1, 2, 3):
                        self.app.receber_captura(str(n).encode(), ".png")
                    self.aguardar_ocr()
                self.assertEqual(chamadas, [(str(n), motor) for n in (1, 2, 3)])
                self.assertEqual(main.carregar_linhas("a2.txt"),
                                 [f"[{n}] {linha}" for n, linha in enumerate(origem, 1)])
                self.assertEqual(self.app.fila_captura.get(), "Fila: 0 foto(s)")

    def test_erro_inesperado_no_worker_nao_prende_proxima_foto(self):
        with patch.object(self.app, "ler_imagem_captura", side_effect=[
                RuntimeError("falha simulada"),
                ("Loja\n04/11/2026\nTotal a pagar 200,00D", "Revisar")]):
            self.app.receber_captura(b"um", ".png")
            self.app.receber_captura(b"dois", ".png")
            self.aguardar_ocr()
        self.assertIsNotNone(self.app.captura_pendente)
        self.assertEqual(self.app.captura_valor.get(), "200.00")
        self.assertEqual(self.app.capturas_fila, [])

    def test_descartar_nao_confirma_documento_e_libera_fila(self):
        self.app.apresentar_resultado_ocr("Loja\n04/11/2026\nTotal a pagar 100,00D", "")
        with patch.object(main, "executar_ocr_motor", return_value=(
                "Outra loja\n04/11/2026\nTotal a pagar 200,00D", "Leitura incerta")):
            self.app.receber_captura(b"outra", ".png")
            self.app.descartar_captura()
            self.app.update()
            self.aguardar_ocr()
        self.assertEqual(main.carregar_linhas("a2.txt"), [])
        self.assertEqual(self.app.captura_valor.get(), "200.00")
        self.assertIn("incerta", self.app.captura_aviso.get())
        self.app.receber_captura(b"mais uma", ".png")
        self.assertIn("incerta", self.app.captura_aviso.get())

    def test_paddle_processa_sem_bloquear_interface_e_preserva_fila(self):
        Path("a1.txt").write_text("04/11/2026 Mercado 123,45D\n", encoding="utf-8")
        self.app.atualizar_tudo()
        self.app.motor_ocr.set("PaddleOCR")
        liberar = threading.Event()
        def leitura(*args):
            liberar.wait(timeout=3)
            return "Mercado\n04/11/2026\nTotal a pagar R$ 123,45", "Leitura incerta"
        with patch.object(main, "executar_ocr_motor", side_effect=leitura):
            try:
                self.app.receber_captura(b"foto um", ".png")
                self.app.receber_captura(b"foto dois", ".png")
                eventos = []
                self.app.after_idle(lambda: eventos.append("janela responsiva"))
                self.app.update()
                self.assertEqual(eventos, ["janela responsiva"])
                self.assertTrue(self.app.captura_processando)
                self.assertEqual(len(self.app.capturas_fila), 1)
                liberar.set()
                limite = time.monotonic() + 3
                while self.app.captura_processando and time.monotonic() < limite:
                    self.app.update()
                    time.sleep(0.01)
                self.assertFalse(self.app.captura_processando)
                self.assertIsNotNone(self.app.captura_pendente)
                self.assertEqual(len(self.app.capturas_fila), 1)
                self.assertEqual(main.carregar_linhas("a2.txt"), [])
            finally:
                liberar.set()

    def test_captura_nao_encontrada_no_a1_e_encerrada_com_aviso(self):
        Path("a1.txt").write_text(
            "03/11/2026 Mercado Diferente 999,99D\n", encoding="utf-8")
        self.app.atualizar_tudo()
        with patch.object(main, "executar_ocr", return_value=(
                    "Mercado Teste\n03/11/2026\nTotal a pagar R$ 123,45\n",
                    "")):
            self.app.receber_captura(b"imagem ficticia", ".png")
            self.aguardar_ocr()
            self.app.update_idletasks()
            self.app.update()
        self.assertIsNone(self.app.captura_pendente)
        self.assertEqual(main.carregar_linhas("a2.txt"), [])
        self.assertIn("não encontrado no A1", self.app.captura_aviso.get())

    def test_captura_sem_campos_identificados_e_descartada(self):
        Path("a1.txt").write_text(
            "03/11/2026 Mercado Teste 123,45D\n", encoding="utf-8")
        self.app.atualizar_tudo()
        with patch.object(main, "executar_ocr", return_value=(
                    "imagem sem texto financeiro", "")):
            self.app.receber_captura(b"imagem ficticia", ".png")
            self.aguardar_ocr()
            self.app.update_idletasks()
            self.app.update()
        self.assertIsNone(self.app.captura_pendente)
        self.assertEqual(main.carregar_linhas("a2.txt"), [])
        self.assertIn("imagem", self.app.captura_aviso.get().lower())
        self.assertIn("descartado", self.app.captura_aviso.get().lower())

    def test_comparacao_mantem_ok_verde_e_captura_amarela(self):
        Path("a1.txt").write_text(
            "01/11/2026 Registro normal 100,00D\n"
            "02/11/2026 Registro da captura 200,00D\n", encoding="utf-8")
        Path("a2.txt").write_text(
            "[1] 01/11/2026 Registro normal 100,00D\n"
            "[2] 02/11/2026 Registro da captura 200,00D\n", encoding="utf-8")
        self.app.capturas_adicionadas = {2}
        self.app.atualizar_tudo()
        itens = self.app.tree_deb.get_children()
        self.assertEqual(self.app.tree_deb.item(itens[0], "tags")[0], "ok")
        self.assertEqual(self.app.tree_deb.item(itens[1], "tags")[0], "captura")

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

    def test_cabecalho_acomoda_fontes_largas_ao_redimensionar_e_reabrir_aparencia(self):
        # Reproduz a diferença de métricas das fontes dos runners Linux.
        self.app.navegacao.configure(font=(main.FONTE, 20, "bold"))
        for largura in (960, 1366, 960):
            with self.subTest(largura=largura):
                self.app.geometry(f"{largura}x768")
                self.app.update()
                for widget in (self.app.navegacao, self.app.botao_aparencia,
                               self.app.painel_aparencia):
                    self.assertTrue(widget.winfo_ismapped())
                    self.assertGreaterEqual(widget.winfo_x(), 0)
                    self.assertLessEqual(widget.winfo_x() + widget.winfo_width(),
                                         widget.master.winfo_width())
                    self.assertLessEqual(widget.winfo_y() + widget.winfo_height(),
                                         widget.master.winfo_height())
                self.app.alternar_aparencia()
                self.app.geometry("1200x768")
                self.app.update()
                self.assertFalse(self.app.painel_aparencia.winfo_ismapped())
                self.app.geometry(f"{largura}x768")
                self.app.update()
                self.app.alternar_aparencia()
                self.app.update()
                painel = self.app.painel_aparencia
                self.assertTrue(painel.winfo_ismapped())
                self.assertLessEqual(painel.winfo_x() + painel.winfo_width(),
                                     painel.master.winfo_width())
                self.assertLessEqual(self.app.botao_aparencia.winfo_x() +
                                     self.app.botao_aparencia.winfo_width(),
                                     self.app.cabecalho.winfo_width())

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
