# Orientações para manutenção

Este é um aplicativo desktop em português, usado para conferir registros financeiros.

- Antes de mudar comparação, pesquisa, numeração ou arquivos, leia **Uso e comparação**
  no [README](README.md). Essa é a referência das regras do aplicativo.
- Preserve os nomes dos controles, Aparência, referências de linha e cores de
  conferência aprovados. Limite mudanças visuais ao que foi solicitado.
- Reproduza um defeito antes de corrigir. Para regressões, exercite as interfaces
  já usadas em `tests/test_lancamentos.py` e `tests/test_interface.py`, com resultados
  esperados independentes do algoritmo. Faça uma correção verificável por vez.
- Use arquivos temporários e dados fictícios nos testes e nas capturas. Os arquivos
  `a1.txt`, `a2.txt` e a pasta `No/` são dados locais do usuário.
- Consulte **Desenvolvimento e validação** no [README](README.md) para executar os
  testes. Diferencie testes aprovados, ignorados e não executados; valide a interface
  com sessão gráfica quando alterar seus controles ou comportamento.
- Faça refatorações apenas quando simplificarem uma mudança concreta. Mantenha
  dependências e `uv.lock` coerentes; use instalação com lockfile congelado.
- Antes de publicar uma alteração autorizada, revise o diff e execute os testes
  pertinentes. Informe o que foi verificado e as limitações que restarem.
