# Comentários dos arquivos do projeto

O ZIP contém 55 arquivos. Este guia descreve a finalidade de cada um. Os módulos Python também contêm comentários no código.

Os componentes distribuídos com o Tesseract estão descritos aqui; seus arquivos binários e suas configurações originais foram preservados. Os perfis em `tessdata/configs/` são opções do Tesseract e não são todos ativados pela aplicação.

| Arquivo | Comentário |
| --- | --- |
| `.github/workflows/tests.yml` | Automatiza os testes em Windows e Linux com Python 3.11 e 3.12; prepara uma sessão gráfica virtual no Linux. |
| `.gitignore` | Exclui caches, ambientes virtuais e dados locais, como a pasta No/ e arquivos .txt. |
| `.python-version` | Indica a versão de Python preferida pelas ferramentas de ambiente. |
| `AGENTS.md` | Orienta a manutenção do projeto, a preservação das regras financeiras e a validação de alterações. |
| `Diagrama.png` | Imagem de diagrama fornecida com o projeto. |
| `Interface.png` | Imagem da interface fornecida com o projeto. |
| `README.md` | Explica instalação, uso, comparação A1 × A2, captura de documentos e validação. |
| `Tesseract-OCR/Dependências.md` | Reúne notas de distribuição do Tesseract portátil e referências de ferramentas e modelos. |
| `Tesseract-OCR/tessdata/configs/alto` | Ativa a saída XML ALTO. |
| `Tesseract-OCR/tessdata/configs/ambigs.train` | Configura o treinamento de ambiguidades e desativa dicionários nessa etapa. |
| `Tesseract-OCR/tessdata/configs/api_config` | Ativa a opção de rejeição zero do reconhecimento. |
| `Tesseract-OCR/tessdata/configs/bazaar` | Desativa dicionários padrão e define sufixos de palavras e padrões do usuário. |
| `Tesseract-OCR/tessdata/configs/bigram` | Habilita correção por bigramas e opções de diagnóstico. |
| `Tesseract-OCR/tessdata/configs/box.train` | Configura treinamento e segmentação com arquivos de caixas de caracteres. |
| `Tesseract-OCR/tessdata/configs/box.train.stderr` | Variante de configuração de treinamento com caixas, com opções próprias de rejeição e segmentação. |
| `Tesseract-OCR/tessdata/configs/digits` | Restringe os caracteres reconhecidos a dígitos, hífen e ponto. |
| `Tesseract-OCR/tessdata/configs/get.images` | Solicita a gravação das imagens processadas pelo Tesseract. |
| `Tesseract-OCR/tessdata/configs/hocr` | Ativa a saída hOCR e desativa informações de fonte nessa saída. |
| `Tesseract-OCR/tessdata/configs/inter` | Ativa visualizações interativas de diagnóstico. |
| `Tesseract-OCR/tessdata/configs/kannada` | Ajusta parâmetros de segmentação e inclinação para Kannada. |
| `Tesseract-OCR/tessdata/configs/linebox` | Reconstitui caixas de caracteres a partir de caixas de linhas. |
| `Tesseract-OCR/tessdata/configs/logfile` | Direciona o diagnóstico para tesseract.log. |
| `Tesseract-OCR/tessdata/configs/lstm.train` | Configura o treinamento do reconhecedor de linhas LSTM. |
| `Tesseract-OCR/tessdata/configs/lstmbox` | Ativa a saída de caixas no formato LSTM. |
| `Tesseract-OCR/tessdata/configs/lstmdebug` | Ativa níveis de diagnóstico do classificador e do modelo de linguagem. |
| `Tesseract-OCR/tessdata/configs/makebox` | Ativa a geração de caixas de caracteres. |
| `Tesseract-OCR/tessdata/configs/page` | Ativa a saída PAGE XML. |
| `Tesseract-OCR/tessdata/configs/pdf` | Ativa a geração de PDF pesquisável. |
| `Tesseract-OCR/tessdata/configs/quiet` | Direciona mensagens de diagnóstico para /dev/null. |
| `Tesseract-OCR/tessdata/configs/rebox` | Recalcula caixas a partir de caixas existentes. |
| `Tesseract-OCR/tessdata/configs/strokewidth` | Configura visualizações de diagnóstico da segmentação e da largura dos traços. |
| `Tesseract-OCR/tessdata/configs/tsv` | Ativa a saída tabular TSV. |
| `Tesseract-OCR/tessdata/configs/txt` | Ativa a saída de texto simples, podendo ser combinada com outros formatos. |
| `Tesseract-OCR/tessdata/configs/unlv` | Ativa a saída no formato UNLV e seu tratamento de caracteres rejeitados. |
| `Tesseract-OCR/tessdata/configs/wordstrbox` | Ativa a geração de caixas com texto de palavras. |
| `Tesseract-OCR/tessdata/osd.traineddata` | Modelo de detecção de orientação e sistema de escrita do Tesseract. |
| `Tesseract-OCR/tessdata/pdf.ttf` | Fonte usada pelo Tesseract na geração de PDFs pesquisáveis. |
| `Tesseract-OCR/tessdata/por.traineddata` | Modelo de reconhecimento de texto em português. |
| `Tesseract-OCR/tesseract.exe` | Executável do Tesseract para Windows, usado no reconhecimento óptico local. |
| `docs/images/comparacao.png` | Captura da tela de comparação A1 × A2 para a documentação. |
| `docs/images/creditos.png` | Captura do filtro de créditos para a documentação. |
| `docs/images/lista-a2.png` | Captura da aba Lista A2 para a documentação. |
| `docs/images/tela-inicial.png` | Captura da tela inicial para a documentação. |
| `docs/images/tema-claro.png` | Captura da interface em tema claro para a documentação. |
| `iniciar.bat` | Inicializador do Windows: verifica o uv, sincroniza dependências com o lockfile e executa main.py. |
| `main.py` | Implementa a interface desktop, leitura e gravação de A1/A2, comparação financeira, marcações de atenção, relatório e captura com OCR. |
| `ocr_paddle.py` | Adaptador opcional do PaddleOCR: inicializa modelos sob demanda, organiza palavras em linhas e sinaliza leituras incertas. |
| `pyproject.toml` | Define os metadados, a versão mínima de Python, as dependências principais e o extra opcional paddle. |
| `scripts/comparar_ocr.py` | Compara tempo, texto, campos e avisos dos motores Tesseract e PaddleOCR nas imagens indicadas. |
| `scripts/test.py` | Descobre e executa a suíte unittest; com --require-gui, falha também quando há testes ignorados. |
| `tests/test_interface.py` | Valida interações, filtros, tabelas, seleção, temas e dimensões da interface em sessão gráfica. |
| `tests/test_lancamentos.py` | Valida comparação financeira, pesquisa, referências de linha, relatório e captura com dados temporários. |
| `tests/test_ocr.py` | Valida a preservação de linhas e o tratamento de confiança e erros do Tesseract com resultados simulados. |
| `tests/test_paddle.py` | Valida a integração opcional, a ordem de leitura e os avisos do PaddleOCR usando simulações. |
| `uv.lock` | Fixa as versões e os artefatos das dependências para instalações reproduzíveis com uv sync --frozen. |
