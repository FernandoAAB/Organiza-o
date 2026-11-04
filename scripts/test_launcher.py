"""Valida o .bat no cmd.exe, sem baixar pacotes nem modelos de OCR."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    if os.name != "nt":
        raise SystemExit("Este teste precisa do Windows e do cmd.exe.")
    raiz = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="teste inicializador ") as pasta:
        destino = Path(pasta)
        shutil.copyfile(raiz / "iniciar.bat", destino / "iniciar.bat")
        # Projeto fictício: o uv real interpreta --extra e prepara o ambiente,
        # enquanto o adaptador simulado verifica a ordem e as falhas do preparo.
        (destino / "pyproject.toml").write_text(
            '[project]\nname="teste-launcher"\nversion="0.0.0"\n'
            'requires-python=">=3.11,<3.14"\ndependencies=[]\n'
            '[project.optional-dependencies]\npaddle=[]\n', encoding="utf-8")
        env = dict(os.environ, UV_OFFLINE="1")
        subprocess.run(["uv", "lock", "--offline", "--python", ">=3.11,<3.14"],
                       cwd=destino, env=env, check=True, timeout=60)
        (destino / "ocr_paddle.py").write_text(
            "from pathlib import Path\n"
            "import os\n"
            "Path('preparo.txt').write_text('executado')\n"
            "raise SystemExit(int(os.environ.get('TESTE_MODELOS_ERRO', '0')))\n",
            encoding="utf-8")
        (destino / "main.py").write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "assert Path('preparo.txt').read_text() == 'executado'\n"
            "assert sys.argv[1:] == ['argumento com espacos']\n"
            "print('LAUNCHER_OK')\n"
            "raise SystemExit(7)\n", encoding="utf-8")
        for erro_modelos in ("0", "1"):
            (destino / "preparo.txt").unlink(missing_ok=True)
            resultado = subprocess.run(
                f'cmd.exe /d /s /c ""{destino / "iniciar.bat"}" "argumento com espacos""',
                cwd=raiz.parent, env=dict(env, TESTE_MODELOS_ERRO=erro_modelos),
                input=b"\r\n", stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=90,
            )
            print(resultado.stdout.decode("utf-8", errors="replace"))
            assert b"LAUNCHER_OK" in resultado.stdout, "O .bat nao iniciou o Python."
            assert resultado.returncode == 7, "O .bat nao preservou o codigo de saida."
            if erro_modelos == "1":
                assert b"PaddleOCR nao ficou pronto" in resultado.stdout
    print("Inicializador e falha de modelos validados no cmd.exe.")


if __name__ == "__main__":
    main()
