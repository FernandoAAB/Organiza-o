# Adaptador opcional: importar este módulo não inicializa o PaddleOCR nem baixa modelos.
"""PaddleOCR opcional: carrega modelos só quando solicitado e processa localmente."""
import re
import math
import statistics
import os
from pathlib import Path
import sys
import threading

_motor = None
_trava = threading.Lock()


def criar_motor():
    if not (3, 11) <= sys.version_info[:2] < (3, 14):
        raise RuntimeError("Use Python 3.11 a 3.13 para o PaddleOCR.")
    modelos = {
        "doc_orientation_classify": "PP-LCNet_x1_0_doc_ori",
        "textline_orientation": "PP-LCNet_x1_0_textline_ori",
        "text_detection": "PP-OCRv5_mobile_det",
        "text_recognition": "latin_PP-OCRv5_mobile_rec",
    }
    cache = Path(os.environ.get("PADDLE_PDX_CACHE_HOME", Path.home() / ".paddlex")) / "official_models"
    opcoes = {}
    for tarefa, nome in modelos.items():
        opcoes[tarefa + "_model_name"] = nome
        pasta = cache / nome
        if all((pasta / arquivo).is_file() for arquivo in
               ("inference.json", "inference.pdiparams", "inference.yml")):
            opcoes[tarefa + "_model_dir"] = str(pasta)
    from paddleocr import PaddleOCR
    return PaddleOCR(
        **opcoes,
        use_doc_orientation_classify=True,
        use_doc_unwarping=False,
        use_textline_orientation=True,
        text_rec_score_thresh=0.0,
        device="cpu", enable_mkldnn=False,
        cpu_threads=max(1, min(2, (os.cpu_count() or 2) - 1)),
    )


def organizar_resultado(paginas):
    linhas = []
    soma = peso = 0
    numeros_incertos = False
    for pagina in paginas:
        caixas = pagina["rec_boxes"]
        palavras = []
        poligonos = pagina.get("rec_polys")
        angulos = ([math.atan2(p[1][1] - p[0][1], p[1][0] - p[0][0])
                    for p in poligonos] if poligonos is not None else [])
        angulo = statistics.median(angulos) if angulos else 0
        seno, cosseno = math.sin(angulo), math.cos(angulo)
        for i, (texto, confianca, caixa) in enumerate(zip(
                pagina["rec_texts"], pagina["rec_scores"], caixas)):
            texto = texto.strip()
            if not texto:
                continue
            x1, y1, x2, y2 = map(float, caixa)
            if poligonos is not None:
                pontos = [(cosseno * x + seno * y, -seno * x + cosseno * y)
                          for x, y in poligonos[i]]
                x1 = min(x for x, _ in pontos)
                y1, y2 = min(y for _, y in pontos), max(y for _, y in pontos)
            palavras.append((y1, x1, y2, texto))
            soma += float(confianca) * len(texto)
            peso += len(texto)
            if re.search(r"\d", texto) and confianca < 0.9:
                numeros_incertos = True
        # Uma data ou valor à direita do rótulo deve continuar na mesma linha.
        grupos = []
        for y1, x1, y2, texto in sorted(palavras):
            centro = (y1 + y2) / 2
            grupo = next((g for g in grupos
                          if abs(g[0] - centro) <= max(1, min(g[1], y2 - y1) * 0.5)), None)
            if grupo is None:
                grupo = [centro, y2 - y1, []]
                grupos.append(grupo)
            grupo[2].append((x1, texto))
        linhas.extend(" ".join(texto for _, texto in sorted(g[2])) for g in grupos)
    texto = "\n".join(linhas)
    if not texto:
        return "", "PaddleOCR não reconheceu texto na imagem."
    if numeros_incertos or not peso or soma / peso < 0.9:
        return texto, "Leitura incerta do PaddleOCR: revise data, valor e tipo antes de confirmar."
    return texto, ""


def executar_paddleocr(caminho):
    global _motor
    try:
        with _trava:
            if _motor is None:
                _motor = criar_motor()
            return organizar_resultado(_motor.predict(str(caminho)))
    except ImportError:
        return "", "PaddleOCR não instalado. Instale a opção paddle conforme o README."
    except Exception as erro:
        # A biblioteca pode falhar ao carregar o runtime ou baixar os modelos.
        return "", f"PaddleOCR indisponível: {erro}"


def preparar_modelos():
    """Baixa/carrega somente os modelos; nenhuma imagem é enviada."""
    global _motor
    with _trava:
        if _motor is None:
            _motor = criar_motor()


if __name__ == "__main__":
    from ocr_runtime import preparar_console_windows
    preparar_console_windows()
    preparar_modelos()
    print("Modelos do PaddleOCR preparados para processamento local.")
