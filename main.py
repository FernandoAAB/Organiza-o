import json
import os
import re
import webbrowser
import tkinter as tk
from collections import Counter
from datetime import datetime
from decimal import Decimal
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile
from tkinter import ttk, messagebox
from tkinter import font as tkfont

import customtkinter as ctk  # pip install customtkinter

ARQUIVO_ORIGEM = "a1.txt"
ARQUIVO_DESTINO = "a2.txt"
PASTA_REG = "No"
CONFIG = os.path.join(PASTA_REG, "config.json")


# TEMAS  (cada cor: (claro, escuro))

TEMAS = {
    "bg": ("#f1f5f9", "#0f172a"),
    "painel": ("#ffffff", "#162130"),
    "superficie": ("#ffffff", "#1b283a"),
    "borda": ("#d1d5db", "#2b394d"),
    "campo": ("#e2e8f0", "#243448"),
    "campo_hover": ("#cbd5e1", "#33455c"),
    "selecao": ("#dbeafe", "#163f73"),
    "texto": ("#0f172a", "#f8fafc"),
    "cinza": ("#64748b", "#94a3b8"),
    "cabecalho": ("#475569", "#cbd5e1"),
    "verde": ("#16a34a", "#4ade80"),
    "vermelho": ("#e11d48", "#fb7185"),
    "marcado": ("#fef08a", "#3b2d54"),
    "perigo": ("#ffe4e6", "#4c1d24"),
    "perigo_hover": ("#fecdd3", "#6b2129"),
}

ACENTOS = {  # (normal, hover)
    "Índigo": ("#6366f1", "#4f46e5"),
    "Ciano": ("#06b6d4", "#0891b2"),
    "Violeta": ("#8b5cf6", "#7c3aed"),
    "Esmeralda": ("#10b981", "#059669"),
    "Laranja": ("#f97316", "#ea580c"),
    "Azul": ("#3b82f6", "#2563eb"),
}



def c(chave):
    """Cor com as duas variações (CustomTkinter troca sozinho)."""
    return TEMAS[chave]


def cm(chave, modo):
    """Cor única para widgets ttk, conforme o modo atual."""
    return TEMAS[chave][0 if modo == "Claro" else 1]


def carregar_config():
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict):
            return "Escuro", "Azul"
        modo = dados.get("tema", "Escuro")
        acento = dados.get("acento", "Azul")
        return (modo if modo in ("Escuro", "Claro") else "Escuro",
                acento if isinstance(acento, str) and acento in ACENTOS else "Azul")
    except (OSError, ValueError):
        return "Escuro", "Azul"


def salvar_config(modo, acento):
    try:
        os.makedirs(PASTA_REG, exist_ok=True)
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump({"tema": modo, "acento": acento}, f)
    except OSError:
        pass



# LÓGICA (mesmas regras do script original)

def inicializar_arquivos():
    for arquivo in (ARQUIVO_ORIGEM, ARQUIVO_DESTINO):
        if not os.path.exists(arquivo):
            open(arquivo, "w", encoding="utf-8").close()
    caminho_log = os.path.join(PASTA_REG, "data.log")
    if not os.path.exists(PASTA_REG):
        os.makedirs(PASTA_REG)
        with open(caminho_log, "w", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%d/%m/%Y"))
    else:
        verificar_dias()


def verificar_dias():
    caminho_log = os.path.join(PASTA_REG, "data.log")
    if not os.path.exists(caminho_log):
        return
    try:
        with open(caminho_log, "r", encoding="utf-8") as f:
            data_inicial = datetime.strptime(f.read().strip(), "%d/%m/%Y")
        dias = (datetime.now() - data_inicial).days
        with open(os.path.join(PASTA_REG, "data1.log"), "w", encoding="utf-8") as f:
            f.write(f"A diferença de dias é: {dias}")
    except ValueError:
        pass


def carregar_linhas(nome_arquivo):
    if not os.path.exists(nome_arquivo):
        return []
    with open(nome_arquivo, "r", encoding="utf-8-sig") as f:
        return [l.strip() for l in f if l.strip()]


def carregar_origem_numerada():
    """[(numero_da_linha, texto), ...] sem modificar o a1.txt"""
    if not os.path.exists(ARQUIVO_ORIGEM):
        return []
    linhas = []
    with open(ARQUIVO_ORIGEM, "r", encoding="utf-8-sig") as f:
        for numero, linha in enumerate(f, start=1):
            linha = linha.strip()
            if linha:
                linhas.append((numero, linha))
    return linhas


def salvar_linhas(nome_arquivo, linhas):
    """Substitui o arquivo somente depois de gravar todo o conteúdo."""
    caminho = Path(nome_arquivo).absolute()
    temporario = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=caminho.parent,
                                delete=False) as f:
            temporario = Path(f.name)
            for linha in linhas:
                f.write(linha + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporario, caminho)
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)


def extrair_numero(linha):
    try:
        if linha.startswith("["):
            return int(linha[1:linha.index("]")])
    except (ValueError, IndexError):
        pass
    return 999999


def extrair_texto_registro(item):
    if item.startswith("["):
        try:
            return item[item.index("]") + 1:].strip()
        except ValueError:
            pass
    return item


def obter_destino_ordenado():
    return sorted(carregar_linhas(ARQUIVO_DESTINO), key=extrair_numero)


def extrair_lancamento(texto):
    """Retorna (D/C, valor) do primeiro lançamento em formato brasileiro."""
    encontrado = re.search(
        r"(?<![0-9.,+\-])[+\-]?([0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)"
        r"(,[0-9]{1,2})?\s*([DC])\b", texto.strip().upper()
    )
    if encontrado is None:
        return None
    inteiro, centavos, tipo = encontrado.groups()
    valor = Decimal(inteiro.replace(".", "") + (centavos or "").replace(",", "."))
    return tipo, valor


def extrair_valor_debito(texto):
    lancamento = extrair_lancamento(texto)
    return lancamento[1] if lancamento is not None and lancamento[0] == "D" else None


def referencias_no_destino(origem, destino):
    """Valida a referência e o texto, tolerando diferenças de espaçamento."""
    textos = {numero: " ".join(texto.split()) for numero, texto in origem}
    conferidos = set()
    for item in destino:
        referencia = re.fullmatch(r"\[(\d+)\]\s*(.*)", item)
        if referencia is not None:
            numero = int(referencia[1])
            if textos.get(numero) == " ".join(referencia[2].split()):
                conferidos.add(numero)
    return conferidos


def carregar_lancamentos_origem():
    """Ignora saldos e resumos do extrato, mantendo as linhas originais."""
    origem = carregar_origem_numerada()
    extrato = any(texto.upper() == "LANÇAMENTOS" for _, texto in origem)
    secao = None
    resultado = []
    for numero, texto in origem:
        titulo = texto.upper()
        if extrato:
            if titulo in ("LANÇAMENTOS", "LANÇAMENTOS FUTUROS", "RESUMO"):
                secao = titulo
            if secao not in ("LANÇAMENTOS", "LANÇAMENTOS FUTUROS"):
                continue
            if not re.match(r"^\d{2}/\d{2}/\d{4}\s", texto):
                continue
        if re.match(r"^(?:\d{2}/\d{2}/\d{4}\s+)?SALDO "
                    r"(?:DO DIA|ANTERIOR|BLOQUEADO ANTERIOR)(?:\s|$)", titulo):
            continue
        valor = extrair_lancamento(texto)
        if valor is not None:
            resultado.append((numero, texto, valor))
    return resultado


def corresponde(termo, texto):
    """Busca normal + busca numérica tolerante.

    1453,30 / 1.453,30 / 145330 encontram qualquer valor 1.453,30.
    """
    t = termo.strip().lower()
    if not t:
        return True
    if t in texto.lower():
        return True
    if re.fullmatch(r"[\d\.,\s]+", t):
        digitos = re.sub(r"\D", "", t)
        if digitos:
            for token in re.findall(r"\d[\d\.,]*", texto):
                if digitos in re.sub(r"\D", "", token):
                    return True
    return False


def calcular_lancamentos(tipo=None, termo=""):
    """Compara por (D/C, valor), preservando a referência e as ocorrências."""
    lancamentos_a2 = Counter()
    itens_a2 = carregar_linhas(ARQUIVO_DESTINO)
    origem = carregar_lancamentos_origem()
    conferidos = referencias_no_destino([(n, texto) for n, texto, _ in origem], itens_a2)
    # Uma referência inválida ou repetida não pode conferir outra linha apenas
    # por ter o mesmo valor. A comparação por valor atende só itens sem referência.
    for item in itens_a2:
        if re.match(r"^\[\d+\]", item):
            continue
        valor = extrair_lancamento(item)
        if valor is not None:
            lancamentos_a2[valor] += 1

    resultado = []
    for numero, texto, valor in origem:
        ok = numero in conferidos or lancamentos_a2[valor] > 0
        if ok and numero not in conferidos:
            lancamentos_a2[valor] -= 1
        resultado.append((numero, texto, ok))
    # A busca acontece após a conferência completa, para não redistribuir
    # ocorrências de mesmo valor quando apenas parte da lista está visível.
    resultado = [(n, texto, ok) for n, texto, ok in resultado
                 if (tipo is None or extrair_lancamento(texto)[0] == tipo)
                 and corresponde(termo, texto)]
    return resultado, len(resultado), sum(not ok for _, _, ok in resultado)


def calcular_debitos():
    return calcular_lancamentos("D")


def gerar_relatorio_html(tipo=None, termo=""):
    resultado, total, faltando = calcular_lancamentos(tipo, termo)
    categoria = {None: "Débitos e Créditos", "D": "Débitos", "C": "Créditos"}[tipo]
    linhas = ""
    for ordem, (numero, texto, ok) in enumerate(resultado, start=1):
        texto = escape(texto)
        if ok:
            linhas += (f'<tr><td>{ordem}</td><td style="text-align:center;">{numero}</td><td>{texto}</td>'
                       f'<td style="text-align:center;"><span class="ok">OK</span></td></tr>')
        else:
            linhas += (f'<tr style="color:red;font-weight:bold;"><td>{ordem}</td><td style="text-align:center;">{numero}</td>'
                       f'<td>{texto}</td><td style="text-align:center;"><span class="falta">FALTA NO A2</span></td></tr>')

    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<title>Comparação de {categoria} - A1 x A2</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; }}
h2, p {{ text-align: center; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
th, td {{ border: 1px solid #ccc; padding: 10px 12px; font-size: 14px; line-height: 1.5; }}
td:nth-child(3) {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
th {{ background-color: #f4f4f4; }}
.ok {{ color: green; font-weight: bold; }}
.falta {{ color: red; font-weight: bold; }}
@media print {{ .nao-imprimir {{ display: none; }} }}
</style></head><body>
<h2>Relatório de Comparação de {categoria}: A1 x A2</h2>
<p>Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
<p>Pesquisa: {escape(termo.strip()) or 'Todos os registros'}</p>
<table><thead><tr>
<th>Nº</th><th>Linha A1</th><th>Registro</th><th>Situação</th>
</tr></thead><tbody>{linhas}</tbody></table>
<p><b>Lançamentos no A1:</b> {total} | <b>Faltando no A2:</b> {faltando}</p>
<div class="nao-imprimir" style="text-align:center;margin-top:30px;">
<button onclick="window.print();" style="padding:10px 20px;font-size:16px;cursor:pointer;background:#007BFF;color:#fff;border:none;border-radius:5px;">Imprimir Relatório</button>
</div></body></html>"""

    os.makedirs(PASTA_REG, exist_ok=True)
    caminho = os.path.join(PASTA_REG, "relatorio_debitos.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)
    webbrowser.open(Path(caminho).resolve().as_uri())
    return caminho



# INTERFACE

FONTE = "Segoe UI"


def formatar_valor_registro(texto):
    lancamento = extrair_lancamento(texto)
    if lancamento is None:
        return ""
    tipo, valor = lancamento
    numero = f"{valor:,.2f}".translate(str.maketrans({",": ".", ".": ","}))
    return f"{numero} {tipo}"


def estilizar_tabelas(modo, acento):
    st = ttk.Style()
    st.theme_use("clam")
    st.configure("Treeview", background=cm("painel", modo),
                 fieldbackground=cm("painel", modo), foreground=cm("texto", modo),
                 rowheight=36, borderwidth=0, font=(FONTE, 12))
    st.configure("Treeview.Heading", background=cm("bg", modo),
                 foreground=cm("cabecalho", modo), relief="flat", borderwidth=0,
                 padding=(8, 7), font=(FONTE, 11, "bold"))
    st.map("Treeview", background=[("selected", cm("selecao", modo))], foreground=[])
    st.map("Origem.Treeview", background=[("selected", acento if modo == "Claro" else cm("selecao", modo))],
           foreground=[("selected", "#ffffff")])
    st.map("Treeview.Heading", background=[("active", cm("bg", modo))])
    st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])


class App(ctk.CTk):
    def __init__(self):
        global FONTE
        # Sem a fonte de formas, o fallback por círculos deixa sobras nas
        # bordas dos controles. Polígonos dispensam essa fonte e evitam as sobras.
        if ctk.DrawEngine.preferred_drawing_method == "circle_shapes":
            ctk.DrawEngine.preferred_drawing_method = "polygon_shapes"
        super().__init__()
        if FONTE not in tkfont.families(self):
            FONTE = tkfont.nametofont("TkDefaultFont", root=self).actual("family")
        self.modo, self.acento = carregar_config()
        ctk.set_appearance_mode("dark" if self.modo == "Escuro" else "light")
        self.primarios = []  # botões que usam a cor de destaque
        self.resultados = []
        self.termo_busca = ""
        self._sincronizando_selecao = False

        self.title("Sistema de Busca e Ordenação")
        largura = max(960, min(1360, self._reverse_window_scaling(self.winfo_screenwidth()) - 40))
        altura = max(560, min(820, self._reverse_window_scaling(self.winfo_screenheight()) - 100))
        self.geometry(f"{largura}x{altura}")
        self.minsize(960, 560)
        self.configure(fg_color=c("bg"))

        self._montar_cabecalho()

        self.status = tk.StringVar(value="Pronto.")
        self.label_status = ctk.CTkLabel(self, textvariable=self.status, anchor="w",
                                        justify="left", text_color=c("cinza"), font=(FONTE, 12))
        self.label_status.pack(side="bottom", fill="x", padx=18, pady=(0, 10))
        self.label_status.bind("<Configure>", self.ajustar_status)

        self.abas = ctk.CTkTabview(
            self, corner_radius=14, fg_color=c("superficie"),
            segmented_button_fg_color=c("campo"),
            segmented_button_unselected_color=c("campo"),
            segmented_button_unselected_hover_color=c("campo_hover"),
            segmented_button_font=(FONTE, 14, "bold"),
            text_color=("#111827", "#ffffff"),
            command=self.atualizar_tudo)
        self.abas.pack(fill="both", expand=True, padx=16, pady=(12, 6))
        self.aba_busca = self.abas.add("Buscar e comparar")
        self.aba_a2 = self.abas.add("Lista A2")
        self.aba_a2.configure(fg_color=c("painel"), border_width=1, border_color=c("borda"), corner_radius=12)

        self._montar_aba_busca()
        self._montar_aba_a2()
        self._montar_aba_debitos()
        self.aplicar_tema()
        self.atualizar_tudo()

    def report_callback_exception(self, exc, valor, traceback):
        """Apresenta erros de arquivo sem deixar a ação falhar silenciosamente."""
        if issubclass(exc, (OSError, UnicodeError)):
            self.status.set("Não foi possível concluir a operação com os arquivos.")
            messagebox.showerror("Erro ao acessar arquivos", str(valor), parent=self)
        else:
            super().report_callback_exception(exc, valor, traceback)

    def ajustar_status(self, evento):
        largura = max(1, self.label_status._reverse_widget_scaling(self.label_status.winfo_width()))
        if self.label_status.cget("wraplength") != largura:
            self.label_status.configure(wraplength=largura)

    #  componentes reutilizáveis 
    def botao(self, pai, texto, comando, primario=False, perigo=False, largura=170, altura=46):
        if perigo:
            kw = dict(fg_color=c("perigo"), hover_color=c("perigo_hover"),
                      text_color=c("vermelho"))
        elif primario:
            kw = dict(fg_color=ACENTOS[self.acento][0],
                      hover_color=ACENTOS[self.acento][1], text_color="#ffffff")
        else:
            kw = dict(fg_color=c("campo"), hover_color=c("campo_hover"),
                      text_color=c("texto"))
        b = ctk.CTkButton(pai, text=texto, command=comando, width=largura, height=altura,
                          corner_radius=10, font=(FONTE, 14, "bold"), **kw)
        if primario:
            self.primarios.append(b)
        return b

    def campo(self, pai, var, placeholder, largura=380):
        return ctk.CTkEntry(pai, textvariable=var, height=42, width=largura,
                            corner_radius=10, border_width=0, fg_color=c("campo"),
                            text_color=c("texto"), placeholder_text=placeholder,
                            placeholder_text_color=c("cinza"), font=(FONTE, 14))

    @staticmethod
    def _tabela(pai, colunas, larguras):
        frame = ctk.CTkFrame(pai, fg_color="transparent", corner_radius=0)
        tree = ttk.Treeview(frame, columns=[c_[0] for c_ in colunas],
                            show="headings", selectmode="extended", style="Origem.Treeview")
        for (cid, titulo), larg in zip(colunas, larguras):
            alin = "w" if cid == "texto" else "e" if cid == "valor" else "center"
            tree.heading(cid, text=titulo, anchor=alin)
            tree.column(cid, width=larg or 300, minwidth=larg or 140,
                        stretch=(larg == 0), anchor=alin)
        tree.column("texto", minwidth=140)
        sb = ctk.CTkScrollbar(frame, command=tree.yview)
        horizontal = ctk.CTkScrollbar(frame, orientation="horizontal", command=tree.xview)
        def atualizar_barra(barra, inicio, fim):
            barra.set(inicio, fim)
            necessaria = float(inicio) > 0 or float(fim) < 1
            if necessaria and not barra.winfo_manager():
                barra.grid()
            elif not necessaria and barra.winfo_manager():
                barra.grid_remove()

        tree.configure(yscrollcommand=lambda inicio, fim: atualizar_barra(sb, inicio, fim),
                       xscrollcommand=lambda inicio, fim: atualizar_barra(horizontal, inicio, fim))
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        horizontal.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        return frame, tree

    @staticmethod
    def ajustar_largura_registro(tree):
        """Mantém o registro inteiro acessível pela rolagem horizontal."""
        fonte = tkfont.Font(root=tree, font=ttk.Style(tree).lookup("Treeview", "font"))
        largura = max((fonte.measure(tree.set(iid, "texto")) + 32
                       for iid in tree.get_children()), default=140)
        tree.column("texto", width=max(140, largura), minwidth=max(140, largura))

    #  cabeçalho com seletor de tema 
    def _montar_cabecalho(self):
        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", padx=20, pady=(16, 0))
        ctk.CTkLabel(cab, text="Busca e Ordenação", text_color=c("texto"),
                     font=(FONTE, 24, "bold")).pack(side="left")

        self.botao(cab, "Aparência", self.alternar_aparencia,
                   largura=120, altura=36).pack(side="right")
        self.painel_aparencia = ctk.CTkFrame(self, fg_color="transparent")

        self.opt_acento = ctk.CTkOptionMenu(
            self.painel_aparencia, values=list(ACENTOS), command=self.mudar_acento, width=140, height=42,
            corner_radius=10, font=(FONTE, 14), dropdown_font=(FONTE, 14),
            fg_color=c("campo"), button_color=c("campo_hover"),
            button_hover_color=c("campo_hover"), text_color=c("texto"),
            dropdown_fg_color=c("painel"), dropdown_text_color=c("texto"),
            dropdown_hover_color=c("campo"))
        self.opt_acento.set(self.acento)
        self.opt_acento.pack(side="right")
        ctk.CTkLabel(self.painel_aparencia, text="Cor:", text_color=c("cinza"),
                     font=(FONTE, 13)).pack(side="right", padx=(18, 6))

        self.seg_tema = ctk.CTkSegmentedButton(
            self.painel_aparencia, values=["Escuro", "Claro"], command=self.mudar_tema, height=42,
            corner_radius=10, font=(FONTE, 14, "bold"), fg_color=c("campo"),
            unselected_color=c("campo"), unselected_hover_color=c("campo_hover"),
            text_color=("#111827", "#ffffff"))
        self.seg_tema.set(self.modo)
        self.seg_tema.pack(side="right")
        ctk.CTkLabel(self.painel_aparencia, text="Tema:", text_color=c("cinza"),
                     font=(FONTE, 13)).pack(side="right", padx=(18, 6))

    def alternar_aparencia(self):
        if self.painel_aparencia.winfo_manager():
            self.painel_aparencia.pack_forget()
        else:
            self.painel_aparencia.pack(before=self.abas, fill="x", padx=20, pady=(12, 0))

    def mudar_tema(self, modo):
        self.modo = modo
        self.seg_tema.set(modo)
        ctk.set_appearance_mode("dark" if modo == "Escuro" else "light")
        self.aplicar_tema()
        salvar_config(self.modo, self.acento)
        self.status.set(f"Tema {modo.lower()} aplicado.")

    def mudar_acento(self, acento):
        self.acento = acento
        self.opt_acento.set(acento)
        self.aplicar_tema()
        salvar_config(self.modo, self.acento)
        self.status.set(f"Cor de destaque: {acento}.")

    def aplicar_tema(self):
        normal, hover = ACENTOS[self.acento]
        # widgets CustomTkinter com cor de destaque
        for b in self.primarios:
            b.configure(fg_color=normal, hover_color=hover)
        if self.botao_adicionar.cget("state") == "disabled":
            self.botao_adicionar.configure(fg_color=c("campo"), text_color_disabled=c("cinza"))
        self.abas.configure(segmented_button_selected_color=normal,
                            segmented_button_selected_hover_color=hover)
        self.seg_tema.configure(selected_color=normal, selected_hover_color=hover)
        # tabelas (ttk) precisam ser reestilizadas
        estilizar_tabelas(self.modo, normal)
        self.tree_busca.tag_configure("ja", foreground=cm("cinza", self.modo))
        self.tree_busca.tag_configure("novo", foreground=cm("texto", self.modo))
        self.tree_deb.tag_configure("falta", foreground=cm("vermelho", self.modo))
        self.tree_deb.tag_configure("ok", foreground=cm("verde", self.modo))
        self.divisao.configure(bg=cm("superficie", self.modo))

    #  aba 1: buscar no A1 
    def _montar_aba_busca(self):
        topo = ctk.CTkFrame(self.aba_busca, fg_color="transparent")
        topo.pack(fill="x", padx=12, pady=(12, 12))
        self.busca_var = tk.StringVar()
        ctk.CTkLabel(topo, text="Pesquisar", font=(FONTE, 14),
                     text_color=c("cinza")).pack(side="left", padx=(0, 12))
        entrada = self.campo(topo, self.busca_var, "Texto, data ou valor")
        entrada.pack(side="left", fill="x", expand=True)
        entrada.bind("<Return>", lambda e: self.buscar_a1())
        entrada.focus_set()
        self.botao(topo, "Buscar", self.buscar_a1, largura=110, altura=42).pack(side="left", padx=10)
        self.botao(topo, "Limpar", self.mostrar_todos, largura=90, altura=42).pack(side="left")
        self.divisao = tk.PanedWindow(self.aba_busca, orient="horizontal", sashwidth=12,
                                     bd=0, sashrelief="flat", showhandle=False,
                                     bg=cm("superficie", self.modo), opaqueresize=True)
        self.divisao.pack(fill="both", expand=True)
        self.painel_busca = ctk.CTkFrame(self.divisao, bg_color=c("superficie"), fg_color=c("painel"),
                                       border_width=1, border_color=c("borda"), corner_radius=12)
        self.aba_deb = ctk.CTkFrame(self.divisao, bg_color=c("superficie"), fg_color=c("painel"),
                                  border_width=1, border_color=c("borda"), corner_radius=12)
        self.divisao.add(self.painel_busca, minsize=380, stretch="always", width=600)
        self.divisao.add(self.aba_deb, minsize=440, stretch="always")
        self._divisao_posicionada = False
        self.divisao.bind("<Configure>", self.posicionar_divisao)
        for painel in (self.painel_busca, self.aba_deb):
            painel.grid_columnconfigure(0, weight=1)
            painel.grid_rowconfigure(0, minsize=48)
            painel.grid_rowconfigure(1, weight=1)
            painel.grid_rowconfigure(2, minsize=44)
        cabecalho = ctk.CTkFrame(self.painel_busca, fg_color="transparent")
        cabecalho.grid(row=0, column=0, sticky="ew", padx=12, pady=6)
        cabecalho.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(cabecalho, text="Registros do A1",
                    font=(FONTE, 18, "bold"), text_color=c("texto")).grid(row=0, column=0, sticky="w")
        self.resumo_origem = tk.StringVar()
        ctk.CTkLabel(cabecalho, textvariable=self.resumo_origem,
                    text_color=c("cinza"), font=(FONTE, 12)).grid(row=0, column=1, sticky="e", padx=(12, 0))

        frame, self.tree_busca = self._tabela(
            self.painel_busca, [("ordem", "Nº"), ("linha", "Linha A1"), ("texto", "Registro"),
                                ("situacao", "No A2"), ("valor", "Valor")],
            [42, 80, 0, 80, 128])
        frame.grid(row=1, column=0, sticky="nsew", padx=12)
        self.tree_busca.configure(displaycolumns=("ordem", "linha", "situacao", "valor", "texto"))
        rodape = ctk.CTkFrame(self.painel_busca, fg_color="transparent")
        rodape.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        self.resumo_selecao = tk.StringVar(value="Nenhum selecionado")
        ctk.CTkLabel(rodape, textvariable=self.resumo_selecao,
                     text_color=c("cinza"), font=(FONTE, 12)).pack(side="left")
        self.botao_adicionar = self.botao(rodape, "Adicionar ao A2", self.adicionar_e_comparar,
                                          primario=True, largura=180, altura=32)
        self.botao_adicionar.pack(side="right")
        self.botao_adicionar.configure(state="disabled")
        self.tree_busca.bind("<Double-1>", self.adicionar_por_duplo_clique)
        self.tree_busca.bind("<<TreeviewSelect>>", self.atualizar_selecao_origem)

    def atualizar_selecao_origem(self, evento=None):
        quantidade = len(self.tree_busca.selection())
        self.resumo_selecao.set("1 selecionado" if quantidade == 1 else
                               f"{quantidade} selecionados" if quantidade else "Nenhum selecionado")
        self.botao_adicionar.configure(state="normal" if quantidade else "disabled")
        self.botao_adicionar.configure(fg_color=ACENTOS[self.acento][0] if quantidade else c("campo"),
                                       text_color_disabled=c("cinza"))
        self.sincronizar_selecao(self.tree_busca, self.tree_deb)

    def posicionar_divisao(self, evento):
        for painel, minimo in ((self.painel_busca, 380), (self.aba_deb, 440)):
            largura = round(painel._apply_widget_scaling(minimo))
            if int(self.divisao.panecget(painel, "minsize")) != largura:
                self.divisao.paneconfigure(painel, minsize=largura)
            altura = round(painel._apply_widget_scaling(48))
            if painel.grid_rowconfigure(0)["minsize"] != altura:
                painel.grid_rowconfigure(0, minsize=altura)
        if not self._divisao_posicionada:
            self._divisao_posicionada = True
            self.after_idle(lambda: self.divisao.sash_place(0, self.divisao.winfo_width() // 2, 0))

    def buscar_a1(self):
        self.termo_busca = self.busca_var.get().strip()
        termo = self.termo_busca.lower()
        self.tree_busca.delete(*self.tree_busca.get_children())
        self.resultados = []
        origem = carregar_origem_numerada()
        conferidos = referencias_no_destino(origem, carregar_linhas(ARQUIVO_DESTINO))
        self.resultados = [(n, t) for n, t in origem if corresponde(termo, t)]
        for i, (n, t) in enumerate(self.resultados):
            ja = n in conferidos
            self.tree_busca.insert("", "end", iid=str(i),
                                   values=(i + 1, n, t, "✓ no A2" if ja else "", formatar_valor_registro(t)),
                                   tags=("ja" if ja else "novo",))
        self.ajustar_largura_registro(self.tree_busca)
        self.resumo_origem.set(f"{len(self.resultados)} registros disponíveis")
        self.atualizar_selecao_origem()
        if termo:
            self.status.set(f"{len(self.resultados)} resultado(s) para '{termo}'.")
        else:
            self.status.set(f"A1: {len(self.resultados)} registro(s) exibido(s).")
        self.atualizar_debitos()

    def sincronizar_selecao(self, origem, destino):
        if self._sincronizando_selecao:
            return
        numeros = {origem.set(iid, "linha") for iid in origem.selection()}
        selecao = tuple(iid for iid in destino.get_children() if destino.set(iid, "linha") in numeros)
        if destino.selection() != selecao:
            self._sincronizando_selecao = True
            destino.selection_set(*selecao)
            if selecao:
                destino.see(selecao[0])
            self.after_idle(lambda: setattr(self, "_sincronizando_selecao", False))

    def mostrar_todos(self):
        self.busca_var.set("")
        self.buscar_a1()

    def adicionar_e_comparar(self):
        self.adicionar_selecionados(comparar=True)

    def adicionar_por_duplo_clique(self, evento):
        if self.tree_busca.identify_region(evento.x, evento.y) != "cell":
            return
        item = self.tree_busca.identify_row(evento.y)
        if item:
            self.tree_busca.selection_set(item)
            self.adicionar_e_comparar()
            return "break"

    def adicionar_selecionados(self, comparar=False):
        sel = self.tree_busca.selection()
        if not sel:
            self.status.set("Selecione um ou mais registros para adicionar.")
            return
        selecionados_origem = [self.resultados[int(iid)] for iid in sel]
        origem_atual = dict(carregar_origem_numerada())
        if any(origem_atual.get(numero) != texto for numero, texto in selecionados_origem):
            self.buscar_a1()
            self.status.set("O A1 foi alterado. Confira os registros e selecione novamente.")
            return
        destino = carregar_linhas(ARQUIVO_DESTINO)
        conferidos = referencias_no_destino(list(origem_atual.items()), destino)
        adicionados = 0
        numeros = set()
        for numero, texto in selecionados_origem:
            numeros.add(numero)
            item = f"[{numero}] {texto}"
            if numero not in conferidos:
                destino.append(item)
                adicionados += 1
        destino.sort(key=extrair_numero)
        salvar_linhas(ARQUIVO_DESTINO, destino)
        self.buscar_a1()
        self.tree_busca.selection_set(*(iid for iid in self.tree_busca.get_children()
                                       if int(self.tree_busca.set(iid, "linha")) in numeros))
        self.atualizar_a2()
        self.atualizar_debitos()
        self.status.set(f"✓ {adicionados} registro(s) adicionado(s) ao A2.")
        if comparar:
            self.tipo_comparacao.set("Todos")
            self.atualizar_debitos()
            self.abas.set("Buscar e comparar")
            selecionados = [iid for iid in self.tree_deb.get_children()
                            if int(self.tree_deb.set(iid, "linha")) in numeros]
            self.tree_deb.selection_set(*selecionados)
            if selecionados:
                self.tree_deb.focus(selecionados[0])
                self.tree_deb.see(selecionados[0])
            self.status.set(f"{adicionados} adicionado(s) ao A2; "
                            f"{len(selecionados)} lançamento(s) selecionado(s) na comparação. "
                            "Saldos, resumos e registros sem D/C não entram na comparação.")

    #  aba 2: lista A2 
    def _montar_aba_a2(self):
        topo = ctk.CTkFrame(self.aba_a2, fg_color="transparent")
        topo.pack(fill="x", padx=12, pady=(10, 12))
        topo.grid_columnconfigure(1, weight=1)
        self.filtro_a2 = tk.StringVar()
        self.filtro_a2.trace_add("write", lambda *a: self.atualizar_a2())
        ctk.CTkLabel(topo, text="Filtrar", font=(FONTE, 14),
                     text_color=c("cinza")).grid(row=0, column=0, padx=(0, 12))
        self.campo(topo, self.filtro_a2, "Filtrar lista...").grid(row=0, column=1, sticky="ew")
        self.botao(topo, "Remover", self.remover_a2, perigo=True, largura=140, altura=42).grid(
            row=0, column=2, padx=10)
        self.botao(topo, "Exportar N.txt", self.exportar, largura=170, altura=42).grid(row=0, column=3)

        frame, self.tree_a2 = self._tabela(
            self.aba_a2, [("ordem", "Nº"), ("linha", "Linha A1"), ("texto", "Registro"),
                          ("valor", "Valor")], [42, 80, 0, 128])
        self.tree_a2.configure(displaycolumns=("ordem", "linha", "valor", "texto"))
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def atualizar_a2(self):
        self.tree_a2.delete(*self.tree_a2.get_children())
        filtro = self.filtro_a2.get().strip().lower()
        total = 0
        self.itens_a2 = obter_destino_ordenado()
        for indice, item in enumerate(self.itens_a2):
            texto = extrair_texto_registro(item)
            if filtro and not corresponde(filtro, texto):
                continue
            total += 1
            numero = extrair_numero(item) if re.match(r"^\[\d+\]", item) else "—"
            self.tree_a2.insert("", "end", iid=str(indice), values=(total, numero, texto, formatar_valor_registro(texto)))
        self.ajustar_largura_registro(self.tree_a2)
        if self.abas.get() == "Lista A2":
            self.status.set(f"A2: {total} registro(s) exibido(s).")

    def remover_a2(self):
        sel = self.tree_a2.selection()
        if not sel:
            self.status.set("Selecione registros do A2 para remover.")
            return
        if not messagebox.askyesno("Remover", f"Remover {len(sel)} registro(s) do A2?"):
            return
        if obter_destino_ordenado() != self.itens_a2:
            self.atualizar_a2()
            self.status.set("O A2 foi alterado. Confira a lista e selecione novamente.")
            return
        indices = {int(iid) for iid in sel}
        restantes = [item for i, item in enumerate(self.itens_a2) if i not in indices]
        salvar_linhas(ARQUIVO_DESTINO, restantes)
        self.atualizar_a2()
        self.atualizar_debitos()
        self.buscar_a1()
        self.status.set(f"{len(sel)} registro(s) removido(s).")

    def exportar(self):
        os.makedirs(PASTA_REG, exist_ok=True)
        caminho = os.path.join(PASTA_REG, "N.txt")
        salvar_linhas(caminho, obter_destino_ordenado())
        self.status.set(f"✓ Exportado para {os.path.abspath(caminho)}")

    #  aba 3: comparação de débitos e créditos
    def _montar_aba_debitos(self):
        cabecalho = ctk.CTkFrame(self.aba_deb, fg_color="transparent")
        cabecalho.grid(row=0, column=0, sticky="ew", padx=12, pady=6)
        cabecalho.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(cabecalho, text="Conferência A1 × A2",
                    font=(FONTE, 18, "bold"), text_color=c("texto")).grid(row=0, column=0, sticky="w")
        rodape = ctk.CTkFrame(self.aba_deb, fg_color="transparent")
        rodape.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        self.tipo_comparacao = tk.StringVar(value="Todos")
        self.tipo_comparacao.trace_add("write", lambda *a: self.atualizar_debitos())
        ctk.CTkLabel(rodape, text="Mostrar:", text_color=c("cinza"),
                     font=(FONTE, 12)).pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(rodape, values=["Todos", "Débitos", "Créditos"],
                         variable=self.tipo_comparacao, width=120, height=32,
                         font=(FONTE, 13), dropdown_font=(FONTE, 13),
                         fg_color=c("campo"), button_color=c("campo_hover"),
                         button_hover_color=c("campo_hover"), text_color=c("texto"),
                         dropdown_fg_color=c("painel"), dropdown_text_color=c("texto"),
                         dropdown_hover_color=c("campo")).pack(side="left")
        self.var_total = tk.StringVar(value="0")
        self.var_falta = tk.StringVar(value="0")
        self.resumo_conferencia = tk.StringVar()
        ctk.CTkLabel(cabecalho, textvariable=self.resumo_conferencia,
                     text_color=c("cinza"), font=(FONTE, 12)).grid(row=0, column=1, sticky="e", padx=(12, 0))

        frame, self.tree_deb = self._tabela(
            self.aba_deb, [("ordem", "Nº"), ("linha", "Linha A1"), ("texto", "Registro"),
                           ("situacao", "Situação"), ("valor", "Valor")],
            [42, 80, 0, 128, 128])
        frame.grid(row=1, column=0, sticky="nsew", padx=12)
        self.tree_deb.configure(style="Treeview", displaycolumns=("ordem", "linha", "situacao", "valor", "texto"))
        self.botao(rodape, "Relatório", self.imprimir_relatorio,
                   largura=110, altura=32).pack(side="right")
        self.botao(rodape, "Atualizar", self.atualizar_tudo,
                   largura=110, altura=32).pack(side="right", padx=(0, 10))
        self.tree_deb.bind("<<TreeviewSelect>>", lambda e: self.sincronizar_selecao(self.tree_deb, self.tree_busca))

    def tipo_selecionado(self):
        return {"Todos": None, "Débitos": "D", "Créditos": "C"}[self.tipo_comparacao.get()]

    def imprimir_relatorio(self):
        caminho = gerar_relatorio_html(self.tipo_selecionado(), self.termo_busca)
        self.status.set(f"Relatório salvo em {os.path.abspath(caminho)}")

    def atualizar_debitos(self):
        self.tree_deb.delete(*self.tree_deb.get_children())
        resultado, total, faltando = calcular_lancamentos(self.tipo_selecionado(), self.termo_busca)
        for i, (numero, texto, ok) in enumerate(resultado):
            situacao = "OK" if ok else "FALTA NO A2"
            tags = ["ok" if ok else "falta"]
            self.tree_deb.insert("", "end", iid=str(i),
                                 values=(i + 1, numero, texto, situacao, formatar_valor_registro(texto)), tags=tuple(tags))
        self.ajustar_largura_registro(self.tree_deb)
        self.var_total.set(str(total))
        self.var_falta.set(str(faltando))
        self.resumo_conferencia.set(f"{total} exibidos · {faltando} faltando no A2")
        self.sincronizar_selecao(self.tree_busca, self.tree_deb)
        if self.abas.get() == "Buscar e comparar":
            self.status.set(f"A1: {len(self.resultados)} registros | Conferência: {total} lançamentos | Faltando: {faltando}")

    def atualizar_tudo(self):
        self.buscar_a1()
        self.atualizar_a2()
        self.atualizar_debitos()


if __name__ == "__main__":
    inicializar_arquivos()
    App().mainloop()
