"""Fila local durável: metadados no SQLite, imagens separadas no disco."""
import json
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import uuid


class FilaOCR:
    def __init__(self, pasta, exclusivo=False):
        self.pasta = Path(pasta).resolve()
        self.imagens = self.pasta / "imagens"
        self.imagens.mkdir(parents=True, exist_ok=True)
        self.banco = self.pasta / "fila.sqlite3"
        self._lock = None
        if exclusivo:
            arquivo = open(self.pasta / "processamento.lock", "a+b")
            try:
                arquivo.seek(0, 2)
                if arquivo.tell() == 0:
                    arquivo.write(b"0")
                    arquivo.flush()
                arquivo.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                arquivo.close()
                raise RuntimeError("A fila já está aberta em outro programa nesta pasta.")
            self._lock = arquivo
        with self._conectar() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute('''CREATE TABLE IF NOT EXISTS fotos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                imagem TEXT, extensao TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'aguardando', motor TEXT,
                texto TEXT NOT NULL DEFAULT '', aviso TEXT NOT NULL DEFAULT '',
                campos TEXT NOT NULL DEFAULT '{}',
                recebido TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            db.execute("CREATE INDEX IF NOT EXISTS ordem_fila ON fotos(estado, id)")

    @contextmanager
    def _conectar(self, timeout=5):
        db = sqlite3.connect(self.banco, timeout=timeout)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def adicionar(self, conteudo, extensao):
        return self.adicionar_lote([(conteudo, extensao)])[0]

    def adicionar_lote(self, arquivos):
        salvos = []
        try:
            for conteudo, extensao in arquivos:
                if extensao not in ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'):
                    raise ValueError("Formato de imagem não aceito.")
                if not conteudo or len(conteudo) > 15 * 1024 * 1024:
                    raise ValueError("Imagem vazia ou maior que 15 MB.")
                nome = uuid.uuid4().hex + extensao
                caminho = self.imagens / nome
                salvos.append((caminho, extensao))
                with caminho.open('xb') as arquivo:
                    arquivo.write(conteudo)
                    arquivo.flush()
                    os.fsync(arquivo.fileno())
            with self._conectar() as db:
                ids = []
                for caminho, extensao in salvos:
                    cursor = db.execute("INSERT INTO fotos(imagem, extensao) VALUES (?, ?)",
                                        (caminho.name, extensao))
                    ids.append(cursor.lastrowid)
            return ids
        except Exception:
            for caminho, _ in salvos:
                caminho.unlink(missing_ok=True)
            raise

    def recuperar(self):
        # Só o dono exclusivo da fila chama isto, antes de receber novos envios.
        with self._conectar() as db:
            db.execute("UPDATE fotos SET estado='aguardando' WHERE estado='processando'")
            nomes = {r[0] for r in db.execute("SELECT imagem FROM fotos WHERE imagem IS NOT NULL")}
        for arquivo in self.imagens.iterdir():
            if arquivo.name not in nomes:
                arquivo.unlink(missing_ok=True)
        self.limpar_concluidas()

    def proxima(self, motor):
        with self._conectar(timeout=0.05) as db:
            db.execute('BEGIN IMMEDIATE')
            foto = db.execute("SELECT * FROM fotos WHERE estado IN ('aguardando','revisao') ORDER BY id LIMIT 1").fetchone()
            if foto is None:
                return None
            if foto['estado'] == 'aguardando':
                db.execute("UPDATE fotos SET estado='processando', motor=COALESCE(motor,?) WHERE id=?", (motor, foto['id']))
                foto = db.execute("SELECT * FROM fotos WHERE id=?", (foto['id'],)).fetchone()
            return dict(foto)

    def caminho(self, foto):
        return self.imagens / foto['imagem']

    def resultado(self, identificador, texto, aviso, campos):
        with self._conectar() as db:
            db.execute("UPDATE fotos SET estado='revisao', texto=?, aviso=?, campos=? WHERE id=?",
                       (texto, aviso, json.dumps(campos, ensure_ascii=False), identificador))

    def salvar_campos(self, identificador, campos):
        with self._conectar() as db:
            db.execute("UPDATE fotos SET campos=? WHERE id=? AND estado='revisao'",
                       (json.dumps(campos, ensure_ascii=False), identificador))

    def finalizar(self, identificador, estado):
        if estado not in ('concluida', 'descartada'):
            raise ValueError(estado)
        with self._conectar() as db:
            db.execute("UPDATE fotos SET estado=? WHERE id=?", (estado, identificador))
        self.limpar_concluidas()

    def limpar_concluidas(self):
        with self._conectar() as db:
            fotos = db.execute("SELECT id, imagem FROM fotos WHERE estado IN ('concluida','descartada') AND imagem IS NOT NULL").fetchall()
        removidas = []
        # A exclusão no disco pode ser lenta (antivírus, HD, sincronização).
        # Faça-a antes de abrir a transação de escrita no SQLite.
        for foto in fotos:
            try:
                (self.imagens / foto['imagem']).unlink(missing_ok=True)
            except OSError:
                continue
            removidas.append((foto['id'],))
        if removidas:
            with self._conectar() as db:
                db.executemany("UPDATE fotos SET imagem=NULL WHERE id=? AND estado IN ('concluida','descartada')", removidas)

    def quantidade(self, estado=None):
        with self._conectar(timeout=0.05) as db:
            if estado:
                return db.execute("SELECT COUNT(*) FROM fotos WHERE estado=?", (estado,)).fetchone()[0]
            return db.execute("SELECT COUNT(*) FROM fotos WHERE estado IN ('aguardando','processando','revisao')").fetchone()[0]

    def fechar(self):
        if self._lock is not None:
            self._lock.close()
            self._lock = None
