"""Executa OCR em um processo persistente, separado da janela e do seu GIL."""
import multiprocessing
import os
import threading
import time
import tempfile


def _ler_captura(conteudo, extensao, motor):
    from main import App
    return App.ler_imagem_captura(conteudo, extensao, motor)


def _servir(conexao, processador):
    # Evita que bibliotecas numéricas ocupem todos os núcleos do computador.
    for nome in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[nome] = "2"
    try:
        while True:
            conteudo, extensao, motor, pasta = conexao.recv()
            tempfile.tempdir = pasta
            try:
                resultado = processador(conteudo, extensao, motor)
            except Exception as erro:
                resultado = ("", f"Não foi possível ler a imagem: {erro}")
            conexao.send(resultado)
    except (EOFError, OSError):
        pass
    finally:
        conexao.close()


class ExecutorOCR:
    def __init__(self, timeout=180, processador=None):
        self.timeout = timeout
        self.processador = processador or _ler_captura
        self.processo = None
        self.conexao = None
        self._fechado = False
        self._estado = threading.Lock()
        self._leitura = threading.Lock()

    def _obter(self):
        with self._estado:
            if self._fechado:
                raise RuntimeError("O processamento de OCR foi encerrado.")
            if self.processo is None:
                contexto = multiprocessing.get_context("spawn")
                pai, filho = contexto.Pipe()
                processo = contexto.Process(target=_servir, args=(filho, self.processador), daemon=True)
                try:
                    processo.start()
                except Exception:
                    pai.close()
                    filho.close()
                    raise
                filho.close()
                self.processo, self.conexao = processo, pai
            return self.processo, self.conexao

    def _parar(self, processo, conexao):
        with self._estado:
            if self.processo is processo:
                self.processo = self.conexao = None
            if conexao is not None and conexao.closed:
                return
            if processo is not None:
                if processo.is_alive():
                    processo.terminate()
                processo.join(timeout=0.5)
                if processo.is_alive():
                    processo.kill()
                    processo.join(timeout=0.5)
            if conexao is not None:
                conexao.close()

    def ler(self, conteudo, extensao, motor):
        with self._leitura:
            processo = conexao = pasta = None
            try:
                processo, conexao = self._obter()
                pasta = tempfile.TemporaryDirectory(prefix="ocr_", ignore_cleanup_errors=True)
                conexao.send((conteudo, extensao, motor, pasta.name))
                limite = time.monotonic() + self.timeout
                while not conexao.poll(0.1):
                    if not processo.is_alive():
                        raise RuntimeError("O processo de OCR encerrou inesperadamente.")
                    if time.monotonic() >= limite:
                        raise TimeoutError("A leitura excedeu o limite de tempo. Tente outra foto.")
                return conexao.recv()
            except Exception as erro:
                self._parar(processo, conexao)
                return "", f"OCR indisponível: {erro}"
            finally:
                if pasta is not None:
                    pasta.cleanup()

    def fechar(self):
        with self._estado:
            self._fechado = True
            processo, conexao = self.processo, self.conexao
            self.processo = self.conexao = None
        self._parar(processo, conexao)
