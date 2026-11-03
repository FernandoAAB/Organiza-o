import tempfile
import unittest
import threading
import urllib.request
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

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
                self.assertIn('onchange="this.form.submit()"', pagina)
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

    def test_interpretacao_nao_inventa_campos_ausentes(self):
        self.assertEqual(main.interpretar_texto_documento("Recibo sem valor"), {
            "descricao": "Recibo sem valor", "data": "", "valor": "", "tipo": ""
        })

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
