import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import main


class LancamentosComSinalTests(unittest.TestCase):
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
                                 [(1, False), (2, True), (3, False)])


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

    def test_referencia_com_texto_alterado_nao_confere_outro_registro(self):
        resultado, _, faltando = self.comparar(
            "Pagamento A -700,00D\nPagamento B -700,00D\n",
            "[2] Pagamento antigo -700,00D\n")
        self.assertEqual([ok for _, _, ok in resultado], [False, False])
        self.assertEqual(faltando, 2)

    def test_referencia_inexistente_nao_confere_por_valor(self):
        resultado, _, _ = self.comparar("Pagamento -700,00D\n", "[99] Pagamento -700,00D\n")
        self.assertFalse(resultado[0][2])

    def test_referencia_duplicada_confere_uma_unica_linha(self):
        resultado, _, _ = self.comparar(
            "Pagamento -700,00D\nPagamento -700,00D\n",
            "[2] Pagamento -700,00D\n[2] Pagamento -700,00D\n")
        self.assertEqual([ok for _, _, ok in resultado], [False, True])

    def test_itens_sem_referencia_consumem_ocorrencias_do_mesmo_tipo(self):
        resultado, total, faltando = self.comparar(
            "Débito A -700,00D\nDébito B -700,00D\nCrédito 700,00C\n",
            "Pagamento 700,00D\n")
        self.assertEqual([ok for _, _, ok in resultado], [True, False, False])
        self.assertEqual((total, faltando), (3, 2))

    def test_selecao_referenciada_tem_prioridade_sobre_comparacao_por_valor(self):
        resultado, _, faltando = self.comparar(
            "Débito A -700,00D\nDébito B -700,00D\nDébito C -700,00D\n",
            "Pagamento 700,00D\n[1] Débito A -700,00D\n")
        self.assertEqual([ok for _, _, ok in resultado], [True, True, False])
        self.assertEqual(faltando, 1)

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
        self.assertEqual([(n, ok) for n, _, ok in resultado], [(2, True)])


if __name__ == "__main__":
    unittest.main()
