"""Executa a suíte existente, com validação gráfica completa opcional."""

import argparse
import sys
import unittest
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-gui", action="store_true",
        help="Falha se algum teste for ignorado, inclusive por falta de sessão gráfica.",
    )
    args = parser.parse_args(argv)
    raiz = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(raiz))
    suite = unittest.defaultTestLoader.discover(str(raiz / "tests"))
    if suite.countTestCases() == 0:
        print("Nenhum teste encontrado; validação não realizada.", file=sys.stderr)
        return 1

    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.require_gui and resultado.skipped:
        print(
            "Validação incompleta: há testes ignorados. Execute com sessão gráfica "
            "para verificar a suíte completa.",
            file=sys.stderr,
        )
        return 1
    return 0 if resultado.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
