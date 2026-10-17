# Organiza-o

Aplicativo desktop em português, feito com CustomTkinter, para pesquisar registros
do A1, organizar uma seleção no A2 e comparar débitos e créditos em um relatório imprimível.

## Telas atuais

Capturas reais do aplicativo com dados fictícios, sem alterar arquivos de uso.
A aparência das fontes pode variar conforme o sistema operacional.

### Tela inicial — Buscar e comparar

Reúne os registros do **A1 à esquerda** e a **conferência A1 × A2 à direita**.
Uma única pesquisa filtra os dois painéis. Ao selecionar e usar **Adicionar ao A2 →**,
a situação é atualizada ao lado, mantendo a pesquisa. Arraste a divisória central
para ajustar o espaço de cada painel.

Na conferência à direita, **Todos**, **Exibidos** e **Faltando no A2** ficam na
mesma linha, em uma faixa compacta. Os botões **Atualizar** e **Relatório** ficam
ao lado do título, deixando mais espaço vertical para os registros da tabela.
Esse layout está implementado no aplicativo; as imagens abaixo foram capturadas
da versão atualizada.

![Tela dividida com A1 à esquerda e comparação de oito lançamentos à direita](docs/images/tela-inicial.png)

### Lista A2

Mostra os registros escolhidos, mantendo a referência original do A1. Permite
filtrar, remover e exportar a seleção.

![Lista A2 com quatro registros selecionados e suas linhas originais](docs/images/lista-a2.png)

### Pesquisa compartilhada

Pesquisar `32000` encontra os registros de `320,00` nos dois lados. Neste exemplo,
o débito já está no A2 e o crédito ainda falta: o mesmo valor com tipos diferentes
é conferido separadamente. **Mostrar todos** limpa a pesquisa dos dois painéis.

![Pesquisa por 32000 nos dois painéis, com um débito conferido e um crédito faltando](docs/images/comparacao.png)

### Filtro de créditos

O filtro da direita permite conferir somente créditos ou somente débitos; o A1
continua disponível à esquerda. Os contadores e o relatório acompanham a pesquisa
e o tipo selecionado. A sequência **Nº** recomeça em 1 e **Linha A1** mantém a referência original.

![Filtro de créditos com três registros, um encontrado e dois faltando](docs/images/creditos.png)

### Referências anteriores

A [captura anterior da interface](Interface.png) e o [diagrama original](Diagrama.png)
foram preservados como referência histórica.

## Executar

Requer Python 3.11 ou superior, Tk e uma sessão gráfica. Com o [uv](https://docs.astral.sh/uv/),
execute na pasta do projeto:

```sh
uv sync --frozen
uv run --frozen python main.py
```

O aplicativo cria `a1.txt`, `a2.txt` e a pasta `No/` no diretório de execução.
Mantenha esse diretório ao reiniciar para acessar os mesmos dados. Esses arquivos
são locais e ignorados pelo Git; faça cópias de segurança dos registros importantes.

## Uso e comparação

1. Preencha `a1.txt` com um registro por linha. Linhas vazias são ignoradas,
   preservando a numeração original.
2. Em **Buscar e comparar**, digite texto, data ou valor e pressione Enter ou
   clique em **Buscar**. Por exemplo, `145330` encontra `1.453,30`.
   A pesquisa filtra simultaneamente o A1 e a comparação, preservando a ordem original.
3. Selecione os registros à esquerda e clique em **Adicionar ao A2 →**, ou use
   duplo clique. A indicação no A1 e a situação na direita são atualizadas sem
   trocar de aba. A seleção localiza a mesma linha no painel ao lado; Ctrl/Shift
   permite escolher vários registros. A comparação contém apenas registros com D/C.
4. Confira as pendências à direita. **Todos / Débitos / Créditos** filtra o tipo
   apenas nesse painel, e os contadores mostram as quantidades visíveis. **Relatório**
   abre `No/relatorio_debitos.html` no navegador, com a mesma pesquisa e tipo.
   O nome do arquivo foi mantido para compatibilidade; ele agora inclui créditos também.
5. Em **Lista A2**, filtre, remova registros ou exporte a seleção para `No/N.txt`.
   A exportação contém todo o A2, na ordem das linhas originais.

A pesquisa não muda o resultado da conferência: os lançamentos são comparados
antes de filtrar a visualização, evitando que uma busca altere qual ocorrência
de um valor repetido está marcada como OK. Pesquisar uma data busca esse texto
no registro; a ordenação permanece pela linha original, sem interpretar datas.

Um débito é identificado por um valor brasileiro seguido de `D`, por exemplo
`Cliente 1.453,30 D`. Um crédito termina em `C`, como `Cliente 100,00 C`.
Os marcadores D/C identificam a saída e a entrada; o sinal negativo não é exigido.
O formato original com valor colado no histórico (`ENVIO TED320,00 D`) também é aceito.
Valores como
`1.453,30` e `1453,3` são equivalentes. Os registros adicionados diretamente do A1
têm prioridade pela linha e pelo texto originais. As demais ocorrências no A2
são comparadas por valor, na ordem das linhas do A1. Cada ocorrência confere
apenas um lançamento do mesmo tipo: um crédito nunca confere um débito.
Dois créditos ou débitos de mesmo valor exigem duas ocorrências do respectivo tipo no A2.
**Situação** mostra `OK` ou `FALTA NO A2`; o valor permanece no registro e
a coluna **Tipo** distingue débito e crédito. Os contadores mostram quantidades de registros.
Linhas sem valor marcado com D/C, como `0SALDO DIA` no exemplo original,
continuam disponíveis no A1 e no A2, mas não entram na comparação financeira.

Todas as abas exibem **Nº** em ordem crescente de 1 até o fim da lista exibida,
sem limite de 30 registros. Ao filtrar A1 ou A2, essa sequência recomeça em 1.
**Linha A1** mantém a referência original, inclusive quando existem linhas vazias
ou registros que não são débitos. O A2 é exibido e exportado pela linha original do A1
(1, 2, 3…), independentemente da ordem de seleção. A numeração de
exibição não altera os arquivos nem os identificadores `[linha]` gravados no A2.
O relatório também contém as colunas **Nº** e **Linha A1**.

A ordem de referência é a sequência das linhas do A1. O identificador `[12]`
no A2 significa que o registro veio da linha 12 do A1; não representa o dia 12.
Códigos numéricos no começo do texto também não são tratados como datas.
Mesmo que uma descrição contenha datas, ela não muda a ordem original.
O arquivo de exemplo do commit `5ac63f7` contém 98 registros sem datas explícitas.

O relatório trata o conteúdo dos registros como texto, inclusive caracteres
como `<`, `>` e `&`. A impressão depende do navegador e da impressora disponível.

## Testes

```sh
uv run --frozen python -m unittest discover -s tests -v
```

Os testes usam arquivos temporários. Os testes da interface exigem uma tela X11
em Linux (`DISPLAY` configurado); sem ela, são indicados como ignorados. Em um
ambiente sem monitor, use uma tela virtual para executar também esses testes.
