# Ferramenta de diagnóstico: executa ambos os motores nas mesmas imagens e imprime um resumo JSON.
"""Compara localmente texto, campos e tempo dos dois mecanismos na mesma imagem."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import executar_ocr_motor, interpretar_texto_documento


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('imagens', nargs='+', type=Path)
    args = parser.parse_args()
    resultados = []
    for caminho in args.imagens:
        for motor in ('Tesseract', 'PaddleOCR'):
            inicio = time.monotonic()
            texto, aviso = executar_ocr_motor(caminho, motor)
            resultados.append(dict(imagem=caminho.name, motor=motor,
                                   segundos=round(time.monotonic() - inicio, 3),
                                   texto=texto, campos=interpretar_texto_documento(texto), aviso=aviso))
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
