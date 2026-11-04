"""Exercita o .bat no cmd.exe real, em uma pasta temporária com espaços."""
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
        for nome in ("iniciar.bat", "pyproject.toml", "uv.lock"):
            shutil.copyfile(raiz / nome, destino / nome)
        # Confirma que o launcher inicia o Python na pasta certa e devolve o erro.
        (destino / "main.py").write_text(
            "from pathlib import Path\n"
            "assert Path('iniciar.bat').is_file()\n"
            "print('LAUNCHER_OK')\n"
            "raise SystemExit(7)\n", encoding="utf-8")
        resultado = subprocess.run(
            ["cmd.exe", "/d", "/c", str(destino / "iniciar.bat")],
            cwd=raiz.parent, input=b"\r\n", stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=180,
        )
        print(resultado.stdout.decode("utf-8", errors="replace"))
        assert b"LAUNCHER_OK" in resultado.stdout, "O .bat nao iniciou o Python."
        assert resultado.returncode == 7, "O .bat nao preservou o codigo de saida."
    print("Inicializador validado no cmd.exe.")


if __name__ == "__main__":
    main()
