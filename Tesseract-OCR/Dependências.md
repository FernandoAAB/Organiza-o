# Guia de Requisitos e Instalação

## TESSERACT PORTÁTIL

Esta pasta contém uma cópia portátil do Tesseract OCR e o modelo `por` usado
pela aplicação. Não é necessário instalar o Tesseract no Windows: mantenha
`tesseract.exe` e a pasta `tessdata` junto do `main.py`.

Como esses arquivos ainda não estão versionados pelo Git, inclua a pasta
`Tesseract-OCR` ao distribuir ou publicar o projeto. Sem ela, o aplicativo
tentará encontrar uma instalação do Tesseract no sistema e, se não encontrar,
permitirá apenas o preenchimento manual dos campos.

## REQUISITOS, PROGRAMAS E MODELOS
- **Programa:**
  - Ollama ([Site Oficial](https://ollama.com/))
  - Tesseract OCR ([Site Oficial](https://tesseractocr.org/pt/)) (https://github.com/UB-Mannheim/tesseract/wiki)
  - Yolo11n.pt ([Site Oficial](https://www.ultralytics.com/pt/yolo))

---

## INSTALAÇÃO DE MODELOS COM OLLAMA
- **Modelos:**
  - `qwen2.5:3b` *(Modelo opcional; melhor modelo recomendado: "mistral:7b-instruct-q4_K_M")*
  - `llama3.2:1b`
  - `nomic-embed-text:latest`

Execute os seguintes comandos no terminal:

```bash
ollama pull qwen2.5:3b
ollama pull llama3.2:1b
ollama pull nomic-embed-text:latest