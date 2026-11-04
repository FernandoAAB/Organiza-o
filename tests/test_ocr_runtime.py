"""Usa processos reais para testar bloqueio nativo, crash e limite do OCR."""
import ctypes
import os
import threading
import time
import unittest
from ocr_runtime import ExecutorOCR


def tarefa_teste(conteudo, extensao, motor):
    if conteudo == b"crash":
        os._exit(3)
    if conteudo == b"erro":
        raise RuntimeError("erro de teste")
    if conteudo == b"nativo":
        # PyDLL mantém o GIL durante a chamada; uma thread não isolaria isto.
        if os.name == "nt":
            ctypes.PyDLL("kernel32").Sleep(1000)
        else:
            ctypes.PyDLL(None).sleep(1)
    return str(os.getpid()), ""


class IsolamentoOCRTests(unittest.TestCase):
    def criar(self):
        executor = ExecutorOCR(timeout=15, processador=tarefa_teste)
        self.addCleanup(executor.fechar)
        return executor

    def test_processo_real_e_reutilizado_sem_rodar_ocr_na_interface(self):
        executor = self.criar()
        pid, aviso = executor.ler(b"pid", ".png", "PaddleOCR")
        self.assertEqual(aviso, "")
        self.assertNotEqual(int(pid), os.getpid())
        self.assertEqual(executor.ler(b"pid", ".png", "PaddleOCR"), (pid, ""))

    def test_crash_e_erro_nao_impedem_leitura_seguinte(self):
        executor = self.criar()
        for conteudo in (b"erro", b"crash"):
            self.assertTrue(executor.ler(conteudo, ".png", "PaddleOCR")[1])
            texto, aviso = executor.ler(b"pid", ".png", "PaddleOCR")
            self.assertTrue(texto.isdigit())
            self.assertEqual(aviso, "")

    def test_timeout_encerra_processo_e_permite_recomecar(self):
        executor = self.criar()
        executor.ler(b"pid", ".png", "PaddleOCR")
        executor.timeout = 0.1
        texto, aviso = executor.ler(b"nativo", ".png", "PaddleOCR")
        self.assertEqual(texto, "")
        self.assertIn("limite de tempo", aviso)
        executor.timeout = 15
        self.assertEqual(executor.ler(b"pid", ".png", "PaddleOCR")[1], "")

    def test_fechar_interrompe_leitura_ativa(self):
        executor = self.criar()
        executor.ler(b"pid", ".png", "PaddleOCR")
        processo = executor.processo
        thread = threading.Thread(target=executor.ler, args=(b"nativo", ".png", "PaddleOCR"))
        thread.start()
        time.sleep(0.1)
        executor.fechar()
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertFalse(processo.is_alive())
