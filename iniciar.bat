@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo Organização - Inicialização
where uv >nul 2>&1
if errorlevel 1 (
  echo Instale o uv com: python -m pip install uv
  echo Reabra o terminal e execute novamente.
  pause
  exit /b 1
)
uv sync --frozen
if errorlevel 1 (
  echo Não foi possível preparar as dependências. Confira a mensagem acima e a conexão.
  pause
  exit /b 1
)
uv run --no-sync python main.py %*
set "launcher_exit=%errorlevel%"
pause
exit /b %launcher_exit%
