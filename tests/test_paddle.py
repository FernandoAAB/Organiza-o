# Simula o PaddleOCR para validar ordenação, confiança e falhas sem baixar modelos.
"""Integração opcional sem baixar modelos durante a suíte."""
import unittest
import math
from unittest.mock import Mock, patch

import main
import ocr_paddle


def pagina(textos, caixas, scores=None):
    return dict(rec_texts=textos, rec_boxes=caixas,
                rec_scores=scores or [0.99] * len(textos))


class PaddleTests(unittest.TestCase):
    def test_reconstroi_rotulo_e_valor_na_mesma_linha_em_ordem_de_leitura(self):
        dados = pagina(['123,45', 'Mercado Central', 'Total a pagar'],
                       [[200, 41, 290, 61], [0, 0, 150, 20], [0, 40, 140, 60]])
        texto, aviso = ocr_paddle.organizar_resultado([dados])
        self.assertEqual(texto, 'Mercado Central\nTotal a pagar 123,45')
        self.assertEqual(aviso, '')

    def test_inclinacao_nao_mistura_linhas_vizinhas(self):
        seno, cosseno = math.sin(0.1), math.cos(0.1)
        poligonos = []
        caixas = []
        for x, y, largura in ((0, 0, 150), (0, 30, 150), (200, 30, 80)):
            pontos = [(cosseno * a - seno * b, seno * a + cosseno * b)
                      for a, b in ((x, y), (x + largura, y),
                                   (x + largura, y + 20), (x, y + 20))]
            poligonos.append(pontos)
            caixas.append([min(a for a, _ in pontos), min(b for _, b in pontos),
                           max(a for a, _ in pontos), max(b for _, b in pontos)])
        dados = pagina(['04/11/2026', 'Total a pagar', '123,45'], caixas)
        dados['rec_polys'] = poligonos
        texto, aviso = ocr_paddle.organizar_resultado([dados])
        self.assertEqual(texto, '04/11/2026\nTotal a pagar 123,45')
        self.assertEqual(aviso, '')

    def test_numero_pouco_confiavel_exige_revisao(self):
        dados = pagina(['Mercado Central', '123,45'],
                       [[0, 0, 150, 20], [0, 40, 150, 60]], [0.99, 0.6])
        texto, aviso = ocr_paddle.organizar_resultado([dados])
        self.assertIn('123,45', texto)
        self.assertIn('incerta', aviso)

    def test_instalacao_opcional_ausente_exibe_orientacao(self):
        with patch.object(ocr_paddle, '_motor', None), \
                patch.object(ocr_paddle, 'criar_motor', side_effect=ImportError):
            texto, aviso = ocr_paddle.executar_paddleocr('foto.png')
        self.assertEqual(texto, '')
        self.assertIn('não instalado', aviso)

    def test_modelo_sem_texto_nao_inventa_campos(self):
        self.assertEqual(ocr_paddle.organizar_resultado([
            pagina([], [])])[0], '')

    def test_falha_de_modelo_nao_interrompe_aplicativo(self):
        modelo = Mock()
        modelo.predict.side_effect = RuntimeError('modelo incompleto')
        with patch.object(ocr_paddle, '_motor', modelo):
            texto, aviso = ocr_paddle.executar_paddleocr('foto.png')
        self.assertEqual(texto, '')
        self.assertIn('modelo incompleto', aviso)

    def test_comparar_libera_fluxo_automatico_quando_campos_concordam(self):
        texto = 'Mercado\n04/11/2026\nTotal a pagar 123,45'
        with patch.object(main, 'executar_ocr', return_value=(texto, '')), \
                patch.object(ocr_paddle, 'executar_paddleocr', return_value=(texto.replace('Mercado', 'Descricao diferente'), '')):
            obtido, aviso = main.executar_ocr_motor('foto.png', 'Comparar')
        self.assertEqual(obtido, texto.replace('Mercado', 'Descricao diferente'))
        self.assertEqual(aviso, '')

    def test_comparar_nao_oculta_divergencia_financeira(self):
        with patch.object(main, 'executar_ocr', return_value=(
                    'Mercado\n04/11/2026\nTotal a pagar 123,45', '')), \
                patch.object(ocr_paddle, 'executar_paddleocr', return_value=(
                    'Mercado\n04/11/2026\nTotal a pagar 128,45', '')):
            _, aviso = main.executar_ocr_motor('foto.png', 'Comparar')
        self.assertIn('divergência', aviso)

    def test_comparar_preserva_tesseract_se_paddle_indisponivel(self):
        with patch.object(main, 'executar_ocr', return_value=('Texto original', '')), \
                patch.object(ocr_paddle, 'executar_paddleocr', return_value=('', 'PaddleOCR não instalado')):
            texto, aviso = main.executar_ocr_motor('foto.png', 'Comparar')
        self.assertEqual(texto, 'Texto original')
        self.assertIn('não instalado', aviso)

    def test_concordancia_supera_aviso_generico_de_confianca(self):
        texto = 'Mercado\n04/11/2026\nTotal a pagar 123,45'
        for aviso_paddle, aviso_tesseract in (('Leitura incerta PaddleOCR', ''),
                                             ('', 'Leitura incerta Tesseract'),
                                             ('Leitura incerta do PaddleOCR', 'Leitura incerta: confira os campos')):
            with self.subTest(paddle=aviso_paddle, tesseract=aviso_tesseract):
                with patch.object(main, 'executar_ocr', return_value=(texto, aviso_tesseract)), \
                        patch.object(ocr_paddle, 'executar_paddleocr', return_value=(texto, aviso_paddle)):
                    _, aviso = main.executar_ocr_motor('foto.png', 'Comparar')
                self.assertEqual(aviso, '')

    def test_concordancia_nao_esconde_falha_parcial_de_um_motor(self):
        texto = 'Mercado\n04/11/2026\nTotal a pagar 123,45'
        with patch.object(main, 'executar_ocr', return_value=(texto, 'Uma das leituras falhou')), \
                patch.object(ocr_paddle, 'executar_paddleocr', return_value=(texto, '')):
            _, aviso = main.executar_ocr_motor('foto.png', 'Comparar')
        self.assertIn('falhou', aviso)
        self.assertIn('manualmente', aviso)
