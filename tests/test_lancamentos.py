# Testes das regras financeiras, referências de linha e captura, sem usar os dados pessoais do projeto.
import tempfile
import unittest
import threading
import urllib.request
import uuid
import socket
import http.client
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import main


class LancamentosComSinalTests(unittest.TestCase):
    def test_pagina_de_upload_continua_disponivel_apos_envio(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivos = []
            servidor = main._CaptureHTTPServer(("127.0.0.1", 0), main._UploadHandler)
            servidor.captura_callback = lambda conteudo, extensao: arquivos.append(
                (conteudo, extensao))
            thread = threading.Thread(target=servidor.serve_forever, daemon=True)
            thread.start()
            try:
                endereco = f"http://127.0.0.1:{servidor.server_port}"
                pagina = urllib.request.urlopen(endereco).read().decode()
                self.assertIn('multiple', pagina)
                self.assertIn('onchange="enfileirarFotos(this)"', pagina)
                self.assertNotIn('this.form.submit()', pagina)
                self.assertNotIn(">Enviar fotos para o computador<", pagina)
                limite = f"----teste{uuid.uuid4().hex}".encode()
                corpo = (
                    b"--" + limite + b"\r\n"
                    b'Content-Disposition: form-data; name="documento"; filename="foto.png"\r\n'
                    b"Content-Type: image/png\r\n\r\n"
                    b"imagem-ficticia\r\n--" + limite + b"--\r\n"
                )
                requisicao = urllib.request.Request(
                    endereco, data=corpo, method="POST",
                    headers={"Content-Type": f"multipart/form-data; boundary={limite.decode()}",
                             "Content-Length": str(len(corpo))})
                resposta = urllib.request.urlopen(requisicao).read().decode()
                self.assertIn("selecionar e enviar mais", resposta)
                self.assertEqual(len(arquivos), 1)
                self.assertIsInstance(arquivos[0][0], bytes)
                self.assertEqual(arquivos[0][1], ".png")
                self.assertEqual(list(Path(pasta).rglob("*")), [])
            finally:
                servidor.shutdown()
                servidor.server_close()
                thread.join(timeout=2)

    def test_servidor_pode_ser_reiniciado_na_mesma_porta(self):
        primeiro = main._CaptureHTTPServer(("127.0.0.1", 0), main._UploadHandler)
        porta = primeiro.server_port
        thread = threading.Thread(target=primeiro.serve_forever, daemon=True)
        thread.start()
        try:
            primeiro.shutdown()
            primeiro.server_close()
            thread.join(timeout=2)
            segundo = main._CaptureHTTPServer(("127.0.0.1", porta), main._UploadHandler)
            segundo.server_close()
        finally:
            if primeiro.fileno() != -1:
                primeiro.server_close()

    def test_interpreta_campos_financeiros_de_texto_ocr(self):
        campos = main.interpretar_texto_documento(
            "Mercado Central\nData 03/11/2026\nTotal a pagar R$ 1.234,56"
        )
        self.assertEqual(campos, {
            "descricao": "Mercado Central",
            "data": "03/11/2026",
            "valor": "1234.56",
            "tipo": "D",
        })

    def test_interpretacao_prioriza_total_em_vez_do_ultimo_valor(self):
        campos = main.interpretar_texto_documento(
            "Padaria Central\n03.11.2026\nSubtotal R$ 10,00\n"
            "Total a pagar R$ 12,50\nTroco R$ 2,50\nPagamento débito"
        )
        self.assertEqual(campos["data"], "03/11/2026")
        self.assertEqual(campos["valor"], "12.50")
        self.assertEqual(campos["tipo"], "D")

    def test_interpretacao_nao_inventa_campos_ausentes(self):
        self.assertEqual(main.interpretar_texto_documento("Recibo sem valor"), {
            "descricao": "Recibo sem valor", "data": "", "valor": "", "tipo": ""
        })

    def test_valor_pago_prioritario_independe_da_ordem_e_dos_acrescimos(self):
        for rotulo in ("Valor pago", "Total pago", "Pago", "Valor efetivamente pago"):
            for separador in (": R$ ", "\nR$ "):
                texto = (f"Vencimento: 20/11/2026\n{rotulo}{separador}105,00\n"
                         "Valor total: 100,00\nJuros/Multa: 5,00\nDesconto: 0,00\nPagamento débito")
                with self.subTest(rotulo=rotulo, separador=separador):
                    campos = main.interpretar_texto_documento(texto)
                    self.assertEqual(campos["valor"], "105.00")
                    self.assertEqual(campos["data"], "20/11/2026")

    def test_pago_em_e_situacao_pago_nao_sao_rotulos_de_valor_pago(self):
        texto = ("Vencimento: 20/11/2026 Pago em 19/11/2026\n"
                 "Valor do documento: 100,00 Juros: 5,00\nSituação: Pago\n")
        campos = main.interpretar_texto_documento(texto)
        self.assertEqual(campos["data"], "20/11/2026")
        self.assertEqual(campos["valor"], "100.00")
        self.assertEqual(main.identificar_vencimento("Pago em 19/11/2026")[0], "")

    def test_valores_pagos_conflitantes_exigem_revisao(self):
        valor, aviso = main.identificar_valor_documento("Valor pago: 100,00\nTotal pago: 110,00")
        self.assertEqual(valor, "")
        self.assertIn("valor pago", aviso)

    def test_situacao_pago_sozinha_nao_inventa_valor_nem_tipo(self):
        campos = main.interpretar_texto_documento("Situação: Pago\nJuros: 5,00")
        self.assertEqual(campos["valor"], "")
        self.assertEqual(campos["tipo"], "")

    def test_vencimento_tem_prioridade_sobre_emissao_e_pagamento(self):
        exemplos = (
            "Emissão: 01/11/2026\nVencimento: 20/11/2026\nPagamento: 18/11/2026",
            "Emissão 01/11/2026 Venc. 20.11.2026 Pagamento 18/11/2026",
            "Data de emissão: 01/11/2026\nVcto:\n20-11-2026\nPagamento: 18/11/2026",
        )
        for texto in exemplos:
            with self.subTest(texto=texto):
                campos = main.interpretar_texto_documento(texto + "\nTotal a pagar 150,00")
                self.assertEqual(campos["data"], "20/11/2026")
                self.assertEqual(campos["valor"], "150.00")
                self.assertEqual(campos["tipo"], "D")

    def test_datas_ambiguas_ou_vencimento_invalido_nao_usam_a_primeira_data(self):
        for texto in (
            "01/11/2026\n20/11/2026",
            "Emissão: 01/11/2026\nVencimento: 31/11/2026",
            "Vencimento: 10/11/2026\nVencimento: 20/11/2026",
            "Vencimento:\nPagamento: 01/11/2026",
            "Emissão: 01/11/2026",
        ):
            with self.subTest(texto=texto):
                data, aviso = main.identificar_vencimento(texto)
                self.assertEqual(data, "")
                self.assertIn("vencimento", aviso.lower())

    def test_data_unica_sem_rotulo_continua_disponivel(self):
        self.assertEqual(main.identificar_vencimento("Recibo\n20/11/2026\n150,00"),
                         ("20/11/2026", ""))

    def test_documento_encontra_unica_linha_ainda_nao_conferida(self):
        origem = [(4, "03/11/2026 Mercado 123,45D")]
        self.assertEqual(
            main.correspondencias_documento(
                "Mercado\n03/11/2026\nTotal a pagar R$ 123,45\nDébito",
                origem, []),
            origem,
        )

    def test_documento_nao_escolhe_duplicidade(self):
        origem = [
            (1, "03/11/2026 Mercado A 123,45D"),
            (2, "03/11/2026 Mercado B 123,45D"),
        ]
        self.assertEqual(
            main.correspondencias_documento(
                "03/11/2026\nTotal a pagar R$ 123,45\nDébito",
                origem, []),
            origem,
        )

    def test_documento_aplica_busca_tolerante_a_separadores(self):
        origem = [(4, "03/11/2026 Mercado 1.234,56D")]
        self.assertEqual(
            main.correspondencias_campos(
                "03.11.2026", "1.234,56", "D", origem, []),
            origem,
        )

    def test_captura_exige_valor_exato_sem_buscar_parte_do_numero(self):
        for registro in ('04/11/2026 Mercado 1.100,00D',
                         '04/11/2026 Documento 10000 Mercado 99,99D'):
            self.assertEqual(main.correspondencias_campos(
                '04/11/2026', '100.00', 'D', [(1, registro)], []), [])

    def test_captura_aceita_valores_brasileiros_e_decimais_equivalentes(self):
        origem = [(1, '04/11/2026 Mercado 1.234,50D')]
        for valor in ('1234.50', '1.234,50', '1234,5'):
            self.assertEqual(main.correspondencias_campos(
                '04/11/2026', valor, 'D', origem, []), origem)
        for valor in ('NaN', 'Infinity', 'cem', '1.2.3', ''):
            self.assertEqual(main.correspondencias_campos(
                '04/11/2026', valor, 'D', origem, []), [])

    def test_valores_com_e_sem_sinal(self):
        for texto, tipo, valor in (
            ("Pagamento -700,00D", "D", "700.00"),
            ("Pagamento -12.535,39D", "D", "12535.39"),
            ("Recebimento +1.200,50C", "C", "1200.50"),
            ("ENVIO TED320,00 D", "D", "320.00"),
        ):
            with self.subTest(texto=texto):
                self.assertEqual(main.extrair_lancamento(texto), (tipo, Decimal(valor)))

    def test_nao_aceita_sinais_ou_separadores_invalidos(self):
        for texto in ("--700,00D", "+-700,00D", "1.23,45D", "-700,000D"):
            with self.subTest(texto=texto):
                self.assertIsNone(main.extrair_lancamento(texto))

    def test_selecao_negativa_confere_apenas_a_linha_escolhida(self):
        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "a1.txt"
            destino = Path(pasta) / "a2.txt"
            origem.write_text("Pagamento -700,00D\nPagamento -700,00D\nCrédito 700,00C\n", encoding="utf-8")
            destino.write_text("[2] Pagamento -700,00D\n", encoding="utf-8")
            with patch.object(main, "ARQUIVO_ORIGEM", str(origem)), \
                    patch.object(main, "ARQUIVO_DESTINO", str(destino)):
                resultado, total, faltando = main.calcular_lancamentos()
                self.assertEqual((total, faltando), (3, 2))
                self.assertEqual([(n, ok) for n, _, ok in resultado],
                                 [(1, True), (2, False), (3, False)])


class ComparacaoTests(unittest.TestCase):
    def comparar(self, origem, destino, tipo=None, termo=""):
        with tempfile.TemporaryDirectory() as pasta:
            a1 = Path(pasta) / "a1.txt"
            a2 = Path(pasta) / "a2.txt"
            a1.write_text(origem, encoding="utf-8")
            a2.write_text(destino, encoding="utf-8")
            with patch.object(main, "ARQUIVO_ORIGEM", str(a1)), \
                    patch.object(main, "ARQUIVO_DESTINO", str(a2)):
                return main.calcular_lancamentos(tipo, termo)

    def test_espacos_diferentes_preservam_a_linha_selecionada(self):
        resultado, total, faltando = self.comparar(
            "01/10/2026 1001 Pagamento -700,00D\n02/10/2026 1002 Pagamento -700,00D\n",
            "[2] 02/10/2026\t1002    Pagamento -700,00D\n")
        self.assertEqual([(n, ok) for n, _, ok in resultado], [(1, False), (2, True)])
        self.assertEqual((total, faltando), (2, 1))

    def test_referencia_existente_confere_mesmo_com_texto_antigo(self):
        resultado, _, faltando = self.comparar(
            "Pagamento A -700,00D\nPagamento B -700,00D\n",
            "[2] Pagamento antigo -700,00D\n")
        self.assertEqual([ok for _, _, ok in resultado], [False, False])
        self.assertEqual(faltando, 2)

    def test_referencia_inexistente_confere_se_a_linha_for_igual(self):
        resultado, _, _ = self.comparar("Pagamento -700,00D\n", "[99] Pagamento -700,00D\n")
        self.assertTrue(resultado[0][2])

    def test_referencia_duplicada_confere_uma_unica_linha(self):
        resultado, _, _ = self.comparar(
            "Pagamento -700,00D\nPagamento -700,00D\n",
            "[2] Pagamento -700,00D\n[2] Pagamento -700,00D\n")
        self.assertEqual([ok for _, _, ok in resultado], [True, True])

    def test_itens_sem_referencia_consumem_ocorrencias_do_mesmo_tipo(self):
        resultado, total, faltando = self.comparar(
            "Débito A -700,00D\nDébito B -700,00D\nCrédito 700,00C\n",
            "Pagamento 700,00D\n")
        self.assertEqual([ok for _, _, ok in resultado], [False, False, False])
        self.assertEqual((total, faltando), (3, 3))

    def test_selecao_referenciada_tem_prioridade_sobre_comparacao_por_valor(self):
        resultado, _, faltando = self.comparar(
            "Débito A -700,00D\nDébito B -700,00D\nDébito C -700,00D\n",
            "Pagamento 700,00D\n[1] Débito A -700,00D\n")
        self.assertEqual([ok for _, _, ok in resultado], [True, False, False])
        self.assertEqual(faltando, 2)

    def test_pesquisa_e_filtro_nao_redistribuem_ocorrencias(self):
        origem = "01/10/2026 Débito -700,00D\n02/10/2026 Débito -700,00D\nCrédito 700,00C\n"
        destino = "Pagamento 700,00D\n"
        resultado, total, faltando = self.comparar(origem, destino, "D", "02/10/2026")
        self.assertEqual([(n, ok) for n, _, ok in resultado], [(2, False)])
        self.assertEqual((total, faltando), (1, 1))
        resultado, _, _ = self.comparar(origem, destino, "C")
        self.assertEqual([(n, ok) for n, _, ok in resultado], [(3, False)])

    def test_extrato_ignora_saldos_e_resumo_mantendo_futuros_e_linhas_originais(self):
        origem = ("LANÇAMENTOS\n"
                  "30/09/2026 SALDO ANTERIOR 1.000,00C\n"
                  "01/10/2026 SALDO DO DIA 900,00C\n"
                  "01/10/2026 1001 Pagamento -100,00D\n"
                  "01/10/2026 1002 Suprimento de saldo 200,00C\n"
                  "LANÇAMENTOS FUTUROS\n"
                  "30/11/2026 1003 Pagamento futuro -700,00D\n"
                  "RESUMO\n"
                  "(+) SALDO EM CONTA: 900,00C\n"
                  "JUROS: 0,00D\n")
        resultado, total, faltando = self.comparar(origem, "[7] 30/11/2026 1003 Pagamento futuro -700,00D\n")
        self.assertEqual([(n, ok) for n, _, ok in resultado], [(4, False), (5, False), (7, True)])
        self.assertEqual((total, faltando), (3, 2))

    def test_saldo_diario_nao_consume_credito_de_mesmo_valor(self):
        resultado, _, _ = self.comparar(
            "01/10/2026 SALDO DO DIA 700,00C\n01/10/2026 1001 Crédito 700,00C\n",
            "Recebimento 700,00C\n")
        self.assertEqual([(n, ok) for n, _, ok in resultado], [(2, False)])


if __name__ == "__main__":
    unittest.main()


class UploadInterrompidoTests(unittest.TestCase):
    def criar(self, corpo=None):
        corpo = corpo or (b'--teste\r\nContent-Disposition: form-data; name="documento"; '
                          b'filename="foto.png"\r\n\r\nimagem\r\n--teste--\r\n')
        handler = object.__new__(main._UploadHandler)
        handler.path = '/'
        handler.headers = {"Content-Length": str(len(corpo)),
                           "Content-Type": "multipart/form-data; boundary=teste"}
        handler.rfile = Mock()
        handler.rfile.read.return_value = corpo
        handler.wfile = Mock()
        handler.server = Mock(spec=['captura_callback'])
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.send_error = Mock()
        return handler

    def executar(self, handler, metodo='do_POST'):
        with patch.object(main.BaseHTTPRequestHandler, 'handle', side_effect=getattr(handler, metodo)):
            handler.handle()

    def test_reset_durante_upload_nao_escapa_nem_adiciona_foto(self):
        handler = self.criar()
        handler.rfile.read.side_effect = ConnectionResetError(10054, 'conexao interrompida')
        self.executar(handler)
        handler.server.captura_callback.assert_not_called()

    def test_corpo_truncado_nao_e_aceito_como_foto_completa(self):
        handler = self.criar()
        handler.headers['Content-Length'] = str(int(handler.headers['Content-Length']) + 20)
        self.executar(handler)
        handler.send_error.assert_called_once()
        self.assertEqual(handler.send_error.call_args.args[0], 400)
        handler.server.captura_callback.assert_not_called()

    def test_multipart_sem_fechamento_nao_entra_na_fila(self):
        handler = self.criar(b'--teste\r\nContent-Disposition: form-data; name="documento"; '
                             b'filename="foto.png"\r\n\r\nimagem')
        self.executar(handler)
        handler.send_error.assert_called_once()
        handler.server.captura_callback.assert_not_called()

    def test_queda_apos_gravacao_nao_repete_nem_remove_foto(self):
        handler = self.criar()
        handler.wfile.write.side_effect = BrokenPipeError('cliente saiu')
        self.executar(handler)
        handler.server.captura_callback.assert_called_once_with(b'imagem', '.png')

    def test_falha_interna_continua_visivel(self):
        handler = self.criar()
        handler.rfile.read.side_effect = RuntimeError('erro interno')
        with self.assertRaisesRegex(RuntimeError, 'erro interno'):
            self.executar(handler)

    def test_servidor_recebe_nova_foto_apos_envio_interrompido(self):
        fotos = []
        servidor = main._CaptureHTTPServer(("127.0.0.1", 0), main._UploadHandler)
        servidor.captura_callback = lambda dados, extensao: fotos.append((dados, extensao))
        thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        with patch.object(servidor, 'handle_error') as erro_servidor:
            with socket.create_connection(servidor.server_address, timeout=3) as conexao:
                conexao.sendall(b'POST / HTTP/1.0\r\nContent-Length: 1000\r\n'
                               b'Content-Type: multipart/form-data; boundary=teste\r\n\r\nparcial')
                conexao.shutdown(socket.SHUT_WR)
                self.assertIn(b'400', conexao.recv(4096))
            cliente = http.client.HTTPConnection(*servidor.server_address, timeout=3)
            try:
                corpo = (b'--teste\r\nContent-Disposition: form-data; name="documento"; '
                         b'filename="foto.png"\r\n\r\nimagem\r\n--teste--\r\n')
                cliente.request('POST', '/', body=corpo,
                                headers={'Content-Type': 'multipart/form-data; boundary=teste'})
                resposta = cliente.getresponse()
                self.assertEqual(resposta.status, 200)
                resposta.read()
            finally:
                cliente.close()
            self.assertEqual(fotos, [(b'imagem', '.png')])
            erro_servidor.assert_not_called()

    def test_limite_de_15mb_por_foto_considera_cabecalho_multipart(self):
        for acrescimo in (0, 1):
            with self.subTest(acrescimo=acrescimo):
                conteudo = b'X' * (15 * 1024 * 1024 + acrescimo)
                corpo = (b'--teste\r\nContent-Disposition: form-data; name="documento"; '
                         b'filename="foto.png"\r\n\r\n' + conteudo + b'\r\n--teste--\r\n')
                handler = self.criar(corpo)
                self.executar(handler)
                if acrescimo:
                    self.assertEqual(handler.send_error.call_args.args[0], 413)
                    handler.server.captura_callback.assert_not_called()
                else:
                    handler.send_error.assert_not_called()
                    handler.server.captura_callback.assert_called_once_with(conteudo, '.png')


class PainelFolhasHTTPTests(unittest.TestCase):
    def setUp(self):
        from fila_ocr import FilaOCR
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.fila = FilaOCR(pasta.name)
        self.addCleanup(self.fila.fechar)
        self.servidor = main._CaptureHTTPServer(('127.0.0.1', 0), main._UploadHandler)
        self.servidor.fila_ocr = self.fila
        self.servidor.captura_lote_callback = self.fila.adicionar_lote
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)

    def requisitar(self, metodo, caminho, corpo=None, headers=None):
        cliente = http.client.HTTPConnection(*self.servidor.server_address, timeout=5)
        try:
            cliente.request(metodo, caminho, body=corpo, headers=headers or {})
            resposta = cliente.getresponse()
            return resposta.status, dict(resposta.getheaders()), resposta.read()
        finally:
            cliente.close()

    def test_identifica_folha_recebida_previa_e_finalizacao(self):
        import io, json
        from PIL import Image
        dados = io.BytesIO()
        Image.new('RGB', (50, 100), 'white').save(dados, format='PNG')
        corpo = (b'--teste\r\nContent-Disposition: form-data; name="documento"; filename="foto.png"\r\n\r\n'
                 + dados.getvalue() + b'\r\n--teste--\r\n')
        status, _, resposta = self.requisitar('POST', '/', corpo, {
            'Content-Type': 'multipart/form-data; boundary=teste', 'Accept': 'application/json'})
        self.assertEqual(status, 200)
        identificador = json.loads(resposta)['folhas'][0]
        status, headers, painel = self.requisitar('GET', '/fila')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        folha = json.loads(painel)['folhas'][0]
        self.assertEqual(folha['id'], identificador)
        self.assertNotIn('imagem', folha)  # A API não expõe caminhos do computador.
        status, headers, previa = self.requisitar('GET', folha['previa'])
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'image/jpeg')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertTrue(previa.startswith(b'\xff\xd8'))
        self.fila.finalizar(identificador, 'concluida')
        self.assertEqual(self.requisitar('GET', folha['previa'])[0], 410)
        painel = json.loads(self.requisitar('GET', '/fila')[2])
        self.assertEqual(painel['recentes'][0]['id'], identificador)
        self.assertIsNone(painel['recentes'][0]['previa'])

    def test_nao_serve_caminhos_arbitrarios_e_valida_pagina(self):
        for caminho, esperado in (('/fila/../fila.sqlite3', 404),
                                  ('/fila/0/previa', 404),
                                  ('/fila/999999/previa', 410),
                                  ('/fila?pagina=abc', 400)):
            with self.subTest(caminho=caminho):
                self.assertEqual(self.requisitar('GET', caminho)[0], esperado)

    def test_folha_com_erro_pode_ser_reprocessada_ou_descartada_sem_duplicar(self):
        import json
        identificador = self.fila.adicionar(b'foto de teste', '.png')
        self.fila.proxima('Tesseract')
        self.fila.marcar_erro(identificador, 'Falha de processamento de teste')
        painel = json.loads(self.requisitar('GET', '/fila')[2])
        self.assertEqual(painel['erros'][0]['id'], identificador)
        self.assertIn('Falha de processamento', painel['erros'][0]['motivo'])
        rota = f'/fila/{identificador}'
        self.assertEqual(self.requisitar('POST', rota + '/reprocessar')[0], 200)
        self.assertEqual(self.requisitar('POST', rota + '/reprocessar')[0], 409)
        self.assertEqual(self.requisitar('POST', rota + '/descartar')[0], 409)
        foto = self.fila.proxima('Tesseract')
        self.assertEqual(foto['id'], identificador)
        self.fila.marcar_erro(identificador, 'Outra falha')
        self.assertEqual(self.requisitar('POST', rota + '/descartar')[0], 200)
        self.assertEqual(self.requisitar('GET', rota + '/previa')[0], 410)
        painel = json.loads(self.requisitar('GET', '/fila')[2])
        self.assertEqual(painel['erros'], [])
        self.assertEqual(painel['recentes'][0]['id'], identificador)
        self.assertEqual(painel['recentes'][0]['estado'], 'descartada')


class AberturaRelatorioTests(unittest.TestCase):
    def test_windows_usa_caminho_nativo_com_espacos_e_acentos(self):
        caminho = Path('Pasta com espaços João') / 'relatorio.html'
        with patch.object(main.sys, 'platform', 'win32'), \
                patch.object(main.os, 'startfile', create=True) as abrir, \
                patch.object(main.webbrowser, 'open') as navegador:
            self.assertTrue(main.abrir_arquivo_relatorio(caminho))
        abrir.assert_called_once_with(str(caminho.resolve()))
        navegador.assert_not_called()

    def test_falha_da_abertura_nativa_tenta_navegador(self):
        caminho = Path('relatorio.html')
        with patch.object(main.sys, 'platform', 'win32'), \
                patch.object(main.os, 'startfile', create=True, side_effect=OSError('sem associacao')), \
                patch.object(main.webbrowser, 'open', return_value=True) as abrir:
            self.assertTrue(main.abrir_arquivo_relatorio(caminho))
        abrir.assert_called_once_with(caminho.resolve().as_uri(), new=2)

    def test_erro_do_navegador_retorna_falha(self):
        with patch.object(main.sys, 'platform', 'linux'), \
                patch.object(main.webbrowser, 'open', side_effect=main.webbrowser.Error('indisponivel')):
            self.assertFalse(main.abrir_arquivo_relatorio('relatorio.html'))

    def test_relatorio_e_gravado_com_filtro_sem_abrir_programas(self):
        import os
        with tempfile.TemporaryDirectory() as pasta:
            anterior = Path.cwd()
            os.chdir(pasta)
            try:
                Path('a1.txt').write_text('04/11/2026 Pagamento 100,00D\n04/11/2026 Entrada <teste> 200,00C\n', encoding='utf-8')
                Path('a2.txt').write_text('[2] 04/11/2026 Entrada <teste> 200,00C\n', encoding='utf-8')
                with patch.object(main, 'abrir_arquivo_relatorio') as abrir:
                    caminho = main.gerar_relatorio_html('C', 'Entrada', abrir=False)
                html = Path(caminho).read_text(encoding='utf-8')
                abrir.assert_not_called()
                self.assertIn('Entrada &lt;teste&gt;', html)
                self.assertNotIn('Pagamento 100,00D', html)
                self.assertIn('window.print()', html)
                self.assertIn('Faltando no A2:</b> 0', html)
            finally:
                os.chdir(anterior)
