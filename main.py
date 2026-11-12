# Aplicativo desktop: reúne a conferência A1 × A2, a interface e a captura de documentos.
# Os dados de uso ficam no diretório de execução; o Tesseract portátil é localizado junto deste módulo.
import json
import csv
import sqlite3
import io
import subprocess
import multiprocessing
from urllib.parse import urlsplit, parse_qs
import queue
import os
import re
import shutil
import socket
import sys
import threading
import webbrowser
import tkinter as tk
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import Counter
from datetime import datetime
from decimal import Decimal
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from tkinter import ttk, messagebox, simpledialog
from tkinter import font as tkfont
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageStat, ImageTk
try:
    import pytesseract
except ImportError:
    pytesseract = None
try:
    import qrcode
except ImportError:
    qrcode = None

import customtkinter as ctk  # pip install customtkinter
from fila_ocr import FilaOCR
from ocr_runtime import ExecutorOCR, preparar_console_windows
import ocr_paddle  # Adaptador leve; os modelos só carregam quando selecionados.

# A1 guarda a origem; A2 registra os itens escolhidos com a referência da linha original.
ARQUIVO_ORIGEM = "a1.txt"
ARQUIVO_DESTINO = "a2.txt"
PASTA_REG = "No"
CONFIG = os.path.join(PASTA_REG, "config.json")
ARQUIVO_ATENCAO = os.path.join(PASTA_REG, "atencao.json")
TESSERACT_PORTATIL = Path(__file__).resolve().parent / "Tesseract-OCR"


# TEMAS  (cada cor: (claro, escuro))

TEMAS = {
    "bg": ("#e4eaf1", "#06121e"),
    "painel": ("#f8fafc", "#0b1c2b"),
    "superficie": ("#dbe4ee", "#071724"),
    "borda": ("#9aadc1", "#183143"),
    "campo": ("#ffffff", "#152c3d"),
    "campo_hover": ("#dce6f1", "#203b4e"),
    "selecao": ("#d9eaff", "#123e67"),
    "texto": ("#102036", "#f0f6fc"),
    "cinza": ("#586b81", "#acbfd1"),
    "cabecalho": ("#344e69", "#bfd1e2"),
    "grade_cabecalho": ("#cbd7e5", "#071826"),
    "alternada": ("#e2eaf3", "#102332"),
    "verde": ("#008b66", "#00d6a0"),
    "vermelho": ("#e11d48", "#ff416c"),
    "marcado": ("#fef08a", "#3b2d54"),
    "captura": ("#ca8a04", "#facc15"),
    "atencao": ("#854d0e", "#fde047"),
    "atencao_fundo": ("#fff3c4", "#3d3214"),
    "perigo": ("#ffe4e6", "#4c1d24"),
    "perigo_hover": ("#fecdd3", "#6b2129"),
}


ACENTOS = {  # (normal, hover)
    "Índigo": ("#6366f1", "#4f46e5"),
    "Ciano": ("#06b6d4", "#0891b2"),
    "Violeta": ("#8b5cf6", "#7c3aed"),
    "Esmeralda": ("#10b981", "#059669"),
    "Laranja": ("#f97316", "#ea580c"),
    "Azul": ("#3b82f6", "#2563eb"),
}



def c(chave):
    """Cor com as duas variações (CustomTkinter troca sozinho)."""
    return TEMAS[chave]


def cm(chave, modo):
    """Cor única para widgets ttk, conforme o modo atual."""
    return TEMAS[chave][0 if modo == "Claro" else 1]


def carregar_config():
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict):
            return "Escuro", "Esmeralda"
        modo = dados.get("tema", "Escuro")
        acento = dados.get("acento", "Esmeralda")
        return (modo if modo in ("Escuro", "Claro") else "Escuro",
                acento if isinstance(acento, str) and acento in ACENTOS else "Esmeralda")
    except (OSError, ValueError):
        return "Escuro", "Esmeralda"


def salvar_config(modo, acento):
    try:
        os.makedirs(PASTA_REG, exist_ok=True)
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump({"tema": modo, "acento": acento}, f)
    except OSError:
        pass



# LÓGICA (mesmas regras do script original)

def inicializar_arquivos():
    for arquivo in (ARQUIVO_ORIGEM, ARQUIVO_DESTINO):
        if not os.path.exists(arquivo):
            open(arquivo, "w", encoding="utf-8").close()
    caminho_log = os.path.join(PASTA_REG, "data.log")
    if not os.path.exists(PASTA_REG):
        os.makedirs(PASTA_REG)
        with open(caminho_log, "w", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%d/%m/%Y"))
    else:
        verificar_dias()


def verificar_dias():
    caminho_log = os.path.join(PASTA_REG, "data.log")
    if not os.path.exists(caminho_log):
        return
    try:
        with open(caminho_log, "r", encoding="utf-8") as f:
            data_inicial = datetime.strptime(f.read().strip(), "%d/%m/%Y")
        dias = (datetime.now() - data_inicial).days
        with open(os.path.join(PASTA_REG, "data1.log"), "w", encoding="utf-8") as f:
            f.write(f"A diferença de dias é: {dias}")
    except ValueError:
        pass


def carregar_linhas(nome_arquivo):
    if not os.path.exists(nome_arquivo):
        return []
    with open(nome_arquivo, "r", encoding="utf-8-sig") as f:
        return [l.strip() for l in f if l.strip()]


def carregar_origem_numerada():
    """[(numero_da_linha, texto), ...] sem modificar o a1.txt"""
    if not os.path.exists(ARQUIVO_ORIGEM):
        return []
    linhas = []
    with open(ARQUIVO_ORIGEM, "r", encoding="utf-8-sig") as f:
        for numero, linha in enumerate(f, start=1):
            linha = linha.strip()
            if linha:
                linhas.append((numero, linha))
    return linhas


def salvar_linhas(nome_arquivo, linhas):
    """Substitui o arquivo somente depois de gravar todo o conteúdo."""
    caminho = Path(nome_arquivo).absolute()
    temporario = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=caminho.parent,
                                delete=False) as f:
            temporario = Path(f.name)
            for linha in linhas:
                f.write(linha + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporario, caminho)
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)


def chave_atencao(numero, texto):
    return numero, " ".join(texto.split())


def carregar_atencoes():
    try:
        with open(ARQUIVO_ATENCAO, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except FileNotFoundError:
        return set()
    if not isinstance(dados, dict) or dados.get("versao") != 1 or not isinstance(dados.get("marcacoes"), list):
        raise ValueError("Arquivo de atenção inválido: " + ARQUIVO_ATENCAO)
    marcacoes = set()
    for item in dados["marcacoes"]:
        if (not isinstance(item, dict) or type(item.get("linha")) is not int
                or item["linha"] < 1 or not isinstance(item.get("registro"), str)):
            raise ValueError("Marcação de atenção inválida: " + ARQUIVO_ATENCAO)
        marcacoes.add(chave_atencao(item["linha"], item["registro"]))
    return marcacoes


def salvar_atencoes(marcacoes):
    dados = {"versao": 1, "marcacoes": [
        {"linha": numero, "registro": texto} for numero, texto in sorted(marcacoes)]}
    Path(ARQUIVO_ATENCAO).parent.mkdir(parents=True, exist_ok=True)
    salvar_linhas(ARQUIVO_ATENCAO, [json.dumps(dados, ensure_ascii=False, indent=2)])


def identificar_vencimento(texto):
    """Prioriza o rótulo de vencimento; datas ambíguas exigem revisão."""
    padrao = r"\b\d{2}[./-]\d{2}[./-](?:\d{4}|\d{2})\b"
    rotulo = r"\b(?:vencimento|venc\.?|vcto\.?)\b"
    outro_rotulo = r"\b(?:emiss[aã]o|pagamento|agendamento|processamento|documento)\b"

    def validar(valor):
        valor = valor.replace(".", "/").replace("-", "/")
        try:
            datetime.strptime(valor, "%d/%m/%Y" if len(valor) == 10 else "%d/%m/%y")
        except ValueError:
            return ""
        return valor

    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    candidatos = set()
    encontrou_rotulo = False
    vencimento_invalido = False
    for indice, linha in enumerate(linhas):
        for marcador in re.finditer(rotulo, linha, re.I):
            encontrou_rotulo = True
            trecho = re.split(outro_rotulo + "|" + rotulo, linha[marcador.end():],
                              maxsplit=1, flags=re.I)[0]
            datas = re.findall(padrao, trecho)
            if not datas and not trecho.strip(" :.-") and indice + 1 < len(linhas):
                proxima = linhas[indice + 1]
                if re.fullmatch(r"[\s:.-]*(" + padrao + r")[\s.]*", proxima):
                    datas = re.findall(padrao, proxima)
            candidatos.update(valor for data in datas if (valor := validar(data)))
            if not datas or any(not validar(data) for data in datas):
                vencimento_invalido = True
    if encontrou_rotulo:
        if len(candidatos) == 1 and not vencimento_invalido:
            return candidatos.pop(), ""
        return "", "Vencimento ausente, inválido ou com mais de uma data. Informe o vencimento para continuar."
    datas = {valor for data in re.findall(padrao, texto) if (valor := validar(data))}
    data_outro_campo = re.search(
        outro_rotulo + r"(?:[ \t]*:?[ \t]*|\s*:\s*)" + padrao, texto, re.I)
    if datas and data_outro_campo:
        return "", "Vencimento não identificado entre as datas do documento. Informe o vencimento para continuar."
    if len(datas) == 1:
        return datas.pop(), ""
    if datas:
        return "", "Há várias datas e nenhum vencimento identificado. Informe o vencimento para continuar."
    return "", ""


def interpretar_texto_documento(texto):
    """Extrai campos financeiros priorizando rótulos comuns de documentos."""
    padrao_valor = (
        r"(?<![\d.,])(?:R\$\s*)?"
        r"([+-]?\d{1,3}(?:\.\d{3})*,\d{2}|[+-]?\d+,\d{2})(?![\d.,])"
    )
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    valores_contextuais = []
    todos_valores = []
    for linha in linhas:
        encontrados = re.findall(padrao_valor, linha, flags=re.IGNORECASE)
        todos_valores.extend(encontrados)
        if encontrados and re.search(
                r"\b(?:total|valor\s+(?:total|a\s+pagar)|vlr|valor\s+final|pago)\b",
                linha, re.IGNORECASE):
            valores_contextuais.extend(encontrados)
    valores = valores_contextuais or todos_valores
    valor = valores[-1].replace(".", "").replace(",", ".").lstrip("+") if valores else ""
    data, _ = identificar_vencimento(texto)
    tipo = "D" if re.search(r"\b(?:d[eé]bito|pagamento|compra|total a pagar)\b", texto, re.I) else ""
    if not tipo and re.search(r"\b(?:cr[eé]dito|recebimento|entrada)\b", texto, re.I):
        tipo = "C"
    descricao = linhas[0][:120] if linhas else ""
    return {
        "descricao": descricao,
        "data": data,
        "valor": valor,
        "tipo": tipo,
    }


def normalizar_valor_captura(texto):
    """Aceita dinheiro brasileiro e o decimal canônico retornado pelo OCR."""
    texto = texto.strip()
    if re.fullmatch(r"[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{1,2}", texto):
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[+-]?\d+(?:\.\d{1,2})?", texto) is None:
        raise ValueError("Informe um valor monetário válido.")
    return abs(Decimal(texto))


def correspondencias_campos(data, valor_texto, tipo, origem=None, destino=None):
    """Busca por data, valor monetário exato e tipo; a descrição é informativa."""
    if not data or not valor_texto or tipo not in ("D", "C"):
        return []
    try:
        valor = normalizar_valor_captura(valor_texto)
    except (ValueError, ArithmeticError):
        return []
    origem = carregar_origem_numerada() if origem is None else origem
    destino = carregar_linhas(ARQUIVO_DESTINO) if destino is None else destino
    conferidos = referencias_no_destino(origem, destino)
    candidatos = []
    data_digitos = re.sub(r"\D", "", data)
    for numero, registro in origem:
        lancamento = extrair_lancamento(registro)
        datas_registro = re.findall(r"\b\d{2}[./-]\d{2}[./-]\d{2,4}\b", registro)
        data_encontrada = any(re.sub(r"\D", "", item) == data_digitos
                              for item in datas_registro)
        if (numero not in conferidos and lancamento is not None
                and lancamento[0] == tipo
                and data_encontrada
                and lancamento[1] == valor):
            candidatos.append((numero, registro))
    return candidatos


def correspondencias_documento(texto, origem=None, destino=None):
    """Localiza ocorrências do documento no A1 por data, valor e tipo."""
    campos = interpretar_texto_documento(texto)
    return correspondencias_campos(campos["data"], campos["valor"], campos["tipo"],
                                   origem, destino)


# O pré-processamento gera alternativas locais antes de escolher a leitura do documento.
def preparar_imagens_ocr(original):
    """Preserva traços finos e prepara leituras de recibos claros ou escuros."""
    orientada = ImageOps.exif_transpose(original).convert("RGBA")
    fundo = Image.new("RGBA", orientada.size, "white")
    fundo.alpha_composite(orientada)
    imagem = ImageOps.grayscale(fundo)
    imagem = ImageOps.autocontrast(imagem, cutoff=1)
    if ImageStat.Stat(imagem).mean[0] < 127:
        imagem = ImageOps.invert(imagem)
    # A projeção horizontal ajuda a alinhar linhas levemente inclinadas.
    amostra = imagem.copy()
    amostra.thumbnail((700, 700))
    binaria = amostra.point(lambda p: 255 if p > 160 else 0)

    def alinhamento(angulo):
        girada = binaria.rotate(angulo, expand=True, fillcolor=255)
        pixels = list(girada.getdata())
        largura = girada.width
        return sum((largura - sum(pixels[i:i + largura]) / 255) ** 2
                   for i in range(0, len(pixels), largura))

    base = alinhamento(0)
    angulo = max(range(-6, 7), key=alinhamento)
    if angulo and alinhamento(angulo) > base * 1.08:
        imagem = imagem.rotate(angulo, Image.Resampling.BICUBIC,
                               expand=True, fillcolor=255)
    escala = min(3, 1800 / imagem.width, 4000 / max(imagem.size))
    if escala != 1:
        imagem = imagem.resize((max(1, round(imagem.width * escala)),
                                 max(1, round(imagem.height * escala))),
                                Image.Resampling.LANCZOS)
    imagem = imagem.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3))
    # O limiar é calculado pela distribuição de tons (Otsu), não fixado na foto.
    histograma = imagem.histogram()
    total = sum(histograma)
    soma = sum(i * n for i, n in enumerate(histograma))
    peso = parcial = 0
    melhor = -1
    limiar = 127
    for tom, quantidade in enumerate(histograma):
        peso += quantidade
        parcial += tom * quantidade
        if not peso or peso == total:
            continue
        variancia = peso * (total - peso) * (
            parcial / peso - (soma - parcial) / (total - peso)) ** 2
        if variancia > melhor:
            melhor, limiar = variancia, tom
    contraste = imagem.point(lambda p: 255 if p > limiar else 0)
    return [ImageOps.expand(item, border=24, fill=255) for item in (imagem, contraste)]


def ler_resultado_ocr(dados):
    """Reconstrói as linhas e mede a confiança ponderada pelo tamanho das palavras."""
    linhas = {}
    soma = peso = 0
    for i, palavra in enumerate(dados["text"]):
        palavra = palavra.strip()
        confianca = float(dados["conf"][i])
        if not palavra or confianca < 0:
            continue
        chave = tuple(dados[campo][i] for campo in ("page_num", "block_num", "par_num", "line_num"))
        linhas.setdefault(chave, []).append(palavra)
        soma += confianca * len(palavra)
        peso += len(palavra)
    return "\n".join(" ".join(linha) for linha in linhas.values()), soma / peso if peso else 0


def ler_dados_tesseract(imagem, configuracao):
    try:
        return pytesseract.image_to_data(
            imagem, lang="por", output_type=pytesseract.Output.DICT,
            config=configuracao, timeout=20)
    except UnicodeDecodeError:
        # O texto TSV do Tesseract é UTF-8, mas os erros do Windows podem ser
        # CP1252. Não deixe a decodificação do diagnóstico esconder o erro real.
        with NamedTemporaryFile(suffix=".png", delete=False) as arquivo:
            caminho = arquivo.name
        try:
            imagem.save(caminho)
            import shlex
            argumentos = shlex.split(configuracao)
            resultado = subprocess.run(
                [str(pytesseract.pytesseract.tesseract_cmd), caminho, "stdout",
                 "-l", "por", *argumentos, "tsv"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            if resultado.returncode:
                try:
                    detalhe = resultado.stderr.decode("utf-8")
                except UnicodeDecodeError:
                    detalhe = resultado.stderr.decode("cp1252", errors="replace")
                raise RuntimeError("Tesseract: " + detalhe.strip()[:4000])
            linhas = list(csv.DictReader(io.StringIO(resultado.stdout.decode("utf-8-sig")), delimiter="\t"))
            if not linhas:
                return {chave: [] for chave in ("text", "conf", "page_num", "block_num", "par_num", "line_num")}
            return {chave: [linha[chave] for linha in linhas] for chave in linhas[0]}
        finally:
            try:
                Path(caminho).unlink(missing_ok=True)
            except OSError:
                pass


def executar_ocr(caminho):
    if pytesseract is None:
        return "", "OCR local não instalado."
    executavel = TESSERACT_PORTATIL / "tesseract.exe"
    tessdata = TESSERACT_PORTATIL / "tessdata"
    # O executável portátil é exclusivo do Windows; no Linux usa o Tesseract local.
    if sys.platform == "win32" and executavel.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(executavel)
    configuracao = '--tessdata-dir "' + str(tessdata) + '"' if (tessdata / "por.traineddata").is_file() else ""
    candidatos = []
    try:
        with Image.open(caminho) as original:
            imagens = preparar_imagens_ocr(original)
        for imagem, modo in zip(imagens, (6, 11)):
            dados = ler_dados_tesseract(imagem, f'{configuracao} --psm {modo} --dpi 300')
            texto, confianca = ler_resultado_ocr(dados)
            if texto.strip():
                numeros_incertos = any(
                    re.search(r"\d", palavra) and 0 <= float(conf) < 70
                    for palavra, conf in zip(dados["text"], dados["conf"]))
                candidatos.append((texto, confianca, numeros_incertos))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, pytesseract.TesseractNotFoundError,
            pytesseract.TesseractError) as erro:
        if not candidatos:
            return "", f"O OCR local não pôde ler a imagem: {erro}"
        return candidatos[0][0], "Uma das leituras falhou; revise os campos antes de confirmar."
    if not candidatos:
        return "", "Nenhum texto foi reconhecido."
    texto, confianca, numeros_incertos = max(candidatos, key=lambda item: item[1])
    campos = [interpretar_texto_documento(item[0]) for item in candidatos]
    divergencia = any(len({item[chave] for item in campos}) > 1
                      for chave in ("data", "valor", "tipo"))
    if divergencia or confianca < 80 or numeros_incertos:
        return texto, "Leitura incerta: confira data, valor e tipo antes de confirmar."
    return texto, ""


def executar_ocr_motor(caminho, motor="Tesseract"):
    if motor == "Tesseract":
        return executar_ocr(caminho)
    if motor not in ("PaddleOCR", "Comparar"):
        return "", "Mecanismo de leitura desconhecido."
    texto, aviso = ocr_paddle.executar_paddleocr(caminho)
    if motor == "PaddleOCR":
        return texto, aviso
    texto_tesseract, aviso_tesseract = executar_ocr(caminho)
    if not texto:
        return texto_tesseract, aviso or "PaddleOCR indisponível; revise a leitura do Tesseract."
    campos = interpretar_texto_documento(texto)
    outros = interpretar_texto_documento(texto_tesseract)
    iguais = bool(texto_tesseract) and all(campos[k] == outros[k] and campos[k]
                                          for k in ("data", "valor", "tipo"))
    avisos_de_confianca = all(
        not item or item.startswith("Leitura incerta") for item in (aviso, aviso_tesseract))
    if iguais and avisos_de_confianca:
        # A concordância nos três campos supera a confiança genérica do OCR.
        # A confirmação ainda exige uma única correspondência no A1.
        return texto, ""
    resumo = ("Os mecanismos concordam em data, valor e tipo." if iguais else
              "Há divergência ou campos ausentes entre os mecanismos.")
    return texto, " ".join(item for item in (
        resumo, aviso, aviso_tesseract, "Revise e confirme manualmente.") if item)


class _CaptureHTTPServer(ThreadingHTTPServer):
    request_queue_size = 32
    allow_reuse_address = True
    daemon_threads = True


# Recebe a foto pelo servidor local e encaminha o conteúdo para a rotina de captura.
class _UploadHandler(BaseHTTPRequestHandler):
    server_version = "OrganizacaoCapture/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def handle(self):
        try:
            super().handle()
        except (ConnectionError, TimeoutError):
            # O telefone pode cancelar o envio ou sair da rede a qualquer momento.
            # As fotos só entram na fila após receber e validar o corpo completo.
            self.close_connection = True

    @staticmethod
    def pagina_upload(mensagem=""):
        aviso = f"<p class='aviso'>{escape(mensagem)}</p>" if mensagem else ""
        script = """
        const filaEnvios = [];
        let enviando = false;
        let confirmados = 0;
        const mensagem = document.getElementById('situacao-envio');
        const progresso = document.getElementById('progresso-envio');
        const lista = document.getElementById('lista-envios');
        function atualizarEnvios() {
          mensagem.textContent = `${confirmados} foto(s) recebida(s) no computador; ${filaEnvios.length} aguardando envio ou confirmação.`;
        }
        function enfileirarFotos(entrada) {
          for (const arquivo of Array.from(entrada.files || [])) {
            const linha = document.createElement('li');
            lista.appendChild(linha);
            if (arquivo.size === 0 || arquivo.size > 15 * 1024 * 1024) {
              linha.textContent = 'Arquivo vazio ou maior que 15 MB.';
              continue;
            }
            linha.textContent = 'Aguardando envio…';
            filaEnvios.push({arquivo, linha});
          }
          entrada.value = '';
          atualizarEnvios();
          enviarProximo();
        }
        function enviarProximo() {
          if (enviando || filaEnvios.length === 0) return;
          enviando = true;
          progresso.value = 0;
          const tarefa = filaEnvios[0];
          const xhr = new XMLHttpRequest();
          let concluida = false;
          const terminar = (recebida, aviso) => {
            if (concluida) return;
            concluida = true;
            if (recebida) { confirmados++; progresso.value = 100; }
            tarefa.linha.textContent = aviso;
            filaEnvios.shift();
            enviando = false;
            atualizarEnvios();
            enviarProximo();
          };
          xhr.open('POST', '/');
          xhr.setRequestHeader('Accept', 'application/json');
          xhr.timeout = 300000;
          xhr.upload.onprogress = (evento) => {
            if (!evento.lengthComputable) return;
            const percentual = Math.round(100 * evento.loaded / evento.total);
            progresso.value = percentual;
            tarefa.linha.textContent = percentual < 100
              ? 'Enviando — ' + percentual + '%' : 'Aguardando confirmação…';
          };
          xhr.onload = () => {
            if (xhr.status === 200) {
              let folha = '';
              try { folha = JSON.parse(xhr.responseText).folhas[0] || ''; } catch (erro) {}
              terminar(true, folha ? 'Folha ' + folha + ' — recebida.' : 'Folha recebida.');
              consultarPainel();
            } else if (xhr.status === 503) {
              terminar(false, 'o computador não conseguiu salvar. Confira o armazenamento e envie novamente.');
            } else {
              terminar(false, 'envio recusado (' + xhr.status + '). Confira o arquivo e envie novamente.');
            }
          };
          const semConfirmacao = () => terminar(false,
            'sem confirmação. Confira a fila no computador antes de reenviar.');
          xhr.onerror = semConfirmacao;
          xhr.ontimeout = semConfirmacao;
          xhr.onabort = semConfirmacao;
          const dados = new FormData();
          dados.append('documento', tarefa.arquivo, tarefa.arquivo.name);
          tarefa.linha.textContent = 'Enviando…';
          try { xhr.send(dados); } catch (erro) { semConfirmacao(); }
        }
        let paginaFolhas = 0;
        let consultandoPainel = false;
        const mapasFolhas = {pendentes: new Map(), recentes: new Map(), erros: new Map()};
        const nomesEstados = {aguardando:'Aguardando leitura', processando:'Processando agora',
          revisao:'Aguardando revisão no computador', concluida:'Concluída', descartada:'Descartada', erro:'Falha no processamento'};
        function mostrarFolhas(itens, destino, mapa) {
          const presentes = new Set(itens.map(item => item.id));
          for (const [id, cartao] of mapa) {
            if (!presentes.has(id)) { cartao.elemento.remove(); mapa.delete(id); }
          }
          itens.forEach((folha, indice) => {
            let cartao = mapa.get(folha.id);
            if (!cartao) {
              const elemento = document.createElement('article');
              const miniatura = document.createElement('div'); miniatura.className = 'miniatura';
              const texto = document.createElement('div'); texto.className = 'texto-folha';
              const numero = document.createElement('h3');
              numero.textContent = 'Folha ' + String(folha.id).padStart(4, '0');
              const estado = document.createElement('p');
              const motivo = document.createElement('p'); motivo.className = 'motivo-folha';
              const acoes = document.createElement('div'); acoes.className = 'acoes-folha';
              for (const [acao, rotulo] of [['reprocessar','Tentar novamente'],['descartar','Descartar']]) {
                const botao = document.createElement('button'); botao.type = 'button';
                botao.textContent = rotulo;
                botao.onclick = () => acaoFolha(folha.id, acao, botao);
                acoes.appendChild(botao);
              }
              texto.appendChild(numero); texto.appendChild(estado);
              texto.appendChild(motivo); texto.appendChild(acoes);
              elemento.appendChild(miniatura); elemento.appendChild(texto);
              cartao = {elemento, miniatura, estado, motivo, acoes, url:undefined};
              mapa.set(folha.id, cartao);
            }
            cartao.elemento.className = 'folha ' + folha.estado;
            cartao.estado.textContent = nomesEstados[folha.estado] || folha.estado;
            cartao.motivo.textContent = folha.motivo || '';
            cartao.motivo.hidden = !folha.motivo || folha.estado === 'concluida';
            cartao.acoes.hidden = folha.estado !== 'erro';
            if (cartao.url !== folha.previa) {
              cartao.url = folha.previa;
              cartao.miniatura.textContent = '';
              if (folha.previa) {
                const link = document.createElement('a');
                link.href = folha.previa; link.target = '_blank'; link.rel = 'noopener';
                link.title = 'Ampliar prévia temporária da folha ' + folha.id;
                const imagem = document.createElement('img');
                imagem.alt = 'Prévia da folha ' + folha.id; imagem.loading = 'lazy';
                imagem.width = 100; imagem.height = 130;
                imagem.onerror = () => { cartao.miniatura.textContent = 'Prévia indisponível'; };
                imagem.src = folha.previa;
                link.appendChild(imagem); cartao.miniatura.appendChild(link);
              } else {
                cartao.miniatura.textContent = 'Nº ' + folha.id;
              }
            }
            if (destino.children[indice] !== cartao.elemento) {
              destino.insertBefore(cartao.elemento, destino.children[indice] || null);
            }
          });
        }
        async function consultarPainel() {
          if (consultandoPainel) return;
          consultandoPainel = true;
          try {
            const resposta = await fetch('/fila?pagina=' + paginaFolhas, {cache:'no-store'});
            if (!resposta.ok) throw new Error('Fila indisponível');
            const dados = await resposta.json();
            paginaFolhas = dados.pagina;
            const totais = dados.totais;
            document.getElementById('resumo-folhas').textContent = dados.pendentes + ' pendente(s) · ' +
              (totais.erro || 0) + ' com falha · ' + (totais.concluida || 0) + ' concluída(s) · ' + (totais.descartada || 0) + ' descartada(s)';
            document.getElementById('estado-conexao').textContent = 'Atualizado automaticamente';
            document.getElementById('pagina-folhas').textContent = 'Página ' + (dados.pagina + 1) + ' de ' + dados.paginas;
            document.getElementById('folhas-anteriores').disabled = dados.pagina === 0;
            document.getElementById('folhas-proximas').disabled = dados.pagina + 1 >= dados.paginas;
            mostrarFolhas(dados.folhas, document.getElementById('folhas-pendentes'), mapasFolhas.pendentes);
            mostrarFolhas(dados.recentes, document.getElementById('folhas-recentes'), mapasFolhas.recentes);
            mostrarFolhas(dados.erros || [], document.getElementById('folhas-erros'), mapasFolhas.erros);
            document.getElementById('sem-falhas').hidden = (totais.erro || 0) > 0;
            document.getElementById('fila-vazia').hidden = dados.pendentes > 0;
          } catch (erro) {
            document.getElementById('estado-conexao').textContent = 'Sem atualização. Confira a conexão com o computador.';
          } finally {
            consultandoPainel = false;
          }
        }
        async function acaoFolha(id, acao, botao) {
          botao.disabled = true;
          const resultado = document.getElementById('resultado-acao');
          resultado.textContent = 'Atualizando folha ' + id + '...';
          try {
            const resposta = await fetch('/fila/' + id + '/' + acao, {method:'POST',headers:{Accept:'application/json'}});
            if (!resposta.ok) throw new Error(resposta.status === 409
              ? 'A folha mudou de estado ou a imagem não está disponível.' : 'Não foi possível atualizar a folha.');
            resultado.textContent = 'Folha ' + id + (acao === 'reprocessar' ? ' retornou à fila.' : ' foi descartada.');
          } catch (erro) {
            resultado.textContent = erro.message + ' Confira a conexão e atualize o painel.';
          } finally {
            botao.disabled = false;
            consultarPainel();
          }
        }
        function mudarPaginaFolhas(delta) { paginaFolhas = Math.max(0, paginaFolhas + delta); consultarPainel(); }
        consultarPainel();
        setInterval(() => { if (!document.hidden) consultarPainel(); }, 2000);
        document.addEventListener('visibilitychange', () => { if (!document.hidden) consultarPainel(); });
        """
        return f"""<!doctype html>
<html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Capturar documentos</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui, sans-serif; max-width: 560px; min-height: 100vh;
  margin: 0 auto; padding: 18px 14px; background: #f3f7fb; color: #102036; }}
main {{ background: #fbfdff; border: 1px solid #dce6ef; border-radius: 16px;
  padding: 22px; box-shadow: 0 8px 24px #10203618; }}
header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }}
.marca {{ display: grid; place-items: center; width: 42px; height: 42px;
  border-radius: 12px; background: #10b981; color: white; font-size: 1.35rem;
  font-weight: 800; }}
h1 {{ color: #102036; font-size: 1.35rem; line-height: 1.2; margin: 0; }}
.subtitulo {{ color: #586b81; font-size: .9rem; margin: 3px 0 0; }}
form {{ margin-top: 20px; }}
input[type="file"] {{ width: 100%; padding: 12px; border: 1px dashed #9fb3c7;
  border-radius: 10px; background: #f5f9fc; color: #344e69; font-size: .98rem; }}
input[type="file"]:focus-visible {{ outline: 3px solid #10b98155;
  outline-offset: 2px; border-color: #059669; }}
button {{ width: 100%; box-sizing: border-box; font-size: 1rem; padding: 12px;
  margin-top: 12px; border: 0; border-radius: 9px; background: #10b981;
  color: white; font-weight: 700; cursor: pointer; }}
button:hover {{ background: #059669; }}
button:focus-visible {{ outline: 3px solid #10b98166; outline-offset: 2px; }}
button:active {{ transform: translateY(1px); }}
.aviso {{ background: #e5f7ef; border: 1px solid #9de3c5; color: #075e46;
  padding: 11px 12px; border-radius: 10px; }}
.ajuda {{ color: #586b81; font-size: .95rem; line-height: 1.45; }}
.folha {{ display:flex; align-items:center; gap:14px; padding:12px; margin:10px 0;
  border:1px solid #dce6ef; border-radius:12px; background:#f5f9fc; }}
.folha.processando {{ border-color:#059669; border-width:2px; }}
.folha.revisao {{ border-color:#d89a22; }}
.folha.erro {{ border-color:#d43e45; }}
.motivo-folha {{ margin-top:8px !important; overflow-wrap:anywhere; max-height:130px; overflow:auto; }}
.acoes-folha button {{ font-size:.85rem; padding:8px; margin-top:8px; }}
.acoes-folha[hidden] {{ display:none; }}
.miniatura {{ width:100px; min-width:100px; height:130px; display:flex; align-items:center;
  justify-content:center; background:#e5edf5; border-radius:6px; overflow:hidden;
  font-size:1.2rem; font-weight:700; color:#344e69; text-align:center; }}
.miniatura img {{ display:block; width:100px; height:130px; object-fit:contain; }}
.texto-folha h3 {{ margin:0 0 8px; font-size:1.05rem; }}
.texto-folha p {{ margin:0; font-size:.92rem; }}
.paginacao {{ display:flex; align-items:center; justify-content:space-between; gap:10px; }}
.paginacao button {{ width:auto; margin:0; padding:8px 12px; }}
button:disabled {{ opacity:.45; cursor:default; }}
@media (prefers-color-scheme: dark) {{
  body {{ background: #06121e; color: #f0f6fc; }}
  main {{ background: #0b1c2b; border-color: #183143; }}
  h1 {{ color: #f0f6fc; }}
  .subtitulo, .ajuda {{ color: #acbfd1; }}
  input[type="file"] {{ background: #152c3d; border-color: #416076; color: #f0f6fc; }}
  .aviso {{ background: #123b32; border-color: #167653; color: #b7f5d9; }}
  .folha {{ background:#102638; border-color:#294257; }}
  .folha.processando {{ border-color:#10b981; }}
  .folha.revisao {{ border-color:#d89a22; }}
  .miniatura {{ background:#1b354a; color:#e0edf7; }}
}}
</style><body><main>
<header><div class="marca" aria-hidden="true">+</div><div>
<h1>Enviar documentos</h1>
<p class="subtitulo">Captura local pelo telefone</p>
</div></header>
<p class="ajuda">Escolha uma ou várias fotos. Depois do envio, esta página
continua pronta para adicionar mais arquivos.</p>
{aviso}
<form method="post" enctype="multipart/form-data">
<input type="file" name="documento" accept="image/*" capture="environment"
 multiple required onchange="enfileirarFotos(this)">
<p class="ajuda">Depois de tirar ou escolher a foto, o envio começa
automaticamente. Você pode selecionar mais fotos enquanto o envio está em andamento.
Mantenha esta página aberta até a confirmação.</p>
</form>
<p id="situacao-envio" role="status" aria-live="polite">Pronto para receber fotos.</p>
<progress id="progresso-envio" max="100" value="0" aria-label="Progresso do envio" style="width:100%"></progress>
<ul id="lista-envios" style="overflow-wrap:anywhere"></ul>
<section aria-labelledby="titulo-fila">
<h2 id="titulo-fila">Suas folhas</h2>
<p id="resumo-folhas" role="status">Consultando a fila do computador...</p>
<p id="estado-conexao" class="subtitulo"></p>
<h3>Na fila</h3><p id="fila-vazia" hidden>Nenhuma folha pendente.</p>
<div id="folhas-pendentes"></div>
<nav class="paginacao" aria-label="Páginas da fila">
<button type="button" id="folhas-anteriores" onclick="mudarPaginaFolhas(-1)" disabled>Anterior</button>
<span id="pagina-folhas"></span>
<button type="button" id="folhas-proximas" onclick="mudarPaginaFolhas(1)" disabled>Próxima</button>
</nav>
<h3>Falhas no processamento</h3>
<p id="sem-falhas">Nenhuma falha registrada.</p>
<div id="folhas-erros"></div><p id="resultado-acao" role="status" aria-live="polite"></p>
<h3>Últimas folhas finalizadas</h3><div id="folhas-recentes"></div>
<p class="ajuda">A prévia é temporária: ao concluir ou descartar, a imagem sai e o número da folha permanece. Fotos com falha ficam preservadas para tentar novamente. Toque na miniatura para ampliar.</p>
</section>
<script>{script}</script>
</main></body></html>"""

    def responder(self, dados, tipo, status=200):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        endereco = urlsplit(self.path)
        if endereco.path == "/":
            self.responder(self.pagina_upload().encode("utf-8"), "text/html; charset=utf-8")
            return
        fila = getattr(self.server, 'fila_ocr', None)
        if fila is None:
            self.send_error(404)
            return
        try:
            if endereco.path == '/fila':
                try:
                    pagina = int(parse_qs(endereco.query).get('pagina', ['0'])[0])
                except ValueError:
                    self.send_error(400)
                    return
                dados = json.dumps(fila.painel(pagina), ensure_ascii=False).encode('utf-8')
                self.responder(dados, 'application/json; charset=utf-8')
                return
            foto = re.fullmatch(r'/fila/([1-9][0-9]{0,17})/previa', endereco.path)
            if foto:
                dados = fila.previa(int(foto.group(1)))
                if dados is None:
                    self.send_error(410, "Previa indisponivel ou folha finalizada")
                else:
                    self.responder(dados, 'image/jpeg')
                return
        except (OSError, sqlite3.Error):
            self.send_error(503, "Fila temporariamente indisponivel")
            return
        self.send_error(404)

    def do_POST(self):
        acao = re.fullmatch(r'/fila/([1-9][0-9]{0,17})/(reprocessar|descartar)', urlsplit(self.path).path)
        if acao:
            fila = getattr(self.server, 'fila_ocr', None)
            if fila is None:
                self.send_error(404)
                return
            try:
                metodo = fila.reprocessar if acao.group(2) == 'reprocessar' else fila.descartar_erro
                alterou = metodo(int(acao.group(1)))
            except (OSError, sqlite3.Error):
                self.send_error(503, "Nao foi possivel atualizar a folha")
                return
            self.responder(json.dumps(dict(ok=alterou)).encode('utf-8'), 'application/json', 200 if alterou else 409)
            return
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Tamanho de arquivo inválido")
            return
        if tamanho <= 0 or tamanho > 16 * 1024 * 1024:
            self.send_error(413, "Arquivo vazio ou maior que 15 MB")
            return
        corpo = self.rfile.read(tamanho)
        if len(corpo) != tamanho:
            self.send_error(400, "Envio incompleto. Envie a foto novamente.")
            return
        limite = self.headers.get("Content-Type", "")
        correspondencia = re.search(r'boundary="?([^";]+)', limite)
        if correspondencia is None:
            self.send_error(400, "Envio multipart inválido")
            return
        separador = ("--" + correspondencia.group(1)).encode()
        if not corpo.rstrip(b"\r\n").endswith(separador + b"--"):
            self.send_error(400, "Envio incompleto. Envie a foto novamente.")
            return
        partes = corpo.split(separador)
        arquivos = []
        for parte in partes:
            if b'name="documento"' not in parte:
                continue
            cabecalho, _, conteudo = parte.partition(b"\r\n\r\n")
            nome = re.search(br'filename="([^"]*)"', cabecalho)
            if nome is None:
                continue
            if conteudo.endswith(b"\r\n"):
                conteudo = conteudo[:-2]
            extensao = Path(nome.group(1).decode("utf-8", "ignore")).suffix.lower()
            if extensao not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"):
                self.send_error(415, "Formato de imagem não aceito")
                return
            if not conteudo or len(conteudo) > 15 * 1024 * 1024:
                self.send_error(413, "Arquivo vazio ou maior que 15 MB")
                return
            arquivos.append((conteudo, extensao))
        if not arquivos:
            self.send_error(400, "Nenhuma imagem foi enviada")
            return
        try:
            lote = getattr(self.server, "captura_lote_callback", None)
            if lote is not None:
                identificadores = lote(arquivos)
            else:
                identificadores = [self.server.captura_callback(conteudo, extensao)
                                   for conteudo, extensao in arquivos]
            if not isinstance(identificadores, (list, tuple)):
                identificadores = []
            identificadores = [item for item in identificadores if isinstance(item, int)]
        except Exception:
            self.send_error(503, "Nao foi possivel salvar na fila local. Tente novamente.")
            return
        if 'application/json' in self.headers.get('Accept', ''):
            dados = json.dumps(dict(folhas=identificadores, recebidas=len(arquivos))).encode('utf-8')
            self.responder(dados, 'application/json; charset=utf-8')
        else:
            dados = self.pagina_upload(
                f"{len(arquivos)} foto(s) recebida(s). Você pode selecionar e enviar mais.").encode("utf-8")
            self.responder(dados, "text/html; charset=utf-8")

    def log_message(self, *_):
        return


def endereco_rede_local():
    conexao = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        conexao.connect(("192.0.2.1", 1))
        return conexao.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        conexao.close()


def extrair_numero(linha):
    try:
        if linha.startswith("["):
            return int(linha[1:linha.index("]")])
    except (ValueError, IndexError):
        pass
    return 999999


def extrair_texto_registro(item):
    if item.startswith("["):
        try:
            return item[item.index("]") + 1:].strip()
        except ValueError:
            pass
    return item


def obter_destino_ordenado():
    return sorted(carregar_linhas(ARQUIVO_DESTINO), key=extrair_numero)


def extrair_lancamento(texto):
    """Retorna (D/C, valor) do primeiro lançamento em formato brasileiro."""
    encontrado = re.search(
        r"(?<![0-9.,+\-])[+\-]?([0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)"
        r"(,[0-9]{1,2})?\s*([DC])\b", texto.strip().upper()
    )
    if encontrado is None:
        return None
    inteiro, centavos, tipo = encontrado.groups()
    valor = Decimal(inteiro.replace(".", "") + (centavos or "").replace(",", "."))
    return tipo, valor


def extrair_valor_debito(texto):
    lancamento = extrair_lancamento(texto)
    return lancamento[1] if lancamento is not None and lancamento[0] == "D" else None


# Resolve as referências do A2 antes de aplicar filtros de exibição.
def referencias_no_destino(origem, destino):
    """Reconhece referências que apontam para a mesma linha do A1."""
    textos = {numero: " ".join(texto.split()) for numero, texto in origem}
    conferidos = set()
    for item in destino:
        referencia = re.fullmatch(r"\[(\d+)\]\s*(.*)", item)
        if referencia is not None:
            numero = int(referencia[1])
            if textos.get(numero) == " ".join(referencia[2].split()):
                conferidos.add(numero)
    return conferidos


def texto_a2_sem_referencia(item):
    referencia = re.fullmatch(r"\[\d+\]\s*(.*)", item)
    return referencia[1] if referencia is not None else item


def carregar_lancamentos_origem():
    """Ignora saldos e resumos do extrato, mantendo as linhas originais."""
    origem = carregar_origem_numerada()
    extrato = any(texto.upper() == "LANÇAMENTOS" for _, texto in origem)
    secao = None
    resultado = []
    for numero, texto in origem:
        titulo = texto.upper()
        if extrato:
            if titulo in ("LANÇAMENTOS", "LANÇAMENTOS FUTUROS", "RESUMO"):
                secao = titulo
            if secao not in ("LANÇAMENTOS", "LANÇAMENTOS FUTUROS"):
                continue
            if not re.match(r"^\d{2}/\d{2}/\d{4}\s", texto):
                continue
        if re.match(r"^(?:\d{2}/\d{2}/\d{4}\s+)?SALDO "
                    r"(?:DO DIA|ANTERIOR|BLOQUEADO ANTERIOR)(?:\s|$)", titulo):
            continue
        valor = extrair_lancamento(texto)
        if valor is not None:
            resultado.append((numero, texto, valor))
    return resultado


def corresponde(termo, texto):
    """Busca normal + busca numérica tolerante.

    1453,30 / 1.453,30 / 145330 encontram qualquer valor 1.453,30.
    """
    t = termo.strip().lower()
    if not t:
        return True
    if t in texto.lower():
        return True
    if re.fullmatch(r"[\d\.,\s]+", t):
        digitos = re.sub(r"\D", "", t)
        if digitos:
            for token in re.findall(r"\d[\d\.,]*", texto):
                if digitos in re.sub(r"\D", "", token):
                    return True
    return False


def calcular_lancamentos(tipo=None, termo=""):
    """Confere ocorrências de linhas iguais entre A1 e A2."""
    itens_a2 = carregar_linhas(ARQUIVO_DESTINO)
    origem = carregar_lancamentos_origem()
    linhas_a2 = Counter(" ".join(texto_a2_sem_referencia(item).split())
                        for item in itens_a2)

    resultado = []
    for numero, texto, _ in origem:
        chave = " ".join(texto.split())
        ok = linhas_a2[chave] > 0
        if ok:
            linhas_a2[chave] -= 1
        resultado.append((numero, texto, ok))
    # A busca acontece após a conferência completa, para não redistribuir
    # ocorrências de mesmo valor quando apenas parte da lista está visível.
    resultado = [(n, texto, ok) for n, texto, ok in resultado
                 if (tipo is None or extrair_lancamento(texto)[0] == tipo)
                 and corresponde(termo, texto)]
    return resultado, len(resultado), sum(not ok for _, _, ok in resultado)


def calcular_debitos():
    return calcular_lancamentos("D")


def gerar_relatorio_html(tipo=None, termo="", abrir=True):
    resultado, total, faltando = calcular_lancamentos(tipo, termo)
    categoria = {None: "Débitos e Créditos", "D": "Débitos", "C": "Créditos"}[tipo]
    linhas = ""
    for ordem, (numero, texto, ok) in enumerate(resultado, start=1):
        texto = escape(texto)
        if ok:
            linhas += (f'<tr><td>{ordem}</td><td style="text-align:center;">{numero}</td><td>{texto}</td>'
                       f'<td style="text-align:center;"><span class="ok">OK</span></td></tr>')
        else:
            linhas += (f'<tr style="color:red;font-weight:bold;"><td>{ordem}</td><td style="text-align:center;">{numero}</td>'
                       f'<td>{texto}</td><td style="text-align:center;"><span class="falta">FALTA NO A2</span></td></tr>')

    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<title>Comparação de {categoria} - A1 x A2</title>
<style>
@page {{ size: A4 portrait; margin: 8mm; }}
body {{ font-family: Arial, sans-serif; margin: 12px auto; padding: 0 12px; max-width: 1100px; color: #222; }}
h2 {{ font-size: 18px; line-height: 1.2; margin: 0 0 6px; }}
.metadados {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 16px;
  margin-bottom: 8px; font-size: 11px; }}
table {{ width: 100%; table-layout: fixed; border-collapse: collapse; margin: 0; }}
col.numero {{ width: 10mm; }}
col.referencia {{ width: 14mm; }}
col.situacao {{ width: 27mm; }}
th, td {{ border: 1px solid #bbb; padding: 3px 5px; font-size: 12px; line-height: 1.2; vertical-align: top; }}
th {{ background-color: #f1f1f1; }}
td:nth-child(1), td:nth-child(2), td:nth-child(4) {{ text-align: center; white-space: nowrap; }}
td:nth-child(3) {{ white-space: normal; overflow-wrap: anywhere; }}
thead {{ display: table-header-group; }}
tr {{ break-inside: avoid; page-break-inside: avoid; }}
.resumo {{ margin: 6px 0 0; font-size: 11px; }}
.ok {{ color: green; font-weight: bold; }}
.falta {{ color: red; font-weight: bold; }}
@media print {{
  body {{ margin: 0; padding: 0; max-width: none; }}
  h2 {{ font-size: 11pt; margin: 0 0 2mm; }}
  .metadados {{ font-size: 8pt; margin-bottom: 2mm; }}
  th, td {{ font-size: 9pt; line-height: 1.15; padding: 1mm 1.2mm; }}
  .resumo {{ font-size: 8pt; }}
  .nao-imprimir {{ display: none; }}
}}
</style></head><body>
<h2>Relatório de Comparação de {categoria}: A1 x A2</h2>
<div class="metadados"><span>Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</span>
<span>Pesquisa: {escape(termo.strip()) or 'Todos os registros'}</span></div>
<table><colgroup><col class="numero"><col class="referencia"><col><col class="situacao"></colgroup><thead><tr>
<th>Nº</th><th>Linha A1</th><th>Registro</th><th>Situação</th>
</tr></thead><tbody>{linhas}</tbody></table>
<p class="resumo"><b>Lançamentos no A1:</b> {total} | <b>Faltando no A2:</b> {faltando}</p>
<div class="nao-imprimir" style="text-align:center;margin-top:30px;">
<button onclick="window.print();" style="padding:10px 20px;font-size:16px;cursor:pointer;background:#007BFF;color:#fff;border:none;border-radius:5px;">Imprimir Relatório</button>
</div></body></html>"""

    os.makedirs(PASTA_REG, exist_ok=True)
    caminho = os.path.join(PASTA_REG, "relatorio_debitos.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)
    if abrir:
        abrir_arquivo_relatorio(caminho)
    return caminho


def abrir_arquivo_relatorio(caminho):
    arquivo = Path(caminho).resolve()
    if sys.platform == "win32":
        try:
            # ShellExecute recebe o caminho Unicode nativo, sem converter nomes
            # com espaços e acentos em uma URL file:// codificada.
            os.startfile(str(arquivo))
            return True
        except (OSError, AttributeError):
            pass
    try:
        return bool(webbrowser.open(arquivo.as_uri(), new=2))
    except (OSError, webbrowser.Error):
        return False



# INTERFACE

FONTE = "Segoe UI"


def formatar_valor_registro(texto):
    lancamento = extrair_lancamento(texto)
    if lancamento is None:
        return ""
    tipo, valor = lancamento
    numero = f"{valor:,.2f}".translate(str.maketrans({",": ".", ".": ","}))
    return f"{numero} {tipo}"


def icone(nome, cor="cabecalho", tamanho=18):
    """Ícones vetoriais, sem depender de símbolos disponíveis na fonte do PC."""
    def desenhar(modo):
        imagem = Image.new("RGBA", (96, 96))
        d = ImageDraw.Draw(imagem)
        tinta = cm(cor, modo) if cor in TEMAS else cor
        linha = 7
        if nome == "arquivo":
            d.line([(25, 12), (57, 12), (74, 29), (74, 84), (25, 84), (25, 12)], fill=tinta, width=linha)
            d.line([(55, 13), (55, 32), (74, 32)], fill=tinta, width=5)
            for y in (46, 59, 72):
                d.line((37, y, 62, y), fill=tinta, width=5)
        elif nome in ("confirmado", "alerta"):
            d.ellipse((6, 6, 90, 90), fill=tinta)
            if nome == "confirmado":
                d.line([(28, 48), (43, 62), (69, 32)], fill="white", width=9)
            else:
                d.line((48, 24, 48, 56), fill="white", width=9)
                d.ellipse((43, 66, 53, 76), fill="white")
        elif nome == "atencao":
            d.polygon([(48, 7), (92, 85), (4, 85)], fill=tinta)
            d.line((48, 32, 48, 57), fill=cm("painel", modo), width=8)
            d.ellipse((44, 66, 52, 74), fill=cm("painel", modo))
        elif nome == "busca":
            d.ellipse((13, 10, 65, 62), outline=tinta, width=linha)
            d.line((59, 57, 84, 82), fill=tinta, width=linha)
        elif nome == "captura":
            d.line((48, 10, 48, 64), fill=tinta, width=linha)
            d.line([(26, 44), (48, 66), (70, 44)], fill=tinta, width=linha)
            d.line([(16, 70), (16, 84), (80, 84), (80, 70)], fill=tinta, width=linha)
        elif nome == "adicionar":
            d.ellipse((9, 9, 87, 87), outline=tinta, width=linha)
            d.line((48, 28, 48, 68), fill=tinta, width=linha)
            d.line((28, 48, 68, 48), fill=tinta, width=linha)
        elif nome == "atualizar":
            d.arc((12, 12, 84, 84), 35, 310, fill=tinta, width=linha)
            d.polygon([(79, 11), (84, 42), (56, 33)], fill=tinta)
        elif nome == "aparencia":
            for xy in ((38, 3, 58, 93), (3, 38, 93, 58)):
                d.rounded_rectangle(xy, radius=5, fill=tinta)
            d.line((16, 16, 80, 80), fill=tinta, width=18)
            d.line((80, 16, 16, 80), fill=tinta, width=18)
            d.ellipse((17, 17, 79, 79), fill=tinta)
            d.ellipse((34, 34, 62, 62), fill=cm("campo", modo))
        return imagem
    return ctk.CTkImage(light_image=desenhar("Claro"), dark_image=desenhar("Escuro"),
                        size=(tamanho, tamanho))


def estilizar_tabelas(modo, acento, escala=1):
    st = ttk.Style()
    st.theme_use("clam")
    st.configure("Treeview", background=cm("painel", modo),
                 fieldbackground=cm("painel", modo), foreground=cm("texto", modo),
                 rowheight=round(27 * escala), borderwidth=0, font=(FONTE, -round(13 * escala)))
    st.configure("Treeview.Heading", background=cm("grade_cabecalho", modo),
                 foreground=cm("cabecalho", modo), relief="flat", borderwidth=0,
                 padding=(round(6 * escala), round(5 * escala)), font=(FONTE, -round(12 * escala), "bold"))
    st.map("Treeview", background=[("selected", cm("selecao", modo))], foreground=[])
    st.map("Origem.Treeview", background=[("selected", "#087cfa")],
           foreground=[("selected", "#ffffff")])
    st.map("Treeview.Heading", background=[("active", cm("grade_cabecalho", modo))])
    st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])


class AbasCompactas(ctk.CTkFrame):
    """Conteúdo expansível, com navegação no cabeçalho da janela."""

    def __init__(self, pai, selecao):
        super().__init__(pai, fg_color="transparent", corner_radius=0)
        self.selecao = selecao
        self.paineis = {}
        self.atual = None
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def add(self, nome):
        painel = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.paineis[nome] = painel
        if self.atual is None:
            self.set(nome)
        return painel

    def get(self):
        return self.atual

    def set(self, nome):
        if self.atual is not None:
            self.paineis[self.atual].grid_remove()
        self.atual = nome
        self.selecao.set(nome)
        self.paineis[nome].grid(row=0, column=0, sticky="nsew")


class App(ctk.CTk):
    def __init__(self):
        global FONTE
        # Sem a fonte de formas, o fallback por círculos deixa sobras nas
        # bordas dos controles. Polígonos dispensam essa fonte e evitam as sobras.
        if ctk.DrawEngine.preferred_drawing_method == "circle_shapes":
            ctk.DrawEngine.preferred_drawing_method = "polygon_shapes"
        super().__init__()
        if FONTE not in tkfont.families(self):
            FONTE = tkfont.nametofont("TkDefaultFont", root=self).actual("family")
        self.modo, self.acento = carregar_config()
        ctk.set_appearance_mode("dark" if self.modo == "Escuro" else "light")
        self.primarios = []  # botões que usam a cor de destaque
        self.resultados = []
        self.termo_busca = ""
        self._sincronizando_selecao = False
        self.servidor_captura = None
        self.thread_servidor_captura = None
        self.captura_pendente = None
        self.capturas_adicionadas = set()
        erro_atencao = None
        try:
            self.atencoes = carregar_atencoes()
        except (OSError, ValueError) as erro:
            self.atencoes = set()
            erro_atencao = str(erro)

        self.title("Sistema de Busca e Ordenação")
        largura = max(960, min(1360, self._reverse_window_scaling(self.winfo_screenwidth()) - 40))
        altura = max(560, min(820, self._reverse_window_scaling(self.winfo_screenheight()) - 100))
        self.geometry(f"{largura}x{altura}")
        self.minsize(960, 560)
        self.configure(fg_color=c("bg"))

        self.status = tk.StringVar(value="Pronto.")
        self.rodape_global = ctk.CTkFrame(self, height=24, corner_radius=0,
                                                       fg_color=c("superficie"), border_width=1, border_color=c("borda"))
        self.rodape_global.pack(side="bottom", fill="x", pady=(2, 0))
        self.rodape_global.pack_propagate(False)
        self.contadores = tk.StringVar()
        ctk.CTkLabel(self.rodape_global, textvariable=self.contadores, height=24,
                     text_color=c("cinza"), font=(FONTE, 11)).pack(side="left", padx=12)
        self.status_visivel = tk.StringVar()
        self.label_status = ctk.CTkLabel(self.rodape_global, textvariable=self.status_visivel,
                                        height=24, anchor="e", text_color=c("cinza"), font=(FONTE, 11))
        self.ponto_status = ctk.CTkLabel(self.rodape_global, text="●", width=14, height=24,
                                               text_color=c("verde"), font=(FONTE, 12))
        self.ponto_status.pack(side="right", padx=(0, 8))
        self.label_status.pack(side="right", fill="x", expand=True, padx=(12, 4))
        self.label_status.bind("<Configure>", self.ajustar_status)
        self.label_status.configure(cursor="hand2")
        self.label_status.bind("<Button-1>", lambda evento: messagebox.showinfo(
            "Status", self.status.get(), parent=self))
        self.status.trace_add("write", self.ajustar_status)

        self._montar_cabecalho()
        self.abas = AbasCompactas(self.corpo, self.aba_selecionada)
        self.abas.pack(fill="both", expand=True, padx=(76, 12), pady=(10, 0))
        self.aba_busca = self.abas.add("Buscar e comparar")
        self.aba_a2 = self.abas.add("Lista A2")
        self.aba_captura = self.abas.add("Capturar documento")
        self.aba_a2.configure(fg_color=c("painel"), border_width=1, border_color=c("borda"), corner_radius=6)
        self.aba_captura.configure(fg_color=c("painel"), border_width=1, border_color=c("borda"), corner_radius=6)

        self._montar_aba_busca()
        self._montar_aba_a2()
        self._montar_aba_captura()
        self._montar_aba_debitos()
        self.aplicar_tema()
        self.abas.bind("<Configure>", self.ajustar_escala_tabelas, add="+")
        self.atualizar_tudo()
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        if erro_atencao:
            self.status.set("Não foi possível carregar as marcações de atenção: " + erro_atencao)

    def fechar(self):
        self.encerrando = True
        self.salvar_revisao_captura()
        self.parar_servidor_captura()
        self.executor_ocr.fechar()
        if self.thread_ocr is not None:
            self.thread_ocr.join(timeout=2)
        self.fila_ocr.fechar()
        self.destroy()

    def report_callback_exception(self, exc, valor, traceback):
        """Apresenta erros de arquivo sem deixar a ação falhar silenciosamente."""
        if issubclass(exc, (OSError, UnicodeError)):
            self.status.set("Não foi possível concluir a operação com os arquivos.")
            messagebox.showerror("Erro ao acessar arquivos", str(valor), parent=self)
        else:
            super().report_callback_exception(exc, valor, traceback)

    def ajustar_status(self, *args):
        # Mensagens extensas continuam completas em self.status, sem aumentar o rodapé.
        fonte = tkfont.Font(root=self, font=self.label_status._label.cget("font"))
        largura = max(0, self.label_status.winfo_width() - 4)
        mensagem = " ".join(self.status.get().splitlines())
        if fonte.measure(mensagem) > largura:
            while mensagem and fonte.measure(mensagem + "…") > largura:
                mensagem = mensagem[:-1]
            mensagem += "…"
        self.status_visivel.set(mensagem)

    #  componentes reutilizáveis 
    def botao(self, pai, texto, comando, primario=False, perigo=False, largura=140, altura=30):
        if perigo:
            kw = dict(fg_color=c("perigo"), hover_color=c("perigo_hover"),
                      text_color=c("vermelho"))
        elif primario:
            kw = dict(fg_color=ACENTOS[self.acento][0],
                      hover_color=ACENTOS[self.acento][1], text_color="#ffffff")
        else:
            kw = dict(fg_color=c("campo"), hover_color=c("campo_hover"),
                      text_color=c("texto"))
        simbolo = {"Aparência": "aparencia", "Adicionar ao A2": "adicionar",
                   "Atualizar": "atualizar", "Relatório": "arquivo",
                   "Backup da sessão": "arquivo"}.get(texto)
        imagem = icone(simbolo, "#ffffff" if primario else "cabecalho", 16) if simbolo else None
        b = ctk.CTkButton(pai, text=texto, image=imagem, command=comando, width=largura, height=altura,
                          corner_radius=5, border_width=0 if primario else 1, border_color=c("borda"),
                          font=(FONTE, 12, "bold"), **kw)
        if primario:
            self.primarios.append(b)
        return b

    def campo(self, pai, var, placeholder, largura=380):
        return ctk.CTkEntry(pai, textvariable=var, height=34, width=largura,
                            corner_radius=5, border_width=0, fg_color=c("campo"),
                            text_color=c("texto"), placeholder_text=placeholder,
                            placeholder_text_color=c("cinza"), font=(FONTE, 13))

    @staticmethod
    def _tabela(pai, colunas, larguras):
        frame = ctk.CTkFrame(pai, fg_color="transparent", corner_radius=0)
        tree = ttk.Treeview(frame, columns=[c_[0] for c_ in colunas],
                            show="headings", selectmode="extended", style="Origem.Treeview")
        tree.larguras_fixas = {cid: larg for (cid, _), larg in zip(colunas, larguras) if larg}
        escala = pai._apply_widget_scaling(1)
        for (cid, titulo), larg in zip(colunas, larguras):
            alin = "w" if cid == "texto" else "e" if cid == "valor" else "center"
            tree.heading(cid, text=titulo, anchor=alin)
            tree.column(cid, width=round((larg or 300) * escala), minwidth=round((larg or 140) * escala),
                        stretch=(larg == 0), anchor=alin)
        tree.column("texto", minwidth=140)
        sb = ctk.CTkScrollbar(frame, command=tree.yview)
        horizontal = ctk.CTkScrollbar(frame, orientation="horizontal", command=tree.xview)
        def atualizar_barra(barra, inicio, fim):
            barra.set(inicio, fim)
            necessaria = float(inicio) > 0 or float(fim) < 1
            if necessaria and not barra.winfo_manager():
                barra.grid()
            elif not necessaria and barra.winfo_manager():
                barra.grid_remove()

        tree.configure(yscrollcommand=lambda inicio, fim: atualizar_barra(sb, inicio, fim),
                       xscrollcommand=lambda inicio, fim: atualizar_barra(horizontal, inicio, fim))
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        horizontal.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        return frame, tree

    @staticmethod
    def ajustar_largura_registro(tree):
        """Mantém o registro inteiro acessível pela rolagem horizontal."""
        fonte = tkfont.Font(root=tree, font=ttk.Style(tree).lookup("Treeview", "font"))
        largura = max((fonte.measure(tree.set(iid, "texto")) + 32
                       for iid in tree.get_children()), default=140)
        tree.column("texto", width=max(140, largura), minwidth=max(140, largura))

    def _montar_cabecalho(self):
        # O menu se sobrepõe ao conteúdo ao abrir; as tabelas não mudam de lugar.
        self.corpo = ctk.CTkFrame(self, fg_color="transparent")
        self.corpo.pack(fill="both", expand=True)
        self.aba_selecionada = tk.StringVar(value="Buscar e comparar")
        self.menu_expandido = False
        self._recolher_menu_id = None
        self.cabecalho = ctk.CTkFrame(self.corpo, width=64, corner_radius=0,
                                    fg_color=c("superficie"), border_width=1, border_color=c("borda"))
        self.cabecalho.place(x=0, y=0, relheight=1)
        self.titulo_cabecalho = ctk.CTkLabel(
            self.cabecalho, text="", image=icone("arquivo", tamanho=26), compound="left",
            anchor="w", font=(FONTE, 17, "bold"), height=54)
        self.titulo_cabecalho.pack(fill="x", padx=18, pady=(8, 14))
        self.botoes_menu = {}
        for nome, simbolo in (("Buscar e comparar", "busca"), ("Lista A2", "arquivo"), ("Captura", "captura")):
            botao = ctk.CTkButton(
                self.cabecalho, text="", image=icone(simbolo, tamanho=22), anchor="w",
                width=44, height=42, corner_radius=5, border_spacing=10,
                font=(FONTE, 13, "bold"), text_color=c("texto"),
                fg_color="transparent", hover_color=c("campo_hover"),
                command=lambda aba=nome: self.trocar_aba(aba))
            botao.pack(fill="x", padx=8, pady=4)
            self.botoes_menu[nome] = botao
        self.botao_aparencia = ctk.CTkButton(
            self.cabecalho, text="", image=icone("aparencia", tamanho=22), anchor="w",
            width=44, height=42, border_spacing=10, fg_color="transparent",
            hover_color=c("campo_hover"), text_color=c("texto"),
            font=(FONTE, 13, "bold"), command=self.alternar_aparencia)
        self.botao_aparencia.pack(side="bottom", fill="x", padx=8, pady=12)
        self.painel_aparencia = ctk.CTkFrame(self.corpo, width=240, height=126,
                                           fg_color=c("painel"), border_width=1, border_color=c("borda"))
        ctk.CTkLabel(self.painel_aparencia, text="Tema:", font=(FONTE, 12)).grid(row=0, column=0, padx=12, pady=12)
        self.seg_tema = ctk.CTkSegmentedButton(
            self.painel_aparencia, values=["Escuro", "Claro"], command=self.mudar_tema,
            height=30, font=(FONTE, 12, "bold"), fg_color=c("campo"),
            unselected_color=c("campo"), unselected_hover_color=c("campo_hover"),
            text_color=("#111827", "#ffffff"))
        self.seg_tema.set(self.modo)
        self.seg_tema.grid(row=0, column=1, padx=(0, 12), pady=12)
        ctk.CTkLabel(self.painel_aparencia, text="Cor:", font=(FONTE, 12)).grid(row=1, column=0, padx=12, pady=(0, 12))
        self.opt_acento = ctk.CTkOptionMenu(
            self.painel_aparencia, values=list(ACENTOS), command=self.mudar_acento,
            width=146, height=30, font=(FONTE, 12), dropdown_font=(FONTE, 12),
            fg_color=c("campo"), button_color=c("campo_hover"), text_color=c("texto"),
            dropdown_fg_color=c("painel"), dropdown_text_color=c("texto"))
        self.opt_acento.set(self.acento)
        self.opt_acento.grid(row=1, column=1, padx=(0, 12), pady=(0, 12))
        self.bind("<Motion>", self._acompanhar_menu, add="+")
        self.bind("<Leave>", self._acompanhar_menu, add="+")
        self.bind("<FocusIn>", self._foco_menu, add="+")

    def _foco_menu(self, evento):
        if str(evento.widget).startswith(str(self.cabecalho) + "."):
            self.expandir_menu()

    def expandir_menu(self):
        if self._recolher_menu_id is not None:
            self.after_cancel(self._recolher_menu_id)
            self._recolher_menu_id = None
        self._definir_menu(True)

    def _definir_menu(self, expandido):
        if self.menu_expandido == expandido:
            return
        self.menu_expandido = expandido
        self.cabecalho.configure(width=236 if expandido else 64)
        self.titulo_cabecalho.configure(text="  Busca e Ordenação" if expandido else "")
        for nome, botao in self.botoes_menu.items():
            botao.configure(text="  " + nome if expandido else "")
        self.botao_aparencia.configure(text="  Aparência" if expandido else "")
        self.cabecalho.lift()

    def _acompanhar_menu(self, evento=None):
        x, y = self.winfo_pointerxy()
        dentro = (self.cabecalho.winfo_rootx() <= x < self.cabecalho.winfo_rootx() + self.cabecalho.winfo_width()
                  and self.cabecalho.winfo_rooty() <= y < self.cabecalho.winfo_rooty() + self.cabecalho.winfo_height())
        if dentro:
            self.expandir_menu()
        elif self.menu_expandido and self._recolher_menu_id is None:
            self._recolher_menu_id = self.after(250, self.recolher_menu)

    def recolher_menu(self):
        self._recolher_menu_id = None
        if not self.painel_aparencia.winfo_manager():
            self._definir_menu(False)

    def _atualizar_menu(self):
        normal, hover = ACENTOS[self.acento]
        for nome, botao in self.botoes_menu.items():
            ativo = nome == self.aba_selecionada.get()
            botao.configure(fg_color=normal if ativo else "transparent",
                            hover_color=hover if ativo else c("campo_hover"))

    def trocar_aba(self, nome):
        self.abas.set("Capturar documento" if nome == "Captura" else nome)
        self.aba_selecionada.set(nome)
        self._atualizar_menu()
        self.atualizar_tudo()

    def alternar_aparencia(self):
        if self.painel_aparencia.winfo_manager():
            self.painel_aparencia.place_forget()
            self._acompanhar_menu()
        else:
            self.expandir_menu()
            self.painel_aparencia.place(x=242, rely=1, y=-12, anchor="sw")
            self.painel_aparencia.lift()

    def iniciar_servidor_captura(self):
        if (self.servidor_captura is not None
                and self.thread_servidor_captura is not None
                and self.thread_servidor_captura.is_alive()):
            self.status.set("A captura já está disponível no endereço mostrado.")
            return
        if self.servidor_captura is not None:
            self.servidor_captura.server_close()
            self.servidor_captura = None
            self.thread_servidor_captura = None
        try:
            servidor = _CaptureHTTPServer(("0.0.0.0", 0), _UploadHandler)
        except OSError as erro:
            self.status.set("Não foi possível iniciar o servidor de captura.")
            messagebox.showerror("Servidor de captura", str(erro), parent=self)
            return
        servidor.captura_callback = self.fila_ocr.adicionar
        servidor.captura_lote_callback = self.fila_ocr.adicionar_lote
        servidor.fila_ocr = self.fila_ocr
        self.servidor_captura = servidor
        self.thread_servidor_captura = threading.Thread(
            target=servidor.serve_forever, daemon=True)
        self.thread_servidor_captura.start()
        endereco = f"http://{endereco_rede_local()}:{servidor.server_port}"
        self.url_captura.set(endereco)
        self._mostrar_qr(endereco)
        self.status.set("Servidor local ativo. Abra o endereço no telefone e envie uma foto.")

    def parar_servidor_captura(self):
        if self.servidor_captura is not None:
            self.servidor_captura.shutdown()
            self.servidor_captura.server_close()
            if self.thread_servidor_captura is not None:
                self.thread_servidor_captura.join(timeout=2)
            self.servidor_captura = None
            self.thread_servidor_captura = None
            self.url_captura.set("Servidor parado.")
            self.qr_captura.configure(image="", text="Inicie o servidor para gerar o QR Code.")
            self.qr_imagem = None

    def _mostrar_qr(self, endereco):
        if qrcode is None:
            self.qr_captura.configure(text="QR Code indisponível.\nUse o endereço acima.")
            return
        imagem = qrcode.make(endereco).convert("RGB")
        imagem.thumbnail((220, 220))
        self.qr_imagem = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=imagem.size)
        self.qr_captura.configure(text="", image=self.qr_imagem)

    def receber_fotos_enfileiradas(self):
        try:
            self.atualizar_fila_captura()
            self.processar_proxima_captura()
        except (OSError, sqlite3.Error) as erro:
            self.status.set(f"Não foi possível acessar a fila local: {erro}")
        finally:
            self.after(250, self.receber_fotos_enfileiradas)

    def salvar_revisao_captura(self, *_):
        if self.captura_id is not None and self.captura_pendente is not None and not self.restaurando_revisao:
            campos = {nome: getattr(self, "captura_" + nome).get()
                      for nome in ("descricao", "data", "valor", "tipo")}
            self.fila_ocr.salvar_campos(self.captura_id, campos)

    def finalizar_foto_captura(self, estado, motivo=None):
        if self.captura_id is not None:
            self.fila_ocr.finalizar(self.captura_id, estado, motivo)
            self.captura_id = None

    def descartar_captura(self):
        if self.captura_processando or self.captura_pendente is None:
            return
        self.finalizar_foto_captura("descartada", "Descartada por você.")
        self.captura_pendente = None
        self.atualizar_fila_captura()
        self.captura_aviso.set("Documento descartado e não adicionado ao A2.")
        self.status.set("Documento descartado; seguindo a fila.")
        self.after_idle(self.processar_proxima_captura)

    def receber_captura(self, conteudo, extensao):
        self.fila_ocr.adicionar(conteudo, extensao)
        self.atualizar_fila_captura()
        if self.captura_pendente is not None or self.captura_processando:
            if self.captura_pendente is None:
                self.captura_aviso.set(
                    f"Foto recebida. A foto atual está em leitura; "
                    f"{self.fila_ocr.quantidade('aguardando')} foto(s) depois dela.")
            self.status.set(f"Foto recebida; {self.fila_ocr.quantidade('aguardando')} na fila.")
            return
        self.processar_proxima_captura()

    def processar_proxima_captura(self):
        if self.captura_pendente is not None or self.captura_processando or self.fila_pausada:
            return
        foto = self.fila_ocr.proxima(self.motor_ocr.get())
        if foto is None:
            return
        self.captura_id = foto['id']
        if foto['estado'] == 'revisao':
            self.restaurando_revisao = True
            try:
                self.apresentar_resultado_ocr(foto['texto'], foto['aviso'] or "Documento recuperado; revise antes de confirmar.")
                for nome, valor in json.loads(foto['campos']).items():
                    getattr(self, 'captura_' + nome).set(valor)
            finally:
                self.restaurando_revisao = False
            return
        self.atualizar_fila_captura()
        self.captura_descricao.set("")
        self.captura_data.set("")
        self.captura_valor.set("")
        self.captura_tipo.set("")
        self.captura_texto.delete("1.0", "end")
        self.captura_aviso.set("Processando a próxima foto...")
        motor = foto['motor']
        self.captura_processando = True
        self.atualizar_fila_captura()
        self.captura_aviso.set("Lendo com " + motor + ". Aguarde o processamento.")
        def tarefa():
            try:
                conteudo = self.fila_ocr.caminho(foto).read_bytes()
                resultado = self.executor_ocr.ler(conteudo, foto['extensao'], motor)
            except Exception as erro:
                resultado = ("", f"Não foi possível ler a imagem: {erro}")
            if self.encerrando:
                return  # Mantém 'processando' para retomar ao reabrir.
            salvo = True
            try:
                self.fila_ocr.resultado(foto['id'], *resultado, interpretar_texto_documento(resultado[0]))
            except (OSError, sqlite3.Error) as erro:
                salvo = False
                resultado = ("", f"Fila pausada: não foi possível salvar o resultado: {erro}. A foto foi preservada; verifique o disco e reabra o programa.")
            self.resultados_ocr.put((*resultado, salvo))
        self.thread_ocr = threading.Thread(target=tarefa, daemon=True)
        self.thread_ocr.start()
        self.after(50, self.verificar_resultado_ocr)

    @staticmethod
    def ler_imagem_captura(conteudo, extensao, motor):
        temporario = None
        try:
            with NamedTemporaryFile(suffix=extensao, delete=False) as arquivo:
                arquivo.write(conteudo)
                temporario = arquivo.name
            return executar_ocr_motor(temporario, motor)
        except Exception as erro:
            return "", f"Não foi possível ler a imagem: {erro}"
        finally:
            if temporario is not None:
                try:
                    Path(temporario).unlink(missing_ok=True)
                except OSError as erro:
                    # Uma falha de limpeza não pode interromper a fila de OCR.
                    print(f"Não foi possível remover a imagem temporária: {erro}", file=sys.stderr)

    def verificar_resultado_ocr(self):
        try:
            resultado = self.resultados_ocr.get_nowait()
        except queue.Empty:
            self.after(50, self.verificar_resultado_ocr)
            return
        self.captura_processando = False
        texto, aviso, salvo = resultado
        if not salvo:
            self.fila_pausada = True
            self.captura_aviso.set(aviso)
            self.status.set("Fila pausada para preservar a foto. Verifique o armazenamento.")
            return
        self.apresentar_resultado_ocr(texto, aviso)

    def apresentar_resultado_ocr(self, texto, aviso):
        campos = interpretar_texto_documento(texto)
        _, aviso_data = identificar_vencimento(texto)
        if aviso_data:
            aviso = " ".join(item for item in (aviso_data, aviso) if item)
        self.captura_descricao.set(campos["descricao"])
        self.captura_data.set(campos["data"])
        self.captura_valor.set(campos["valor"])
        self.captura_tipo.set(campos["tipo"])
        self.captura_texto.delete("1.0", "end")
        self.captura_texto.insert("1.0", texto)
        if ((not campos["data"] and not aviso_data) or not campos["valor"]
                or campos["tipo"] not in ("D", "C")):
            motivo = aviso or "Não foi possível identificar data, valor e tipo na imagem."
            if self.captura_id is not None:
                self.fila_ocr.marcar_erro(self.captura_id, motivo)
                self.captura_id = None
            self.captura_pendente = None
            self.atualizar_fila_captura()
            self.trocar_aba("Captura")
            self.captura_aviso.set(motivo + " Foto preservada nas falhas do painel; tente novamente ou descarte.")
            self.status.set("Falha de leitura. Foto preservada; seguindo a fila.")
            self.after_idle(self.processar_proxima_captura)
            return
        self.captura_pendente = {"texto": texto}
        self.atualizar_fila_captura()
        self.captura_aviso.set(
            aviso or "Foto pronta. Confira os campos e verifique no A1.")
        self.trocar_aba("Captura")
        self.status.set("Documento recebido para revisão.")
        if not aviso:
            documento = self.captura_pendente
            self.after_idle(lambda: self.confirmar_captura(automatico=True)
                            if self.captura_pendente is documento else None)

    def confirmar_captura(self, automatico=False):
        if self.captura_pendente is None:
            self.status.set("Envie uma imagem antes de confirmar.")
            return
        valor = self.captura_valor.get().strip()
        tipo = self.captura_tipo.get().strip().upper()
        data = self.captura_data.get().strip()
        if not data or not valor or tipo not in ("D", "C"):
            mensagem = "Informe data, valor e tipo D ou C."
            if automatico:
                self.captura_aviso.set(f"Validação pendente: {mensagem}")
                self.status.set("A validação automática precisa de revisão.")
            else:
                messagebox.showwarning("Revisão necessária", mensagem, parent=self)
            return
        try:
            numero = normalizar_valor_captura(valor)
        except (ValueError, ArithmeticError):
            mensagem = "Informe um valor brasileiro válido."
            if automatico:
                self.captura_aviso.set(f"Validação pendente: {mensagem}")
                self.status.set("A validação automática precisa de revisão.")
            else:
                messagebox.showwarning("Valor inválido", mensagem, parent=self)
            return
        if data and re.fullmatch(r"\d{2}/\d{2}/\d{2,4}", data) is None:
            mensagem = "Use o formato DD/MM/AAAA."
            if automatico:
                self.captura_aviso.set(f"Validação pendente: {mensagem}")
                self.status.set("A validação automática precisa de revisão.")
            else:
                messagebox.showwarning("Data inválida", mensagem, parent=self)
            return
        correspondencias = correspondencias_campos(
            data, str(numero), tipo)
        if len(correspondencias) == 0:
            self.captura_aviso.set(
                "Documento não encontrado no A1. Não foi adicionado ao A2.")
            self.status.set("Documento não encontrado no A1.")
            self.finalizar_foto_captura("descartada", "Documento não encontrado no A1 por data, valor e tipo.")
            self.captura_pendente = None
            self.atualizar_fila_captura()
            self.processar_proxima_captura()
            return
        if len(correspondencias) > 1:
            self.captura_aviso.set(
                f"{len(correspondencias)} correspondências encontradas no A1. "
                "Não foi adicionado ao A2.")
            self.status.set("Há duplicidade no A1; escolha manualmente.")
            return
        numero_a1, registro = correspondencias[0]
        destino = carregar_linhas(ARQUIVO_DESTINO)
        destino.append(f"[{numero_a1}] {registro}")
        destino.sort(key=extrair_numero)
        salvar_linhas(ARQUIVO_DESTINO, destino)
        self.capturas_adicionadas.add(numero_a1)
        self.finalizar_foto_captura("concluida")
        self.captura_pendente = None
        self.atualizar_fila_captura()
        aguardando = self.fila_ocr.quantidade("aguardando")
        self.captura_aviso.set(
            f"Linha A1 {numero_a1} adicionada ao A2 e marcada na conferência. "
            f"{aguardando} foto(s) aguardando." if aguardando else
            f"Linha A1 {numero_a1} adicionada ao A2 e marcada na conferência.")
        self.atualizar_tudo()
        self.status.set(f"Linha A1 {numero_a1} adicionada ao A2.")
        self.processar_proxima_captura()

    def _montar_aba_captura(self):
        self.captura_processando = False
        self.executor_ocr = ExecutorOCR()
        self.resultados_ocr = queue.Queue()
        self.fila_ocr = FilaOCR(Path(PASTA_REG) / "capturas", exclusivo=True)
        self.fila_ocr.recuperar()
        self.captura_id = None
        self.fila_pausada = False
        self.encerrando = False
        self.restaurando_revisao = False
        self.thread_ocr = None
        self.after(250, self.receber_fotos_enfileiradas)
        self.motor_ocr = tk.StringVar(value="Tesseract")
        self.aba_captura.grid_columnconfigure(0, weight=1)
        self.aba_captura.grid_columnconfigure(1, weight=1)
        cabecalho = ctk.CTkFrame(self.aba_captura, fg_color="transparent")
        cabecalho.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 6))
        ctk.CTkLabel(cabecalho, text="Capturar documento",
                     font=(FONTE, 18, "bold"), text_color=c("texto")).pack(anchor="w")
        ctk.CTkLabel(cabecalho, text="Use o telefone na mesma rede Wi-Fi; a imagem é processada neste computador.",
                     text_color=c("cinza"), font=(FONTE, 12)).pack(anchor="w", pady=(2, 0))
        esquerda = ctk.CTkFrame(self.aba_captura, fg_color="transparent")
        esquerda.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=6)
        direita = ctk.CTkFrame(self.aba_captura, fg_color="transparent")
        direita.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=6)
        self.aba_captura.grid_rowconfigure(1, weight=1)
        self.url_captura = tk.StringVar(value="Servidor parado.")
        self.qr_imagem = None
        self.qr_captura = ctk.CTkLabel(esquerda, text="Inicie o servidor para gerar o QR Code.",
                                      text_color=c("cinza"), width=240, height=240)
        self.qr_captura.pack(pady=(8, 12))
        ctk.CTkLabel(esquerda, textvariable=self.url_captura, wraplength=360,
                     text_color=c("texto"), font=(FONTE, 13)).pack(fill="x")
        self.botao(esquerda, "Iniciar captura", self.iniciar_servidor_captura,
                   primario=True, largura=180).pack(pady=(14, 6))
        self.botao(esquerda, "Parar servidor", self.parar_servidor_captura,
                   largura=180).pack()
        seletor = ctk.CTkFrame(esquerda, fg_color="transparent")
        seletor.pack(fill="x", pady=(12, 4))
        ctk.CTkLabel(seletor, text="Leitura da imagem", text_color=c("cinza"),
                     font=(FONTE, 12)).pack()
        ctk.CTkOptionMenu(seletor, variable=self.motor_ocr,
                          values=["Tesseract", "PaddleOCR", "Comparar"],
                          width=180).pack(pady=4)
        self.captura_aviso = tk.StringVar(value="Nenhum documento recebido.")
        ctk.CTkLabel(direita, textvariable=self.captura_aviso, wraplength=460,
                     text_color=c("cinza"), justify="left").pack(anchor="w", pady=(4, 10))
        self.fila_captura = tk.StringVar(value="Fila: 0 foto(s)")
        ctk.CTkLabel(direita, textvariable=self.fila_captura,
                     text_color=c("cinza"), font=(FONTE, 11)).pack(anchor="w", pady=(0, 6))
        campos = (("Descrição (informativa)", "captura_descricao"), ("Data", "captura_data"),
                  ("Valor", "captura_valor"), ("Tipo (D/C)", "captura_tipo"))
        for titulo, atributo in campos:
            ctk.CTkLabel(direita, text=titulo, text_color=c("cinza"),
                         font=(FONTE, 12)).pack(anchor="w", pady=(4, 2))
            variavel = tk.StringVar()
            setattr(self, atributo, variavel)
            variavel.trace_add("write", self.salvar_revisao_captura)
            campo = self.campo(direita, variavel, titulo)
            if atributo == "captura_descricao":
                campo.configure(state="readonly")
            campo.pack(fill="x")
        ctk.CTkLabel(direita, text="Texto reconhecido", text_color=c("cinza"),
                     font=(FONTE, 12)).pack(anchor="w", pady=(8, 2))
        self.captura_texto = tk.Text(direita, height=8, wrap="word",
                                     bg=cm("campo", self.modo), fg=cm("texto", self.modo),
                                     insertbackground=cm("texto", self.modo), relief="flat")
        self.captura_texto.pack(fill="both", expand=True)
        self.botao(direita, "Verificar no A1 e adicionar ao A2", self.confirmar_captura,
                   primario=True, largura=250).pack(anchor="e", pady=(10, 4))
        self.botao(direita, "Descartar foto e seguir fila", self.descartar_captura,
                   largura=250).pack(anchor="e", pady=(0, 4))

    def atualizar_fila_captura(self):
        erros = self.fila_ocr.quantidade('erro')
        self.fila_captura.set(f"Fila: {self.fila_ocr.quantidade()} foto(s)" + (f" | Falhas: {erros}" if erros else ""))

    def mudar_tema(self, modo):
        self.modo = modo
        self.seg_tema.set(modo)
        ctk.set_appearance_mode("dark" if modo == "Escuro" else "light")
        self.aplicar_tema()
        salvar_config(self.modo, self.acento)
        self.status.set(f"Tema {modo.lower()} aplicado.")

    def mudar_acento(self, acento):
        self.acento = acento
        self.opt_acento.set(acento)
        self.aplicar_tema()
        salvar_config(self.modo, self.acento)
        self.status.set(f"Cor de destaque: {acento}.")

    def aplicar_tema(self):
        normal, hover = ACENTOS[self.acento]
        # widgets CustomTkinter com cor de destaque
        for b in self.primarios:
            b.configure(fg_color=normal, hover_color=hover)
        if self.botao_adicionar.cget("state") == "disabled":
            self.botao_adicionar.configure(fg_color=c("campo"), text_color_disabled=c("cinza"))
        self._atualizar_menu()
        self.seg_tema.configure(selected_color=("#1686ff", normal), selected_hover_color=("#0874e8", hover))
        # tabelas (ttk) precisam ser reestilizadas
        estilizar_tabelas(self.modo, normal, self.painel_busca._apply_widget_scaling(1))
        self.tree_busca.tag_configure("ja", foreground=cm("cinza", self.modo))
        self.tree_busca.tag_configure("novo", foreground=cm("texto", self.modo))
        self.tree_deb.tag_configure("atencao", foreground=cm("atencao", self.modo),
                                    background=cm("atencao_fundo", self.modo))
        self.tree_deb.tag_configure("falta", foreground=cm("vermelho", self.modo))
        self.tree_deb.tag_configure("ok", foreground=cm("verde", self.modo))
        self.tree_deb.tag_configure("captura", foreground=cm("captura", self.modo))
        for tree in (self.tree_busca, self.tree_deb, self.tree_a2):
            tree.tag_configure("alternada", background=cm("alternada", self.modo))
        if hasattr(self, "captura_texto"):
            self.captura_texto.configure(
                bg=cm("campo", self.modo), fg=cm("texto", self.modo),
                insertbackground=cm("texto", self.modo))
        self.divisao.configure(bg=cm("bg", self.modo))

    def ajustar_escala_tabelas(self, evento=None):
        escala = self.painel_busca._apply_widget_scaling(1)
        if getattr(self, "_escala_tabelas", None) == escala:
            return
        self._escala_tabelas = escala
        estilizar_tabelas(self.modo, ACENTOS[self.acento][0], escala)
        for tree in (self.tree_busca, self.tree_deb, self.tree_a2):
            for coluna, largura in tree.larguras_fixas.items():
                tree.column(coluna, width=round(largura * escala), minwidth=round(largura * escala))
            self.ajustar_largura_registro(tree)

    #  aba 1: buscar no A1 
    def _montar_aba_busca(self):
        topo = ctk.CTkFrame(self.aba_busca, fg_color="transparent")
        topo.pack(fill="x", pady=(2, 6))
        topo.grid_columnconfigure(0, weight=1)
        pesquisa = self.barra_pesquisa = ctk.CTkFrame(topo, fg_color="transparent")
        pesquisa.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        pesquisa.grid_columnconfigure(0, weight=1)
        caixa = ctk.CTkFrame(pesquisa, height=34, fg_color=c("campo"), corner_radius=5,
                              border_width=1, border_color=c("borda"))
        caixa.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(caixa, text="", image=icone("busca", tamanho=16), width=30, height=32).pack(side="left", padx=(6, 0))
        self.busca_var = tk.StringVar()
        entrada = self.campo(caixa, self.busca_var, "Pesquisar...", largura=170)
        self.entrada_busca = entrada
        entrada.configure(height=32)
        entrada.pack(side="left", fill="x", expand=True, padx=(0, 4), pady=1)
        entrada.bind("<Return>", lambda e: self.buscar_a1())
        entrada.focus_set()
        self.dica_busca = ctk.CTkLabel(caixa, text="Pesquisar...", height=24,
                                       text_color=c("cinza"), font=(FONTE, 12))
        self.dica_busca.place(x=42, rely=0.5, anchor="w")
        self.dica_busca.bind("<Button-1>", lambda evento: entrada.focus_set())
        self.busca_var.trace_add("write", self.atualizar_dica_busca)
        self.botao(pesquisa, "Buscar", self.buscar_a1, primario=True, largura=84, altura=32).grid(row=0, column=1, padx=(10, 8))
        self.botao(pesquisa, "Limpar", self.mostrar_todos, largura=84, altura=32).grid(row=0, column=2)
        self.botao_backup = self.botao(
            pesquisa, "Backup da sessão", self.criar_backup_sessao, largura=142, altura=32)
        self.botao_backup.grid(row=0, column=3, padx=(12, 0))
        self.botao_relatorio = self.botao(pesquisa, "Relatório", self.imprimir_relatorio, largura=108, altura=32)
        self.botao_relatorio.grid(row=0, column=4, padx=(8, 0))
        indicadores = self.barra_indicadores = ctk.CTkFrame(topo, fg_color="transparent")
        indicadores.grid(row=0, column=1, sticky="e")
        self.indicador_origem = tk.StringVar(value="0")
        self.indicador_ok = tk.StringVar(value="0")
        self.indicador_falta = tk.StringVar(value="0")
        self.indicador_atencao = tk.StringVar(value="0")
        self.cartoes_resumo = []
        for coluna, (variavel, titulo, simbolo, cor) in enumerate((
                (self.indicador_origem, "Registros A1", "arquivo", "cabecalho"),
                (self.indicador_ok, "Conferidos", "confirmado", "verde"),
                (self.indicador_falta, "Faltando no A2", "alerta", "vermelho"),
                (self.indicador_atencao, "Atenção", "atencao", "atencao"))):
            cartao = ctk.CTkFrame(indicadores, height=38, width=0, corner_radius=5,
                                   fg_color=c("painel"), border_width=1, border_color=c("borda"))
            cartao.grid(row=0, column=coluna, sticky="ew", padx=(0 if coluna == 0 else 6, 0))
            # Largura segue o texto, sem distribuir espaço vazio entre os ícones.
            ctk.CTkLabel(cartao, text="", image=icone(simbolo, cor, 20), width=24, height=32).grid(
                row=0, column=0, rowspan=2, padx=(6, 4), pady=2)
            ctk.CTkLabel(cartao, textvariable=variavel, height=20, anchor="w", text_color=c("texto"),
                         font=(FONTE, 16, "bold")).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(2, 0))
            ctk.CTkLabel(cartao, text=titulo, height=15, anchor="w", text_color=c(cor),
                         font=(FONTE, 11)).grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 2))
            self.cartoes_resumo.append(cartao)
        topo.bind("<Configure>", self.ajustar_barra_pesquisa)
        self.divisao = tk.PanedWindow(self.aba_busca, orient="horizontal", sashwidth=8,
                                     bd=0, sashrelief="flat", showhandle=False,
                                     bg=cm("bg", self.modo), opaqueresize=True)
        self.divisao.pack(fill="both", expand=True)
        self.painel_busca = ctk.CTkFrame(self.divisao, bg_color=c("bg"), fg_color=c("painel"),
                                       border_width=1, border_color=c("borda"), corner_radius=6)
        self.aba_deb = ctk.CTkFrame(self.divisao, bg_color=c("bg"), fg_color=c("painel"),
                                  border_width=1, border_color=c("borda"), corner_radius=6)
        self.divisao.add(self.painel_busca, minsize=380, stretch="always", width=600)
        self.divisao.add(self.aba_deb, minsize=440, stretch="always")
        self._divisao_posicionada = False
        self.divisao.bind("<Configure>", self.posicionar_divisao)
        for painel in (self.painel_busca, self.aba_deb):
            painel.grid_columnconfigure(0, weight=1)
            painel.grid_rowconfigure(0, minsize=34)
            painel.grid_rowconfigure(1, weight=1)
            painel.grid_rowconfigure(2, minsize=38)
        cabecalho = ctk.CTkFrame(self.painel_busca, fg_color="transparent")
        cabecalho.grid(row=0, column=0, sticky="ew", padx=8, pady=3)
        cabecalho.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(cabecalho, text="Registros do A1",
                    font=(FONTE, 16, "bold"), text_color=c("texto")).grid(row=0, column=0, sticky="w")
        self.resumo_origem = tk.StringVar()
        ctk.CTkLabel(cabecalho, textvariable=self.resumo_origem,
                    text_color=c("cinza"), font=(FONTE, 12)).grid(row=0, column=1, sticky="w", padx=(8, 0))

        frame, self.tree_busca = self._tabela(
            self.painel_busca, [("ordem", "Nº"), ("linha", "Linha A1"), ("texto", "Registro"),
                                ("situacao", "No A2"), ("valor", "Valor")],
            [42, 80, 0, 60, 112])
        frame.grid(row=1, column=0, sticky="nsew", padx=8)
        self.tree_busca.configure(displaycolumns=("ordem", "linha", "situacao", "valor", "texto"))
        rodape = ctk.CTkFrame(self.painel_busca, fg_color="transparent")
        rodape.grid(row=2, column=0, sticky="ew", padx=8, pady=3)
        self.resumo_selecao = tk.StringVar(value="Nenhum selecionado")
        ctk.CTkLabel(rodape, textvariable=self.resumo_selecao,
                     text_color=c("cinza"), font=(FONTE, 12)).pack(side="left")
        self.botao_adicionar = self.botao(rodape, "Adicionar ao A2", self.adicionar_e_comparar,
                                          primario=True, largura=164, altura=32)
        self.botao_adicionar.pack(side="right")
        self.botao_adicionar.configure(state="disabled")
        self.tree_busca.bind("<Double-1>", self.adicionar_por_duplo_clique)
        self.tree_busca.bind("<<TreeviewSelect>>", self.atualizar_selecao_origem)

    def ajustar_barra_pesquisa(self, evento=None):
        pesquisa, indicadores = self.barra_pesquisa, self.barra_indicadores
        topo = pesquisa.master
        minimo = pesquisa.winfo_reqwidth() + indicadores.winfo_reqwidth()
        minimo += round(pesquisa._apply_widget_scaling(20))
        compacta = topo.winfo_width() < minimo
        linha = 1 if compacta else 0
        if int(indicadores.grid_info()["row"]) != linha:
            indicadores.grid(row=linha, column=0 if compacta else 1,
                             sticky="w" if compacta else "e", pady=(6, 0) if compacta else 0)
            pesquisa.grid(columnspan=2 if compacta else 1)

    def atualizar_dica_busca(self, *args):
        if self.busca_var.get():
            self.dica_busca.place_forget()
        else:
            self.dica_busca.place(x=42, rely=0.5, anchor="w")

    def atualizar_selecao_origem(self, evento=None):
        quantidade = len(self.tree_busca.selection())
        self.resumo_selecao.set("1 selecionado" if quantidade == 1 else
                               f"{quantidade} selecionados" if quantidade else "Nenhum selecionado")
        self.botao_adicionar.configure(state="normal" if quantidade else "disabled")
        self.botao_adicionar.configure(fg_color=ACENTOS[self.acento][0] if quantidade else c("campo"),
                                       text_color_disabled=c("cinza"))
        self.sincronizar_selecao(self.tree_busca, self.tree_deb)
        self.atualizar_contadores()

    def posicionar_divisao(self, evento):
        for painel, minimo in ((self.painel_busca, 380), (self.aba_deb, 440)):
            largura = round(painel._apply_widget_scaling(minimo))
            if int(self.divisao.panecget(painel, "minsize")) != largura:
                self.divisao.paneconfigure(painel, minsize=largura)
            altura = round(painel._apply_widget_scaling(34))
            if painel.grid_rowconfigure(0)["minsize"] != altura:
                painel.grid_rowconfigure(0, minsize=altura)
        if not self._divisao_posicionada:
            self._divisao_posicionada = True
            self.after_idle(lambda: self.divisao.sash_place(0, self.divisao.winfo_width() // 2, 0))

    def buscar_a1(self):
        self.termo_busca = self.busca_var.get().strip()
        termo = self.termo_busca.lower()
        self.tree_busca.delete(*self.tree_busca.get_children())
        self.resultados = []
        origem = carregar_origem_numerada()
        conferidos = referencias_no_destino(origem, carregar_linhas(ARQUIVO_DESTINO))
        self.resultados = [(n, t) for n, t in origem if corresponde(termo, t)]
        for i, (n, t) in enumerate(self.resultados):
            ja = n in conferidos
            self.tree_busca.insert("", "end", iid=str(i),
                                   values=(i + 1, n, t, "✓ no A2" if ja else "", formatar_valor_registro(t)),
                                   tags=("ja" if ja else "novo", "alternada" if i % 2 else "normal"))
        self.ajustar_largura_registro(self.tree_busca)
        self.resumo_origem.set(f"({len(self.resultados)} registros disponíveis)")
        self.atualizar_selecao_origem()
        if termo:
            self.status.set(f"{len(self.resultados)} resultado(s) para '{termo}'.")
        else:
            self.status.set(f"A1: {len(self.resultados)} registro(s) exibido(s).")
        self.atualizar_debitos()

    def sincronizar_selecao(self, origem, destino):
        if self._sincronizando_selecao:
            return
        numeros = {origem.set(iid, "linha") for iid in origem.selection()}
        selecao = tuple(iid for iid in destino.get_children() if destino.set(iid, "linha") in numeros)
        if destino.selection() != selecao:
            self._sincronizando_selecao = True
            destino.selection_set(*selecao)
            if selecao:
                destino.see(selecao[0])
            self.after_idle(lambda: setattr(self, "_sincronizando_selecao", False))

    def mostrar_todos(self):
        self.busca_var.set("")
        self.buscar_a1()

    def adicionar_e_comparar(self):
        self.adicionar_selecionados(comparar=True)

    def adicionar_por_duplo_clique(self, evento):
        if self.tree_busca.identify_region(evento.x, evento.y) != "cell":
            return
        item = self.tree_busca.identify_row(evento.y)
        if item:
            self.tree_busca.selection_set(item)
            self.adicionar_e_comparar()
            return "break"

    def adicionar_selecionados(self, comparar=False):
        sel = self.tree_busca.selection()
        if not sel:
            self.status.set("Selecione um ou mais registros para adicionar.")
            return
        selecionados_origem = [self.resultados[int(iid)] for iid in sel]
        origem_atual = dict(carregar_origem_numerada())
        if any(origem_atual.get(numero) != texto for numero, texto in selecionados_origem):
            self.buscar_a1()
            self.status.set("O A1 foi alterado. Confira os registros e selecione novamente.")
            return
        destino = carregar_linhas(ARQUIVO_DESTINO)
        conferidos = referencias_no_destino(list(origem_atual.items()), destino)
        adicionados = 0
        numeros = set()
        for numero, texto in selecionados_origem:
            numeros.add(numero)
            item = f"[{numero}] {texto}"
            if numero not in conferidos:
                destino.append(item)
                adicionados += 1
        destino.sort(key=extrair_numero)
        salvar_linhas(ARQUIVO_DESTINO, destino)
        self.buscar_a1()
        self.tree_busca.selection_set(*(iid for iid in self.tree_busca.get_children()
                                       if int(self.tree_busca.set(iid, "linha")) in numeros))
        self.atualizar_a2()
        self.atualizar_debitos()
        self.status.set(f"✓ {adicionados} registro(s) adicionado(s) ao A2.")
        if comparar:
            self.tipo_comparacao.set("Todos")
            self.atualizar_debitos()
            self.abas.set("Buscar e comparar")
            selecionados = [iid for iid in self.tree_deb.get_children()
                            if int(self.tree_deb.set(iid, "linha")) in numeros]
            self.tree_deb.selection_set(*selecionados)
            if selecionados:
                self.tree_deb.focus(selecionados[0])
                self.tree_deb.see(selecionados[0])
            self.status.set(f"{adicionados} adicionado(s) ao A2; "
                            f"{len(selecionados)} lançamento(s) selecionado(s) na comparação. "
                            "Saldos, resumos e registros sem D/C não entram na comparação.")

    #  aba 2: lista A2 
    def _montar_aba_a2(self):
        topo = ctk.CTkFrame(self.aba_a2, fg_color="transparent")
        topo.pack(fill="x", padx=12, pady=(6, 6))
        topo.grid_columnconfigure(1, weight=1)
        self.filtro_a2 = tk.StringVar()
        self.filtro_a2.trace_add("write", lambda *a: self.atualizar_a2())
        ctk.CTkLabel(topo, text="Filtrar", font=(FONTE, 14),
                     text_color=c("cinza")).grid(row=0, column=0, padx=(0, 12))
        self.campo(topo, self.filtro_a2, "Filtrar lista...").grid(row=0, column=1, sticky="ew")
        self.botao(topo, "Remover", self.remover_a2, perigo=True, largura=140, altura=30).grid(
            row=0, column=2, padx=10)

        frame, self.tree_a2 = self._tabela(
            self.aba_a2, [("ordem", "Nº"), ("linha", "Linha A1"), ("texto", "Registro"),
                          ("valor", "Valor")], [42, 80, 0, 128])
        self.tree_a2.configure(displaycolumns=("ordem", "linha", "valor", "texto"))
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))

    def atualizar_a2(self):
        self.tree_a2.delete(*self.tree_a2.get_children())
        filtro = self.filtro_a2.get().strip().lower()
        total = 0
        self.itens_a2 = obter_destino_ordenado()
        for indice, item in enumerate(self.itens_a2):
            texto = extrair_texto_registro(item)
            if filtro and not corresponde(filtro, texto):
                continue
            total += 1
            numero = extrair_numero(item) if re.match(r"^\[\d+\]", item) else "—"
            self.tree_a2.insert("", "end", iid=str(indice), values=(total, numero, texto, formatar_valor_registro(texto)),
                                tags=("alternada" if total % 2 == 0 else "normal",))
        self.ajustar_largura_registro(self.tree_a2)
        if self.abas.get() == "Lista A2":
            self.status.set(f"A2: {total} registro(s) exibido(s).")

    def remover_a2(self):
        sel = self.tree_a2.selection()
        if not sel:
            self.status.set("Selecione registros do A2 para remover.")
            return
        if not messagebox.askyesno("Remover", f"Remover {len(sel)} registro(s) do A2?"):
            return
        if obter_destino_ordenado() != self.itens_a2:
            self.atualizar_a2()
            self.status.set("O A2 foi alterado. Confira a lista e selecione novamente.")
            return
        indices = {int(iid) for iid in sel}
        restantes = [item for i, item in enumerate(self.itens_a2) if i not in indices]
        salvar_linhas(ARQUIVO_DESTINO, restantes)
        self.atualizar_a2()
        self.atualizar_debitos()
        self.buscar_a1()
        self.status.set(f"{len(sel)} registro(s) removido(s).")

    def criar_backup_sessao(self):
        """Copia A1, A2 e as marcações para uma pasta identificada pelo usuário."""
        sugestao = "Usuário - " + datetime.now().strftime("%d-%m-%Y")
        nome = simpledialog.askstring(
            "Backup da sessão", "Nome da pasta do backup:",
            initialvalue=sugestao, parent=self)
        if nome is None:
            self.status.set("Backup cancelado.")
            return
        nome = nome.strip()
        reservado = re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", nome.split(".")[0])
        if (not nome or nome in {".", ".."} or nome[-1:] in {".", " "} or reservado
                or any(ord(caractere) < 32 or caractere in '<>:"/\\|?*' for caractere in nome)):
            messagebox.showerror(
                "Nome inválido",
                "Use um nome de pasta válido, sem caracteres especiais ou nomes reservados do Windows.",
                parent=self)
            self.status.set("O backup não foi criado: nome inválido.")
            return

        base = Path(PASTA_REG).absolute()
        base.mkdir(parents=True, exist_ok=True)
        destino = base / nome
        if destino.exists():
            messagebox.showerror(
                "Pasta existente",
                f"A pasta já existe:\n{destino}\n\nEscolha outro nome.", parent=self)
            self.status.set("O backup não foi criado porque o nome já existe.")
            return

        # Monta tudo em uma pasta temporária para não deixar exportação parcial.
        with TemporaryDirectory(prefix="exportacao-", dir=base) as temporaria:
            pasta_temporaria = Path(temporaria)
            for origem in (Path(ARQUIVO_ORIGEM), Path(ARQUIVO_DESTINO)):
                shutil.copy2(origem, pasta_temporaria / origem.name)
            origem_atencao = Path(ARQUIVO_ATENCAO)
            if origem_atencao.is_file():
                shutil.copy2(origem_atencao, pasta_temporaria / origem_atencao.name)
            else:
                dados = {"versao": 1, "marcacoes": []}
                (pasta_temporaria / origem_atencao.name).write_text(
                    json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
            os.replace(pasta_temporaria, destino)
        self.status.set(f"✓ Backup da sessão criado em {destino}")
        messagebox.showinfo(
            "Backup concluído",
            f"Arquivos copiados para:\n{destino}", parent=self)

    #  aba 3: comparação de débitos e créditos
    def _montar_aba_debitos(self):
        cabecalho = ctk.CTkFrame(self.aba_deb, fg_color="transparent")
        cabecalho.grid(row=0, column=0, sticky="ew", padx=8, pady=3)
        cabecalho.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(cabecalho, text="Conferência A1 × A2",
                    font=(FONTE, 16, "bold"), text_color=c("texto")).grid(row=0, column=0, sticky="w")
        rodape = ctk.CTkFrame(self.aba_deb, fg_color="transparent")
        rodape.grid(row=2, column=0, sticky="ew", padx=8, pady=3)
        self.tipo_comparacao = tk.StringVar(value="Todos")
        self.tipo_comparacao.trace_add("write", lambda *a: self.atualizar_debitos())
        ctk.CTkLabel(rodape, text="Mostrar:", text_color=c("cinza"),
                     font=(FONTE, 12)).pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(rodape, values=["Todos", "Débitos", "Créditos"],
                         variable=self.tipo_comparacao, width=120, height=30,
                         font=(FONTE, 13), dropdown_font=(FONTE, 13),
                         fg_color=c("campo"), button_color=c("campo_hover"),
                         button_hover_color=c("campo_hover"), text_color=c("texto"),
                         dropdown_fg_color=c("painel"), dropdown_text_color=c("texto"),
                         dropdown_hover_color=c("campo")).pack(side="left")
        self.var_total = tk.StringVar(value="0")
        self.var_falta = tk.StringVar(value="0")
        self.resumo_conferencia = tk.StringVar()
        ctk.CTkLabel(cabecalho, textvariable=self.resumo_conferencia,
                     text_color=c("cinza"), font=(FONTE, 12)).grid(row=0, column=1, sticky="w", padx=(8, 0))

        frame, self.tree_deb = self._tabela(
            self.aba_deb, [("ordem", "Nº"), ("linha", "Linha A1"), ("texto", "Registro"),
                           ("situacao", "Situação"), ("valor", "Valor")],
            [42, 80, 0, 116, 110])
        frame.grid(row=1, column=0, sticky="nsew", padx=8)
        self.tree_deb.configure(style="Treeview", displaycolumns=("ordem", "linha", "situacao", "valor", "texto"))
        self.botao(rodape, "Atualizar", self.atualizar_tudo,
                   largura=108, altura=32).pack(side="right", padx=(0, 10))
        self.tree_deb.bind("<<TreeviewSelect>>", lambda e: self.sincronizar_selecao(self.tree_deb, self.tree_busca))
        self.tree_deb.bind("<Double-1>", self.alternar_atencao)

    def alternar_atencao(self, evento):
        if self.tree_deb.identify_region(evento.x, evento.y) != "cell":
            return
        item = self.tree_deb.identify_row(evento.y)
        if not item:
            return
        numero = int(self.tree_deb.set(item, "linha"))
        texto = self.tree_deb.set(item, "texto")
        atual = dict(carregar_origem_numerada()).get(numero)
        if atual is None or chave_atencao(numero, atual) != chave_atencao(numero, texto):
            self.buscar_a1()
            self.status.set("O A1 foi alterado. Confira a lista antes de marcar atenção.")
            return "break"
        chave = chave_atencao(numero, texto)
        try:
            marcacoes = carregar_atencoes()
            marcou = chave not in marcacoes
            marcacoes.symmetric_difference_update({chave})
            salvar_atencoes(marcacoes)
        except (OSError, ValueError) as erro:
            self.status.set("Não foi possível salvar a marcação de atenção.")
            messagebox.showerror("Marcação de atenção", str(erro), parent=self)
            return "break"
        self.atencoes = marcacoes
        # Atualiza somente as tags para preservar seleção, foco e rolagem.
        for iid in self.tree_deb.get_children():
            tags = list(self.tree_deb.item(iid, "tags"))
            tags = [tag for tag in tags if tag != "atencao"]
            identidade = chave_atencao(int(self.tree_deb.set(iid, "linha")),
                                       self.tree_deb.set(iid, "texto"))
            if identidade in self.atencoes:
                tags.insert(0, "atencao")
            self.tree_deb.item(iid, tags=tags)
        self.indicador_atencao.set(str(sum(
            "atencao" in self.tree_deb.item(iid, "tags") for iid in self.tree_deb.get_children())))
        self.status.set(f"Linha A1 {numero}: atenção {'marcada' if marcou else 'removida'} e salva.")
        return "break"

    def tipo_selecionado(self):
        return {"Todos": None, "Débitos": "D", "Créditos": "C"}[self.tipo_comparacao.get()]

    def imprimir_relatorio(self):
        caminho = gerar_relatorio_html(self.tipo_selecionado(), self.termo_busca, abrir=False)
        arquivo = str(Path(caminho).resolve())
        if abrir_arquivo_relatorio(arquivo):
            self.status.set(f"Relatório aberto. Arquivo salvo em {arquivo}")
        else:
            self.status.set(f"Relatório salvo, mas não foi possível abrir automaticamente: {arquivo}")
            messagebox.showwarning(
                "Relatório salvo",
                "O relatório foi gerado, mas não foi possível abrir automaticamente.\n\n"
                f"Arquivo: {arquivo}\n\n"
                "Abra esse arquivo em um navegador e clique em Imprimir Relatório ou pressione Ctrl+P.",
                parent=self)

    def atualizar_debitos(self):
        self.tree_deb.delete(*self.tree_deb.get_children())
        resultado, total, faltando = calcular_lancamentos(self.tipo_selecionado(), self.termo_busca)
        for i, (numero, texto, ok) in enumerate(resultado):
            situacao = "OK" if ok else "FALTA NO A2"
            status_tag = "captura" if numero in self.capturas_adicionadas else ("ok" if ok else "falta")
            tags = [status_tag, "alternada" if i % 2 else "normal"]
            if chave_atencao(numero, texto) in self.atencoes:
                tags.insert(0, "atencao")
            self.tree_deb.insert("", "end", iid=str(i),
                                 values=(i + 1, numero, texto, situacao, formatar_valor_registro(texto)), tags=tuple(tags))
        self.ajustar_largura_registro(self.tree_deb)
        self.var_total.set(str(total))
        self.var_falta.set(str(faltando))
        self.resumo_conferencia.set(f"({total} exibidos · {faltando} faltando no A2)")
        self.indicador_origem.set(str(len(self.resultados)))
        self.indicador_ok.set(str(total - faltando))
        self.indicador_falta.set(str(faltando))
        self.indicador_atencao.set(str(sum(
            chave_atencao(numero, texto) in self.atencoes for numero, texto, _ in resultado)))
        self.atualizar_contadores()
        self.sincronizar_selecao(self.tree_busca, self.tree_deb)
        if self.abas.get() == "Buscar e comparar":
            self.status.set(f"Atualizado em {datetime.now():%d/%m/%Y %H:%M:%S}")

    def atualizar_contadores(self):
        self.contadores.set(f"A1: {len(self.resultados)} registros  |  "
                            f"Conferência: {self.var_total.get()} lançamentos  |  "
                            f"Faltando: {self.var_falta.get()}  |  "
                            f"Selecionados: {len(self.tree_busca.selection())}")

    def atualizar_tudo(self):
        self.buscar_a1()
        self.atualizar_a2()
        self.atualizar_debitos()
        self.status.set(f"Atualizado em {datetime.now():%d/%m/%Y %H:%M:%S}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    preparar_console_windows()
    inicializar_arquivos()
    App().mainloop()
