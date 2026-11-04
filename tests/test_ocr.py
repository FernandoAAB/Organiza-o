# Usa resultados simulados para verificar o tratamento do OCR sem depender do executável externo.
"""Contratos do OCR: preservação de linhas e revisão de leituras incertas."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import main


def resultado(texto, confianca=95):
    palavras, linhas = [], []
    for numero, linha in enumerate(texto.splitlines(), 1):
        for palavra in linha.split():
            palavras.append(palavra)
            linhas.append(numero)
    return dict(text=palavras, conf=[confianca] * len(palavras),
                page_num=[1] * len(palavras), block_num=[1] * len(palavras),
                par_num=[1] * len(palavras), line_num=linhas)


class OCRTests(unittest.TestCase):
    def ler(self, resultados):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'recibo.png'
            Image.new('RGB', (400, 150), 'white').save(caminho)
            with patch.object(main.pytesseract, 'image_to_data', side_effect=resultados):
                return main.executar_ocr(caminho)

    def test_preserva_linhas_e_escolhe_leitura_mais_confiavel(self):
        bom = 'Mercado Central\n04/11/2026\nTotal a pagar R$ 123,45'
        ruim = 'Mercado CentraI\n04/11/2026\nTotal a pagar R$ 123,45'
        texto, aviso = self.ler([resultado(ruim, 65), resultado(bom, 95)])
        self.assertEqual(texto, bom)
        self.assertEqual(aviso, '')

    def test_divergencia_financeira_exige_revisao_mesmo_com_alta_confianca(self):
        texto, aviso = self.ler([
            resultado('Pagamento\n04/11/2026\nTotal a pagar 123,45'),
            resultado('Pagamento\n04/11/2026\nTotal a pagar 128,45')])
        self.assertIn('123,45', texto)
        self.assertIn('Leitura incerta', aviso)

    def test_baixa_confianca_exige_revisao(self):
        texto, aviso = self.ler([resultado('Pagamento 123,45', 40)] * 2)
        self.assertEqual(texto, 'Pagamento 123,45')
        self.assertIn('Leitura incerta', aviso)

    def test_numero_incerto_exige_revisao_mesmo_com_texto_confiavel(self):
        dados = resultado('Mercado Central Pagamento total a pagar R$ 123,45', 99)
        dados['conf'][-1] = 45
        texto, aviso = self.ler([dados, dados])
        self.assertIn('123,45', texto)
        self.assertIn('Leitura incerta', aviso)

    def test_falha_de_segunda_leitura_preserva_primeira_para_revisao(self):
        texto, aviso = self.ler([resultado('Pagamento 123,45'), RuntimeError('timeout')])
        self.assertEqual(texto, 'Pagamento 123,45')
        self.assertTrue(aviso)

    def test_imagem_transparente_preserva_texto_escuro_sobre_branco(self):
        imagem = Image.new('RGBA', (400, 150), (0, 0, 0, 0))
        imagem.putpixel((100, 75), (0, 0, 0, 255))
        variantes = main.preparar_imagens_ocr(imagem)
        self.assertEqual(len(variantes), 2)
        for variante in variantes:
            self.assertEqual(variante.getpixel((0, 0)), 255)
            self.assertLess(variante.getextrema()[0], 255)

    def test_linux_nao_seleciona_executavel_windows_nem_altera_ambiente(self):
        import os
        with patch.object(main.sys, 'platform', 'linux'), \
                patch.object(main.pytesseract.pytesseract, 'tesseract_cmd', 'tesseract'):
            anterior = os.environ.get('TESSDATA_PREFIX')
            self.ler([resultado('Pagamento 123,45')] * 2)
            self.assertEqual(main.pytesseract.pytesseract.tesseract_cmd, 'tesseract')
            self.assertEqual(os.environ.get('TESSDATA_PREFIX'), anterior)
