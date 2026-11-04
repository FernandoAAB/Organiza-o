"""Contratos de persistência, ordem, concorrência e recuperação da fila."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import threading
import tempfile
import unittest
from unittest.mock import patch
from fila_ocr import FilaOCR


class FilaOCRTests(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.fila = FilaOCR(self.pasta, exclusivo=True)
        self.addCleanup(self.fila.fechar)

    def test_imagens_fora_do_banco_e_valores_armazenados_separadamente(self):
        id_foto = self.fila.adicionar(b'foto de teste', '.png')
        foto = self.fila.proxima('PaddleOCR')
        self.assertEqual(foto['id'], id_foto)
        self.assertEqual(self.fila.caminho(foto).read_bytes(), b'foto de teste')
        self.fila.resultado(id_foto, 'texto', 'revisar', {'valor': '123.45'})
        with closing(sqlite3.connect(self.fila.banco)) as db:
            dados = db.execute('SELECT imagem, campos, estado FROM fotos').fetchone()
        self.assertEqual(dados[0], foto['imagem'])
        self.assertIn('123.45', dados[1])
        self.assertEqual(dados[2], 'revisao')

    def test_ordem_e_recuperacao_de_leitura_interrompida(self):
        ids = [self.fila.adicionar(str(n).encode(), '.jpg') for n in range(3)]
        self.assertEqual(self.fila.proxima('PaddleOCR')['id'], ids[0])
        self.fila.fechar()
        nova = FilaOCR(self.pasta, exclusivo=True)
        self.addCleanup(nova.fechar)
        nova.recuperar()
        foto = nova.proxima('Tesseract')
        self.assertEqual(foto['id'], ids[0])
        self.assertEqual(foto['motor'], 'PaddleOCR')
        for id_foto in ids:
            foto = foto if id_foto == ids[0] else nova.proxima('PaddleOCR')
            self.assertEqual(foto['id'], id_foto)
            nova.finalizar(id_foto, 'concluida')
        self.assertEqual(nova.quantidade(), 0)
        self.assertEqual(list(nova.imagens.iterdir()), [])

    def test_revisao_e_campos_editados_sobrevivem_ao_reinicio(self):
        identificador = self.fila.adicionar(b'imagem', '.png')
        self.fila.proxima('Tesseract')
        self.fila.resultado(identificador, 'texto', 'incerta', {'valor': '10'})
        self.fila.salvar_campos(identificador, {'valor': '25.60'})
        self.fila.adicionar(b'outra', '.png')
        self.fila.recuperar()
        foto = self.fila.proxima('PaddleOCR')
        self.assertEqual(foto['estado'], 'revisao')
        self.assertIn('25.60', foto['campos'])
        self.assertEqual(foto['aviso'], 'incerta')
        self.assertTrue(self.fila.caminho(foto).exists())

    def test_envios_simultaneos_nao_perdem_fotos(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda n: self.fila.adicionar(str(n).encode(), '.png'), range(20)))
        self.assertEqual(len(set(ids)), 20)
        self.assertEqual(self.fila.quantidade(), 20)
        self.assertEqual(len(list(self.fila.imagens.iterdir())), 20)

    def test_falha_no_banco_nao_deixa_imagem_confirmada(self):
        with patch.object(self.fila, '_conectar', side_effect=sqlite3.OperationalError('disco cheio')):
            with self.assertRaises(sqlite3.OperationalError):
                self.fila.adicionar(b'foto', '.png')
        self.assertEqual(list(self.fila.imagens.iterdir()), [])
        self.assertEqual(self.fila.quantidade(), 0)

    def test_duas_instancias_nao_processam_a_mesma_fila(self):
        with self.assertRaisesRegex(RuntimeError, 'outro programa'):
            FilaOCR(self.pasta, exclusivo=True)

    def test_exclusao_de_imagem_nao_apaga_resultado_do_banco(self):
        identificador = self.fila.adicionar(b'foto', '.png')
        self.fila.proxima('Tesseract')
        self.fila.resultado(identificador, 'recibo', '', {'valor': '1.00'})
        self.fila.finalizar(identificador, 'concluida')
        self.assertEqual(list(self.fila.imagens.iterdir()), [])
        with closing(sqlite3.connect(self.fila.banco)) as db:
            foto = db.execute('SELECT estado, texto, campos, imagem FROM fotos').fetchone()
        self.assertEqual(foto[0:2], ('concluida', 'recibo'))
        self.assertIn('1.00', foto[2])
        self.assertIsNone(foto[3])

    def test_lote_invalido_nao_confirma_nenhuma_foto(self):
        with self.assertRaises(ValueError):
            self.fila.adicionar_lote([(b'primeira', '.png'), (b'segunda', '.exe')])
        self.assertEqual(self.fila.quantidade(), 0)
        self.assertEqual(list(self.fila.imagens.iterdir()), [])

    def test_limpeza_lenta_nao_bloqueia_gravacao_de_novos_envios(self):
        ids = self.fila.adicionar_lote([(b'primeira', '.png'), (b'segunda', '.png')])
        with self.fila._conectar() as db:
            db.execute("UPDATE fotos SET estado='concluida'")
            fotos = db.execute('SELECT imagem FROM fotos ORDER BY id').fetchall()
        segundo = self.fila.imagens / fotos[1]['imagem']
        entrou, liberar, gravou = threading.Event(), threading.Event(), threading.Event()
        unlink_original = Path.unlink
        def remover(caminho, *args, **kwargs):
            if caminho == segundo:
                entrou.set()
                liberar.wait(timeout=5)
            return unlink_original(caminho, *args, **kwargs)
        def adicionar():
            self.fila.adicionar(b'nova', '.png')
            gravou.set()
        with patch.object(Path, 'unlink', remover):
            limpeza = threading.Thread(target=self.fila.limpar_concluidas)
            limpeza.start()
            try:
                self.assertTrue(entrou.wait(timeout=2))
                envio = threading.Thread(target=adicionar)
                envio.start()
                livre = gravou.wait(timeout=0.5)
            finally:
                liberar.set()
                limpeza.join(timeout=5)
                if 'envio' in locals():
                    envio.join(timeout=5)
        self.assertTrue(livre, 'A exclusao da imagem segurou a escrita no banco.')
        self.assertEqual(self.fila.quantidade(), 1)

    def foto_png(self):
        import io
        from PIL import Image
        dados = io.BytesIO()
        Image.new('RGB', (1200, 1600), 'white').save(dados, format='PNG')
        return dados.getvalue()

    def test_previa_temporaria_some_mas_numero_e_estado_permanecem(self):
        import io
        from PIL import Image
        identificador = self.fila.adicionar(self.foto_png(), '.png')
        painel = self.fila.painel()
        self.assertEqual(painel['folhas'][0]['id'], identificador)
        self.assertEqual(painel['folhas'][0]['estado'], 'aguardando')
        with Image.open(io.BytesIO(self.fila.previa(identificador))) as previa:
            self.assertEqual(previa.format, 'JPEG')
            self.assertLessEqual(previa.width, 480)
            self.assertLessEqual(previa.height, 640)
        self.fila.proxima('PaddleOCR')
        self.assertEqual(self.fila.painel()['folhas'][0]['estado'], 'processando')
        self.fila.resultado(identificador, 'recibo', 'revisar', {'valor': '10.00'})
        self.assertEqual(self.fila.painel()['folhas'][0]['estado'], 'revisao')
        self.fila.finalizar(identificador, 'concluida')
        self.assertIsNone(self.fila.previa(identificador))
        painel = self.fila.painel()
        self.assertEqual(painel['folhas'], [])
        self.assertEqual(painel['recentes'][0], dict(id=identificador, estado='concluida', previa=None))
        self.assertEqual(painel['totais']['concluida'], 1)

    def test_painel_paginado_preserva_ordem_e_ids(self):
        ids = self.fila.adicionar_lote([(b'foto', '.png')] * 27)
        self.assertEqual([f['id'] for f in self.fila.painel()['folhas']], ids[:24])
        self.assertEqual([f['id'] for f in self.fila.painel(1)['folhas']], ids[24:])
        self.assertEqual(self.fila.painel(999)['pagina'], 1)
        self.assertEqual(self.fila.painel()['pendentes'], 27)
        self.fila.finalizar(ids[0], 'descartada')
        self.fila.recuperar()
        self.assertEqual(self.fila.painel()['folhas'][0]['id'], ids[1])
        self.assertEqual(self.fila.painel()['recentes'][0]['id'], ids[0])

    def test_cache_de_previas_e_limitado_e_nao_altera_imagem_original(self):
        conteudo = self.foto_png()
        ids = self.fila.adicionar_lote([(conteudo, '.png')] * 18)
        for identificador in ids:
            self.assertIsNotNone(self.fila.previa(identificador))
        self.assertLessEqual(len(self.fila._previas), 16)
        foto = self.fila.proxima('PaddleOCR')
        self.assertEqual(self.fila.caminho(foto).read_bytes(), conteudo)

    def test_previa_invalida_nao_apaga_foto_pendente(self):
        identificador = self.fila.adicionar(b'foto invalida', '.png')
        self.assertIsNone(self.fila.previa(identificador))
        self.assertEqual(self.fila.quantidade(), 1)
