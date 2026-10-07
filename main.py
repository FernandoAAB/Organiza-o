import json
import os
import re
import webbrowser
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

import customtkinter as ctk  # pip install customtkinter

ARQUIVO_ORIGEM = "a1.txt"
ARQUIVO_DESTINO = "a2.txt"
PASTA_REG = "No"
CONFIG = os.path.join(PASTA_REG, "config.json")


# TEMAS  (cada cor: (claro, escuro))

TEMAS = {
    "bg": ("#eef0f4", "#14151a"),
    "painel": ("#ffffff", "#1c1e26"),
    "campo": ("#e5e7eb", "#2a2d38"),
    "campo_hover": ("#d1d5db", "#353948"),
    "texto": ("#111827", "#e5e7eb"),
    "cinza": ("#6b7280", "#6b7280"),
    "cabecalho": ("#4b5563", "#9ca3af"),
    "verde": ("#15803d", "#4ade80"),
    "vermelho": ("#dc2626", "#f87171"),
    "marcado": ("#fef08a", "#4a3f0f"),
    "perigo": ("#fde2e4", "#3a1d22"),
    "perigo_hover": ("#fbcfd4", "#5a2530"),
}
ACENTOS = {  # (normal, hover)
    "Azul": ("#3b82f6", "#2563eb"),
    "Verde": ("#22c55e", "#16a34a"),
    "Roxo": ("#8b5cf6", "#7c3aed"),
    "Laranja": ("#f97316", "#ea580c"),
    "Rosa": ("#ec4899", "#db2777"),
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
        modo = dados.get("tema", "Escuro")
        acento = dados.get("acento", "Azul")
        return (modo if modo in ("Escuro", "Claro") else "Escuro",
                acento if acento in ACENTOS else "Azul")
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
    with open(nome_arquivo, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def carregar_origem_numerada():
    """[(numero_da_linha, texto), ...] sem modificar o a1.txt"""
    if not os.path.exists(ARQUIVO_ORIGEM):
        return []
    linhas = []
    with open(ARQUIVO_ORIGEM, "r", encoding="utf-8") as f:
        for numero, linha in enumerate(f, start=1):
            linha = linha.strip()
            if linha:
                linhas.append((numero, linha))
    return linhas


def salvar_linhas(nome_arquivo, linhas):
    with open(nome_arquivo, "w", encoding="utf-8") as f:
        for linha in linhas:
            f.write(linha + "\n")


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


def extrair_valor_debito(texto):
    encontrados = re.findall(r"(\d[\d\.,]*)\s*D\b", texto.strip().upper())
    return encontrados[0] if encontrados else None


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


def calcular_debitos():
    """Retorna (lista[(numero, texto, ok)], total, faltando)."""
    debitos_a2 = set()
    for item in carregar_linhas(ARQUIVO_DESTINO):
        valor = extrair_valor_debito(extrair_texto_registro(item))
        if valor is not None:
            debitos_a2.add(valor)

    resultado, faltando = [], 0
    for numero, texto in carregar_origem_numerada():
        valor = extrair_valor_debito(texto)
        if valor is None:
            continue
        ok = valor in debitos_a2
        if not ok:
            faltando += 1
        resultado.append((numero, texto, ok))
    return resultado, len(resultado), faltando


def gerar_relatorio_html():
    resultado, total, faltando = calcular_debitos()
    linhas = ""
    for numero, texto, ok in resultado:
        if ok:
            linhas += (f'<tr><td style="text-align:center;">{numero}</td><td>{texto}</td>'
                       f'<td style="text-align:center;"><span class="ok">OK</span></td></tr>')
        else:
            linhas += (f'<tr style="color:red;font-weight:bold;"><td style="text-align:center;">{numero}</td>'
                       f'<td>{texto}</td><td style="text-align:center;"><span class="falta">FALTA NO A2</span></td></tr>')

    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<title>Comparação de Débitos - A1 x A2</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; }}
h2, p {{ text-align: center; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
th, td {{ border: 1px solid #ccc; padding: 8px 12px; font-size: 14px; }}
th {{ background-color: #f4f4f4; }}
.ok {{ color: green; font-weight: bold; }}
.falta {{ color: red; font-weight: bold; }}
@media print {{ .nao-imprimir {{ display: none; }} }}
</style></head><body>
<h2>Relatório de Comparação de Débitos: A1 x A2</h2>
<p>Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
<table><thead><tr>
<th style="width:10%;">Linha A1</th><th style="width:70%;">Registro</th><th style="width:20%;">Situação</th>
</tr></thead><tbody>{linhas}</tbody></table>
<p><b>Débitos no A1:</b> {total} | <b>Débitos faltando no A2:</b> {faltando}</p>
<div class="nao-imprimir" style="text-align:center;margin-top:30px;">
<button onclick="window.print();" style="padding:10px 20px;font-size:16px;cursor:pointer;background:#007BFF;color:#fff;border:none;border-radius:5px;">Imprimir Relatório</button>
</div></body></html>"""

    os.makedirs(PASTA_REG, exist_ok=True)
    caminho = os.path.join(PASTA_REG, "relatorio_debitos.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)
    webbrowser.open("file:///" + os.path.abspath(caminho).replace("\\", "/"))



# INTERFACE

FONTE = "Segoe UI"


def estilizar_tabelas(modo, acento):
    st = ttk.Style()
    st.theme_use("clam")
    st.configure("Treeview", background=cm("painel", modo),
                 fieldbackground=cm("painel", modo), foreground=cm("texto", modo),
                 rowheight=38, borderwidth=0, font=(FONTE, 12))
    st.configure("Treeview.Heading", background=cm("bg", modo),
                 foreground=cm("cabecalho", modo), relief="flat", borderwidth=0,
                 padding=(8, 10), font=(FONTE, 11, "bold"))
    st.map("Treeview", background=[("selected", acento)],
           foreground=[("selected", "#ffffff")])
    st.map("Treeview.Heading", background=[("active", cm("bg", modo))])
    st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.modo, self.acento = carregar_config()
        ctk.set_appearance_mode("dark" if self.modo == "Escuro" else "light")
        self.primarios = []  # botões que usam a cor de destaque
        self.resultados = []

        self.title("Sistema de Busca e Ordenação")
        self.geometry("1100x720")
        self.minsize(900, 540)
        self.configure(fg_color=c("bg"))

        self._montar_cabecalho()

        self.status = tk.StringVar(value="Pronto.")
        ctk.CTkLabel(self, textvariable=self.status, anchor="w", text_color=c("cinza"),
                     font=(FONTE, 12)).pack(side="bottom", fill="x", padx=18, pady=(0, 10))

        self.abas = ctk.CTkTabview(
            self, corner_radius=14, fg_color=c("painel"),
            segmented_button_fg_color=c("campo"),
            segmented_button_unselected_color=c("campo"),
            segmented_button_unselected_hover_color=c("campo_hover"),
            text_color=("#111827", "#ffffff"),
            command=self.atualizar_tudo)
        self.abas.pack(fill="both", expand=True, padx=16, pady=(12, 6))
        try:  # abas maiores
            self.abas._segmented_button.configure(height=42, font=(FONTE, 14, "bold"))
        except Exception:
            pass
        self.aba_busca = self.abas.add("Buscar no A1")
        self.aba_a2 = self.abas.add("Lista A2")
        self.aba_deb = self.abas.add("Débitos A1 x A2")

        self._montar_aba_busca()
        self._montar_aba_a2()
        self._montar_aba_debitos()
        self.aplicar_tema()
        self.atualizar_tudo()

    #  componentes reutilizáveis 
    def botao(self, pai, texto, comando, primario=False, perigo=False, largura=170):
        if perigo:
            kw = dict(fg_color=c("perigo"), hover_color=c("perigo_hover"),
                      text_color=c("vermelho"))
        elif primario:
            kw = dict(fg_color=ACENTOS[self.acento][0],
                      hover_color=ACENTOS[self.acento][1], text_color="#ffffff")
        else:
            kw = dict(fg_color=c("campo"), hover_color=c("campo_hover"),
                      text_color=c("texto"))
        b = ctk.CTkButton(pai, text=texto, command=comando, width=largura, height=46,
                          corner_radius=10, font=(FONTE, 14, "bold"), **kw)
        if primario:
            self.primarios.append(b)
        return b

    def campo(self, pai, var, placeholder, largura=380):
        return ctk.CTkEntry(pai, textvariable=var, height=46, width=largura,
                            corner_radius=10, border_width=0, fg_color=c("campo"),
                            text_color=c("texto"), placeholder_text=placeholder,
                            placeholder_text_color=c("cinza"), font=(FONTE, 14))

    @staticmethod
    def _tabela(pai, colunas, larguras):
        frame = ctk.CTkFrame(pai, fg_color="transparent", corner_radius=0)
        tree = ttk.Treeview(frame, columns=[c_[0] for c_ in colunas],
                            show="headings", selectmode="extended")
        for (cid, titulo), larg in zip(colunas, larguras):
            alin = "w" if cid == "texto" else "center"
            tree.heading(cid, text=titulo, anchor=alin)
            tree.column(cid, width=larg or 300, stretch=(larg == 0), anchor=alin)
        sb = ctk.CTkScrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y", padx=(4, 0))
        return frame, tree

    #  cabeçalho com seletor de tema 
    def _montar_cabecalho(self):
        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", padx=20, pady=(16, 0))
        ctk.CTkLabel(cab, text="Busca e Ordenação", text_color=c("texto"),
                     font=(FONTE, 24, "bold")).pack(side="left")

        self.opt_acento = ctk.CTkOptionMenu(
            cab, values=list(ACENTOS), command=self.mudar_acento, width=140, height=42,
            corner_radius=10, font=(FONTE, 14), dropdown_font=(FONTE, 14),
            fg_color=c("campo"), button_color=c("campo_hover"),
            button_hover_color=c("campo_hover"), text_color=c("texto"),
            dropdown_fg_color=c("painel"), dropdown_text_color=c("texto"),
            dropdown_hover_color=c("campo"))
        self.opt_acento.set(self.acento)
        self.opt_acento.pack(side="right")
        ctk.CTkLabel(cab, text="Cor:", text_color=c("cinza"),
                     font=(FONTE, 13)).pack(side="right", padx=(18, 6))

        self.seg_tema = ctk.CTkSegmentedButton(
            cab, values=["Escuro", "Claro"], command=self.mudar_tema, height=42,
            corner_radius=10, font=(FONTE, 14, "bold"), fg_color=c("campo"),
            unselected_color=c("campo"), unselected_hover_color=c("campo_hover"),
            text_color=("#111827", "#ffffff"))
        self.seg_tema.set(self.modo)
        self.seg_tema.pack(side="right")
        ctk.CTkLabel(cab, text="Tema:", text_color=c("cinza"),
                     font=(FONTE, 13)).pack(side="right", padx=(18, 6))

    def mudar_tema(self, modo):
        self.modo = modo
        ctk.set_appearance_mode("dark" if modo == "Escuro" else "light")
        self.aplicar_tema()
        salvar_config(self.modo, self.acento)
        self.status.set(f"Tema {modo.lower()} aplicado.")

    def mudar_acento(self, acento):
        self.acento = acento
        self.aplicar_tema()
        salvar_config(self.modo, self.acento)
        self.status.set(f"Cor de destaque: {acento}.")

    def aplicar_tema(self):
        normal, hover = ACENTOS[self.acento]
        # widgets CustomTkinter com cor de destaque
        for b in self.primarios:
            b.configure(fg_color=normal, hover_color=hover)
        self.abas.configure(segmented_button_selected_color=normal,
                            segmented_button_selected_hover_color=hover)
        self.seg_tema.configure(selected_color=normal, selected_hover_color=hover)
        # tabelas (ttk) precisam ser reestilizadas
        estilizar_tabelas(self.modo, normal)
        self.tree_busca.tag_configure("ja", foreground=cm("cinza", self.modo))
        self.tree_busca.tag_configure("novo", foreground=cm("texto", self.modo))
        self.tree_deb.tag_configure("falta", foreground=cm("vermelho", self.modo))
        self.tree_deb.tag_configure("ok", foreground=cm("verde", self.modo))
        self.tree_deb.tag_configure("marcado", background=cm("marcado", self.modo))

    #  aba 1: buscar no A1 
    def _montar_aba_busca(self):
        topo = ctk.CTkFrame(self.aba_busca, fg_color="transparent")
        topo.pack(fill="x", pady=(6, 12))
        self.busca_var = tk.StringVar()
        entrada = self.campo(topo, self.busca_var, "Digite o termo e pressione Enter...")
        entrada.pack(side="left")
        entrada.bind("<Return>", lambda e: self.buscar_a1())
        entrada.focus_set()
        self.botao(topo, "Buscar", self.buscar_a1, primario=True, largura=130).pack(side="left", padx=10)
        self.botao(topo, "Adicionar ao A2", self.adicionar_selecionados,
                   primario=True, largura=200).pack(side="right")

        frame, self.tree_busca = self._tabela(
            self.aba_busca, [("linha", "Linha"), ("texto", "Registro"), ("situacao", "Situação")],
            [90, 0, 130])
        frame.pack(fill="both", expand=True)
        self.tree_busca.bind("<Double-1>", lambda e: self.adicionar_selecionados())
        ctk.CTkLabel(self.aba_busca, text="Duplo clique adiciona ao A2  •  Ctrl/Shift seleciona vários",
                     text_color=c("cinza"), font=(FONTE, 12)).pack(anchor="w", pady=(8, 0))

    def buscar_a1(self):
        termo = self.busca_var.get().strip().lower()
        self.tree_busca.delete(*self.tree_busca.get_children())
        self.resultados = []
        if not termo:
            self.status.set("Digite um termo para buscar.")
            return
        destino = set(carregar_linhas(ARQUIVO_DESTINO))
        self.resultados = [(n, t) for n, t in carregar_origem_numerada() if corresponde(termo, t)]
        for i, (n, t) in enumerate(self.resultados):
            ja = f"[{n}] {t}" in destino
            self.tree_busca.insert("", "end", iid=str(i),
                                   values=(n, t, "✓ no A2" if ja else ""),
                                   tags=("ja" if ja else "novo",))
        self.status.set(f"{len(self.resultados)} resultado(s) para '{termo}'.")

    def adicionar_selecionados(self):
        sel = self.tree_busca.selection()
        if not sel:
            self.status.set("Selecione um ou mais registros para adicionar.")
            return
        destino = carregar_linhas(ARQUIVO_DESTINO)
        adicionados = 0
        for iid in sel:
            numero, texto = self.resultados[int(iid)]
            item = f"[{numero}] {texto}"
            if item not in destino:
                destino.append(item)
                adicionados += 1
        destino.sort(key=extrair_numero)
        salvar_linhas(ARQUIVO_DESTINO, destino)
        self.buscar_a1()
        self.atualizar_a2()
        self.status.set(f"✓ {adicionados} registro(s) adicionado(s) ao A2.")

    #  aba 2: lista A2 
    def _montar_aba_a2(self):
        topo = ctk.CTkFrame(self.aba_a2, fg_color="transparent")
        topo.pack(fill="x", pady=(6, 12))
        self.filtro_a2 = tk.StringVar()
        self.filtro_a2.trace_add("write", lambda *a: self.atualizar_a2())
        self.campo(topo, self.filtro_a2, "Filtrar lista...").pack(side="left")
        self.botao(topo, "Exportar N.txt", self.exportar, largura=170).pack(side="right")
        self.botao(topo, "Remover", self.remover_a2, perigo=True, largura=140).pack(side="right", padx=10)

        frame, self.tree_a2 = self._tabela(
            self.aba_a2, [("linha", "Linha"), ("texto", "Registro")], [90, 0])
        frame.pack(fill="both", expand=True)

    def atualizar_a2(self):
        self.tree_a2.delete(*self.tree_a2.get_children())
        filtro = self.filtro_a2.get().strip().lower()
        total = 0
        for item in obter_destino_ordenado():
            texto = extrair_texto_registro(item)
            if filtro and not corresponde(filtro, texto):
                continue
            self.tree_a2.insert("", "end", iid=item, values=(extrair_numero(item), texto))
            total += 1
        self.status.set(f"A2: {total} registro(s) exibido(s).")

    def remover_a2(self):
        sel = self.tree_a2.selection()
        if not sel:
            self.status.set("Selecione registros do A2 para remover.")
            return
        if not messagebox.askyesno("Remover", f"Remover {len(sel)} registro(s) do A2?"):
            return
        restantes = [l for l in carregar_linhas(ARQUIVO_DESTINO) if l not in sel]
        salvar_linhas(ARQUIVO_DESTINO, restantes)
        self.atualizar_a2()
        self.status.set(f"{len(sel)} registro(s) removido(s).")

    def exportar(self):
        os.makedirs(PASTA_REG, exist_ok=True)
        caminho = os.path.join(PASTA_REG, "N.txt")
        salvar_linhas(caminho, obter_destino_ordenado())
        self.status.set(f"✓ Exportado para {os.path.abspath(caminho)}")

    #  aba 3: débitos 
    def _card(self, pai, titulo, var, cor):
        card = ctk.CTkFrame(pai, fg_color=c("campo"), corner_radius=12)
        card.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(card, text=titulo, text_color=c("cinza"),
                     font=(FONTE, 12)).pack(anchor="w", padx=18, pady=(10, 0))
        ctk.CTkLabel(card, textvariable=var, text_color=cor,
                     font=(FONTE, 26, "bold")).pack(anchor="w", padx=18, pady=(0, 10))

    def _montar_aba_debitos(self):
        topo = ctk.CTkFrame(self.aba_deb, fg_color="transparent")
        topo.pack(fill="x", pady=(6, 12))
        self.var_total = tk.StringVar(value="0")
        self.var_falta = tk.StringVar(value="0")
        self._card(topo, "Débitos no A1", self.var_total, c("texto"))
        self._card(topo, "Faltando no A2", self.var_falta, c("vermelho"))
        self.botao(topo, "Imprimir relatório", gerar_relatorio_html,
                   primario=True, largura=200).pack(side="right")
        self.botao(topo, "Atualizar", self.atualizar_debitos, largura=140).pack(side="right", padx=10)

        # barra de pesquisa: ocupa o espaço entre os cartões e o botão Atualizar
        self.filtro_deb = tk.StringVar()
        self.filtro_deb.trace_add("write", lambda *a: self.atualizar_debitos())
        entrada_deb = self.campo(topo, self.filtro_deb, "Pesquisar (Enter = próximo)...",
                                 largura=200)
        entrada_deb.pack(side="left", fill="x", expand=True, padx=(8, 0))
        entrada_deb.bind("<Return>", lambda e: self.proximo_marcado())
        self.marcados_deb = []
        self.pos_marcado = -1
        self.botao(topo, "✕", lambda: self.filtro_deb.set(""),
                   largura=46).pack(side="left", padx=(6, 10))

        frame, self.tree_deb = self._tabela(
            self.aba_deb, [("linha", "Linha A1"), ("texto", "Registro"), ("situacao", "Situação")],
            [100, 0, 150])
        frame.pack(fill="both", expand=True)

    def atualizar_debitos(self):
        self.tree_deb.delete(*self.tree_deb.get_children())
        resultado, total, faltando = calcular_debitos()
        filtro = self.filtro_deb.get().strip().lower()
        self.marcados_deb = []
        self.pos_marcado = -1
        for i, (numero, texto, ok) in enumerate(resultado):
            situacao = "OK" if ok else "FALTA NO A2"
            tags = ["ok" if ok else "falta"]
            if filtro and (corresponde(filtro, texto) or filtro in situacao.lower()):
                tags.append("marcado")
                self.marcados_deb.append(str(i))
            self.tree_deb.insert("", "end", iid=str(i),
                                 values=(numero, texto, situacao), tags=tuple(tags))
        self.var_total.set(str(total))
        self.var_falta.set(str(faltando))
        if filtro:
            if self.marcados_deb:
                self.tree_deb.see(self.marcados_deb[0])
            self.status.set(f"{len(self.marcados_deb)} marcado(s) em {total} débito(s). "
                            "Enter vai para o próximo.")

    def proximo_marcado(self):
        if not self.marcados_deb:
            return
        self.pos_marcado = (self.pos_marcado + 1) % len(self.marcados_deb)
        iid = self.marcados_deb[self.pos_marcado]
        self.tree_deb.see(iid)
        self.tree_deb.selection_set(iid)
        self.status.set(f"Marcado {self.pos_marcado + 1} de {len(self.marcados_deb)}.")

    def atualizar_tudo(self):
        self.atualizar_a2()
        self.atualizar_debitos()


if __name__ == "__main__":
    inicializar_arquivos()
    App().mainloop()
