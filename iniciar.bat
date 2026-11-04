@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo Organizacao - Inicializacao completa
where uv >nul 2>&1
if errorlevel 1 (
  echo Instale o uv com: python -m pip install uv
  echo Reabra o terminal e execute novamente.
  pause
  exit /b 1
)
echo [1/3] Verificando dependencias e PaddleOCR...
uv sync --frozen --inexact --extra paddle --python ">=3.11,<3.14"
if errorlevel 1 goto dependencias_basicas
echo [2/3] Preparando modelos do PaddleOCR. O primeiro uso precisa de internet.
uv run --no-sync --python ">=3.11,<3.14" python ocr_paddle.py
if errorlevel 1 (
  echo Aviso: PaddleOCR nao ficou pronto. Confira o erro acima.
  echo O programa sera aberto para usar Tesseract ou preenchimento manual.
)
goto abrir

:dependencias_basicas
echo Aviso: nao foi possivel preparar o PaddleOCR. Tentando dependencias basicas...
uv sync --frozen --inexact --python ">=3.11,<3.14"
if errorlevel 1 (
  echo Nao foi possivel preparar as dependencias. Confira a mensagem acima e a conexao.
  pause
  exit /b 1
)
echo PaddleOCR indisponivel. Use Tesseract ou preenchimento manual.

:abrir
echo [3/3] Abrindo o programa...
uv run --no-sync --python ">=3.11,<3.14" python main.py %*
set "launcher_exit=%errorlevel%"
pause
exit /b %launcher_exit%
