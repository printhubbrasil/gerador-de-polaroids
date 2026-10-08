#!/usr/bin/env python3
"""A janela do Gerador de Polaroids.

Esquerda: todas as configurações, em blocos. Direita: a prévia da folha, que é
desenhada pelo MESMO motor do PDF (motor.previa) — o que aparece é o que sai.

Tudo que se mexe fica salvo sozinho (config.json da pasta do programa no usuário)
e volta na próxima abertura. "Perfis" guardam conjuntos com nome ("Festa 10×15").
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageTk

from . import fontes, motor as M, registro as R

VERSAO = "2.0"

# cores da janela (as do programa antigo)
BG, CARD, FG, MUTED = "#1C1C2E", "#2A2A3E", "#FFFFFF", "#9E9EBB"
ACCENT, ACCENT_H, OK, PERIGO, AVISO = "#4F8EF7", "#3A7AE4", "#4CAF50", "#EF5350", "#FFA726"
CAMPO = "#3A3A52"


def numero(texto, padrao=0.0):
    """Aceita "4,5" e "4.5" — no Brasil a vírgula vem primeiro."""
    try:
        return float(str(texto).strip().replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def fmt(v):
    v = float(v)
    return f"{v:g}".replace(".", ",")


class Rolavel(tk.Frame):
    """Coluna com barra de rolagem que rola com a roda em cima de QUALQUER controle.
    (o evento da roda vai pro widget debaixo do cursor — bind só no canvas morria
    em cima de campo e botão; aprendido na Central de Produção)."""

    def __init__(self, pai, largura):
        super().__init__(pai, bg=BG)
        self.tela = tk.Canvas(self, bg=BG, highlightthickness=0, width=largura)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.tela.yview)
        self.dentro = tk.Frame(self.tela, bg=BG)
        self._janela = self.tela.create_window((0, 0), window=self.dentro, anchor="nw")
        self.tela.configure(yscrollcommand=barra.set)
        self.tela.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.dentro.bind("<Configure>", lambda e: self.tela.configure(scrollregion=self.tela.bbox("all")))
        self.tela.bind("<Configure>", lambda e: self.tela.itemconfigure(self._janela, width=e.width))
        self.bind("<Enter>", lambda e: self._roda(True))
        self.bind("<Leave>", self._saiu)

    def _saiu(self, e):
        # entrar num campo de DENTRO também dispara <Leave> aqui — só solta a roda
        # se o cursor saiu da coluna de verdade
        w = self.winfo_containing(e.x_root, e.y_root)
        while w is not None:
            if w is self:
                return
            w = getattr(w, "master", None)
        self._roda(False)

    def _roda(self, ligar):
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            if ligar:
                self.bind_all(ev, self._rolar)
            else:
                self.unbind_all(ev)

    def _rolar(self, e):
        if e.num == 4:
            passo = -1
        elif e.num == 5:
            passo = 1
        else:
            passo = -1 if e.delta > 0 else 1
            if sys.platform == "darwin":
                passo *= max(1, abs(e.delta) // 3)
        self.tela.yview_scroll(passo * (1 if sys.platform == "darwin" else 2), "units")


class App:
    def __init__(self, raiz):
        self.raiz = raiz
        raiz.title(f"Gerador de Polaroids — PrintHub Brasil  ·  v{VERSAO}")
        raiz.configure(bg=BG)
        raiz.geometry("1220x800")
        raiz.minsize(980, 640)
        self._tema()

        self.fotos = []
        self.pasta = ""
        self.fontes = {}                 # nome -> caminho
        self.vars = {}                   # caminho da config ("folha.w") -> tk var
        self._carregando = False
        self._agenda = None
        self._previa_ger = 0
        self._previa_img = None
        self._miniaturas = {}
        self._cache_prev = {}
        self.pagina = 0
        self.fila = queue.Queue()
        self.gerando = False
        self._cancelar = False

        salvo = R.ler_json(R.ARQ_CONFIG, {})
        self.cfg = M.completar(salvo.get("cfg"))
        self.pasta = salvo.get("pasta", "")
        self.perfis = R.ler_json(R.ARQ_PERFIS, {})

        self._montar()
        self._para_tela(self.cfg)
        if self.pasta and Path(self.pasta).is_dir():
            self._carregar_pasta(self.pasta)
        threading.Thread(target=self._ler_fontes, daemon=True).start()
        raiz.after(100, self._bombear)
        self._mudou()

    # ── aparência ─────────────────────────────────────────────────────────────
    def _tema(self):
        st = ttk.Style(self.raiz)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TCombobox", fieldbackground=CAMPO, background=CAMPO, foreground=FG,
                     arrowcolor=FG, bordercolor=CAMPO, lightcolor=CAMPO, darkcolor=CAMPO)
        st.map("TCombobox", fieldbackground=[("readonly", CAMPO)], foreground=[("readonly", FG)],
               selectbackground=[("readonly", CAMPO)], selectforeground=[("readonly", FG)])
        self.raiz.option_add("*TCombobox*Listbox.background", CARD)
        self.raiz.option_add("*TCombobox*Listbox.foreground", FG)
        self.raiz.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        st.configure("P.Horizontal.TProgressbar", troughcolor=CARD, background=ACCENT, bordercolor=CARD)
        st.configure("Vertical.TScrollbar", background=CARD, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)
        # ⚠ roda do mouse em cima de caixa de lista TROCA o valor (é de fábrica no Tk).
        # Rolando o painel, a pessoa trocaria o modelo sem ver. Aprendido na Central.
        for classe in ("TCombobox", "TSpinbox"):
            for ev in self.raiz.bind_class(classe):
                if "Wheel" in ev or "Button-4" in ev or "Button-5" in ev:
                    self.raiz.unbind_class(classe, ev)

    def _rotulo(self, pai, texto, cor=MUTED, tam=9, peso="normal"):
        return tk.Label(pai, text=texto, bg=pai["bg"], fg=cor, font=("Segoe UI", tam, peso), anchor="w",
                        justify="left")

    def _bloco(self, titulo, ajuda=""):
        caixa = tk.Frame(self.col.dentro, bg=CARD, padx=14, pady=12)
        caixa.pack(fill="x", padx=(10, 6), pady=(0, 10))
        self._rotulo(caixa, titulo.upper(), FG, 9, "bold").pack(fill="x")
        if ajuda:
            self._rotulo(caixa, ajuda, MUTED, 8).pack(fill="x", pady=(2, 6))
            caixa.bind("<Configure>", lambda e, c=caixa: [w.configure(wraplength=max(200, e.width - 30))
                                                          for w in c.winfo_children() if isinstance(w, tk.Label)])
        return caixa

    def _linha(self, pai):
        f = tk.Frame(pai, bg=pai["bg"])
        f.pack(fill="x", pady=3)
        return f

    def _campo(self, pai, rotulo, chave, largura=7, unidade="mm", dica=""):
        """Um número com rótulo. A var é texto pra aceitar vírgula."""
        f = tk.Frame(pai, bg=pai["bg"])
        self._rotulo(f, rotulo, MUTED, 8).pack(anchor="w")
        linha = tk.Frame(f, bg=pai["bg"])
        linha.pack(anchor="w")
        var = self.vars.setdefault(chave, tk.StringVar())
        e = tk.Entry(linha, textvariable=var, width=largura, bg=CAMPO, fg=FG, insertbackground=FG,
                     relief="flat", font=("Segoe UI", 10), highlightthickness=1,
                     highlightbackground=CAMPO, highlightcolor=ACCENT)
        e.pack(side="left", ipady=3)
        if unidade:
            self._rotulo(linha, unidade, MUTED, 8).pack(side="left", padx=(4, 0))
        var.trace_add("write", lambda *_: self._mudou())
        if dica:
            self._dica(e, dica)
        return f

    def _check(self, pai, texto, chave):
        var = self.vars.setdefault(chave, tk.BooleanVar())
        c = tk.Checkbutton(pai, text=" " + texto, variable=var, command=self._mudou, bg=pai["bg"], fg=FG,
                           selectcolor=CAMPO, activebackground=pai["bg"], activeforeground=FG,
                           font=("Segoe UI", 9), bd=0, highlightthickness=0, anchor="w", cursor="hand2")
        return c

    def _combo(self, pai, chave, valores, largura=30, ao_mudar=None):
        var = self.vars.setdefault(chave, tk.StringVar())
        cb = ttk.Combobox(pai, textvariable=var, values=list(valores), state="readonly", width=largura)
        cb.bind("<<ComboboxSelected>>", lambda e: (ao_mudar or self._mudou)())
        return cb

    def _cor(self, pai, texto, chave):
        f = tk.Frame(pai, bg=pai["bg"])
        var = self.vars.setdefault(chave, tk.StringVar(value="#FFFFFF"))
        amostra = tk.Label(f, text="   ", bg=var.get(), relief="solid", bd=1, cursor="hand2")
        amostra.pack(side="left")
        self._rotulo(f, " " + texto, FG, 9).pack(side="left")

        def escolher(_=None):
            atual = var.get() if var.get().startswith("#") else "#FFFFFF"
            r = colorchooser.askcolor(color=atual, parent=self.raiz, title=texto)
            if r and r[1]:
                var.set(r[1].upper())

        amostra.bind("<Button-1>", escolher)
        var.trace_add("write", lambda *_: (amostra.configure(bg=var.get()) if var.get().startswith("#") else None,
                                           self._mudou()))
        return f

    def _dica(self, widget, texto):
        dica = {"j": None}

        def mostrar(e):
            j = tk.Toplevel(widget)
            j.wm_overrideredirect(True)
            j.geometry(f"+{e.x_root + 12}+{e.y_root + 12}")
            tk.Label(j, text=texto, bg="#11111A", fg=FG, font=("Segoe UI", 8), padx=8, pady=5,
                     wraplength=280, justify="left").pack()
            dica["j"] = j

        def esconder(_):
            if dica["j"]:
                dica["j"].destroy()
                dica["j"] = None

        widget.bind("<Enter>", mostrar)
        widget.bind("<Leave>", esconder)

    def _botao(self, pai, texto, cmd, primario=False):
        b = tk.Button(pai, text=texto, command=cmd, bg=ACCENT if primario else CAMPO, fg=FG,
                      activebackground=ACCENT_H if primario else CARD, activeforeground=FG,
                      relief="flat", font=("Segoe UI", 10 if primario else 9, "bold" if primario else "normal"),
                      cursor="hand2", padx=12, pady=6 if primario else 3, bd=0)
        return b

    # ── montagem da janela ────────────────────────────────────────────────────
    def _montar(self):
        topo = tk.Frame(self.raiz, bg=BG)
        topo.pack(fill="x", padx=16, pady=(12, 8))
        self._rotulo(topo, "Gerador de Fotos Polaroid", FG, 15, "bold").pack(side="left")
        self._rotulo(topo, "   PrintHub Brasil", ACCENT, 10, "bold").pack(side="left", pady=(6, 0))

        corpo = tk.Frame(self.raiz, bg=BG)
        corpo.pack(fill="both", expand=True)
        self.col = Rolavel(corpo, 430)
        self.col.pack(side="left", fill="y")
        direita = tk.Frame(corpo, bg=BG)
        direita.pack(side="left", fill="both", expand=True, padx=(4, 14))

        # ── 1. fotos
        b = self._bloco("1 · Fotos", "Coloque todas as fotos numa pasta e escolha ela aqui. "
                                      "Elas saem na ordem do nome (foto2 antes de foto10).")
        l = self._linha(b)
        self._botao(l, "📂 Escolher pasta…", self._escolher_pasta).pack(side="left")
        self.lbl_pasta = self._rotulo(l, "nenhuma pasta", MUTED, 8)
        self.lbl_pasta.pack(side="left", padx=8, fill="x", expand=True)
        l = self._linha(b)
        self._campo(l, "Cópias de cada foto", "copias", 5, "").pack(side="left")
        self.lbl_qtd = self._rotulo(l, "", OK, 9)
        self.lbl_qtd.pack(side="left", padx=12, pady=(12, 0))

        # ── 2. folha
        b = self._bloco("2 · Folha", "O papel em que vai imprimir.")
        l = self._linha(b)
        self.cb_folha = self._combo(l, "folha.modelo", list(M.FOLHAS) + [M.FOLHA_PERSONALIZADA], 32,
                                    self._trocou_folha)
        self.cb_folha.pack(side="left")
        l = self._linha(b)
        self._campo(l, "Largura", "folha.w").pack(side="left")
        self._campo(l, "Altura", "folha.h").pack(side="left", padx=12)
        orient = tk.Frame(l, bg=b["bg"])
        orient.pack(side="left", padx=6, pady=(14, 0))
        self.vars["folha.paisagem"] = tk.BooleanVar()
        for txt, val in (("Em pé", False), ("Deitada", True)):
            tk.Radiobutton(orient, text=txt, variable=self.vars["folha.paisagem"], value=val, command=self._mudou,
                           bg=b["bg"], fg=FG, selectcolor=CAMPO, activebackground=b["bg"], activeforeground=FG,
                           font=("Segoe UI", 9), bd=0, highlightthickness=0, cursor="hand2").pack(side="left")
        self._rotulo(b, "Margens", FG, 9, "bold").pack(fill="x", pady=(8, 0))
        l = self._linha(b)
        for rot, ch in (("Em cima", "margem.topo"), ("Embaixo", "margem.base"),
                        ("Esquerda", "margem.esq"), ("Direita", "margem.dir")):
            self._campo(l, rot, ch, 5).pack(side="left", padx=(0, 8))
        l = self._linha(b)
        self._campo(l, "Todas iguais", "_margem_todas", 5).pack(side="left")
        self._botao(l, "Aplicar nas 4", self._margem_todas).pack(side="left", padx=8, pady=(14, 0))
        self._check(b, "Centralizar as polaroids na folha", "centralizar").pack(fill="x", pady=(4, 0))
        self._rotulo(b, "Espaço entre as polaroids", FG, 9, "bold").pack(fill="x", pady=(8, 0))
        l = self._linha(b)
        self._campo(l, "Entre colunas", "espaco.h", 5,
                    dica="Distância entre o corte de uma polaroid e o da vizinha, de lado. "
                         "Zero = elas encostam e dividem a mesma linha de corte.").pack(side="left")
        self._campo(l, "Entre fileiras", "espaco.v", 5).pack(side="left", padx=12)

        # ── 3. polaroid
        b = self._bloco("3 · Polaroid", "O tamanho de cada polaroid e da janela da foto. "
                                         "A base (onde vai a legenda) é o que sobra embaixo.")
        l = self._linha(b)
        self.cb_pol = self._combo(l, "polaroid.modelo", list(M.POLAROIDS) + [M.POLAROID_PERSONALIZADA], 32,
                                  self._trocou_polaroid)
        self.cb_pol.pack(side="left")
        l = self._linha(b)
        self._campo(l, "Largura", "polaroid.w").pack(side="left")
        self._campo(l, "Altura", "polaroid.h").pack(side="left", padx=12)
        l = self._linha(b)
        self._campo(l, "Borda dos lados", "polaroid.lat", 5).pack(side="left")
        self._campo(l, "Borda de cima", "polaroid.topo", 5).pack(side="left", padx=12)
        self._campo(l, "Altura da foto", "polaroid.foto_h", 5).pack(side="left")
        self.lbl_pol = self._rotulo(b, "", ACCENT, 8)
        self.lbl_pol.pack(fill="x", pady=(4, 0))
        l = self._linha(b)
        self._rotulo(l, "Na folha  ", MUTED, 8).pack(side="left")
        self.cb_giro = self._combo(l, "_giro", list(M.GIRO.values()), 28)
        self.cb_giro.pack(side="left")
        l = self._linha(b)
        self._cor(l, "Cor da moldura", "moldura_cor").pack(side="left")
        l = self._linha(b)
        self._check(l, "Contorno fino na foto", "contorno_foto").pack(side="left")
        self._cor(l, "cor do contorno", "contorno_cor").pack(side="left", padx=10)

        # ── 4. corte e sangria
        b = self._bloco("4 · Corte e sangria")
        l = self._linha(b)
        self._campo(l, "Sangria", "sangria", 5,
                    dica="Quanto a moldura passa do corte, pra não sobrar fio de papel na borda "
                         "se a guilhotina variar. Entre duas polaroids vizinhas ela nunca passa "
                         "da metade do espaço entre elas.").pack(side="left")
        self._rotulo(b, "Marcas de corte", FG, 9, "bold").pack(fill="x", pady=(8, 0))
        self._check(b, "Imprimir marcas de corte (fora das polaroids)", "marcas.ligado").pack(fill="x")
        l = self._linha(b)
        self._campo(l, "Comprimento", "marcas.comprimento", 5).pack(side="left")
        self._campo(l, "Afastamento", "marcas.afastamento", 5,
                    dica="Distância entre o fim da sangria e o começo da marca.").pack(side="left", padx=10)
        self._campo(l, "Espessura", "marcas.espessura", 5, "pt").pack(side="left")
        l = self._linha(b)
        self._check(l, "Linha fina em volta de cada polaroid", "marcas.linha_corte").pack(side="left")
        self._cor(l, "cor", "marcas.cor").pack(side="left", padx=10)

        # ── 5. enquadramento
        b = self._bloco("5 · Enquadramento da foto")
        l = self._linha(b)
        self.cb_enq = self._combo(l, "_enquadrar", list(M.ENQUADRAR.values()), 30)
        self.cb_enq.pack(side="left")
        l = self._linha(b)
        self._campo(l, "Subir o rosto", "foto.subir_rosto", 5, "%",
                    dica="Quanto o rosto fica acima do meio da foto. 4% é o padrão.").pack(side="left")
        self.lbl_rosto = self._rotulo(b, "", MUTED, 8)
        self.lbl_rosto.pack(fill="x")

        # ── 6. legenda
        b = self._bloco("6 · Legenda (na base)")
        l = self._linha(b)
        self.cb_leg = self._combo(l, "_legenda", list(M.LEGENDA.values()), 30)
        self.cb_leg.pack(side="left")
        l = self._linha(b)
        self._rotulo(l, "Texto  ", MUTED, 8).pack(side="left")
        var = self.vars.setdefault("legenda.texto", tk.StringVar())
        tk.Entry(l, textvariable=var, bg=CAMPO, fg=FG, insertbackground=FG, relief="flat",
                 font=("Segoe UI", 10), highlightthickness=0).pack(side="left", fill="x", expand=True, ipady=3)
        var.trace_add("write", lambda *_: self._mudou())
        l = self._linha(b)
        self._rotulo(l, "Fonte  ", MUTED, 8).pack(side="left")
        self.cb_fonte = self._combo(l, "_fonte", ["Carregando fontes…"], 30)
        self.cb_fonte.pack(side="left")
        l = self._linha(b)
        self._campo(l, "Tamanho", "legenda.tamanho", 5, "pt", dica="0 = automático (cabe na base e na largura)").pack(side="left")
        self._campo(l, "Subir/descer", "legenda.deslocar", 5).pack(side="left", padx=10)
        l = self._linha(b)
        self._cor(l, "Cor do texto", "legenda.cor").pack(side="left")
        self._rotulo(l, "    Alinhar ", MUTED, 8).pack(side="left")
        self.cb_alinhar = self._combo(l, "_alinhar", list(M.ALINHAR.values()), 10)
        self.cb_alinhar.pack(side="left")

        # ── 7. saída
        b = self._bloco("7 · Qualidade do arquivo")
        l = self._linha(b)
        self._campo(l, "Resolução", "dpi", 5, "dpi", dica="300 é o padrão de gráfica. 600 dobra o arquivo e quase nunca se vê.").pack(side="left")
        self._campo(l, "Qualidade JPEG", "qualidade", 5, "%").pack(side="left", padx=12)

        # ── 8. perfis
        b = self._bloco("8 · Perfis", "Guarde um conjunto de configurações com nome, pra trocar de trabalho num clique.")
        l = self._linha(b)
        self.cb_perfil = self._combo(l, "_perfil", sorted(self.perfis), 24, self._carregar_perfil)
        self.cb_perfil.pack(side="left")
        self._botao(l, "Salvar como…", self._salvar_perfil).pack(side="left", padx=6)
        l = self._linha(b)
        self._botao(l, "Excluir perfil", self._excluir_perfil).pack(side="left")
        self._botao(l, "Voltar ao padrão", self._restaurar).pack(side="left", padx=6)

        self._rotulo(self.col.dentro, f"Criado por João Ebel — PrintHub Brasil · v{VERSAO}", "#555577", 8).pack(
            fill="x", padx=14, pady=(0, 14))

        # ── direita: prévia + gerar
        cab = tk.Frame(direita, bg=BG)
        cab.pack(fill="x")
        self._rotulo(cab, "PRÉVIA DA FOLHA", MUTED, 9, "bold").pack(side="left")
        self.nav = tk.Frame(cab, bg=BG)
        self.nav.pack(side="right")
        self._botao(self.nav, "‹", lambda: self._virar(-1)).pack(side="left")
        self.lbl_pag = self._rotulo(self.nav, "1 / 1", FG, 9)
        self.lbl_pag.pack(side="left", padx=8)
        self._botao(self.nav, "›", lambda: self._virar(1)).pack(side="left")
        self.palco = tk.Canvas(direita, bg="#141420", highlightthickness=0)
        self.palco.pack(fill="both", expand=True, pady=(6, 6))
        self.palco.bind("<Configure>", lambda e: self._agendar(150))
        self.lbl_info = self._rotulo(direita, "", FG, 9)
        self.lbl_info.pack(fill="x")
        self.lbl_erro = self._rotulo(direita, "", PERIGO, 9, "bold")
        self.lbl_erro.pack(fill="x")
        rodape = tk.Frame(direita, bg=BG)
        rodape.pack(fill="x", pady=(6, 12))
        self.bt_gerar = self._botao(rodape, "Gerar PDF", self._gerar, primario=True)
        self.bt_gerar.pack(side="left")
        self.barra = ttk.Progressbar(rodape, style="P.Horizontal.TProgressbar", mode="determinate")
        self.barra.pack(side="left", fill="x", expand=True, padx=12)
        self.lbl_status = self._rotulo(rodape, "Pronto.", MUTED, 9)
        self.lbl_status.pack(side="left")

    # ── config <-> tela ───────────────────────────────────────────────────────
    MAPAS = {"_giro": ("giro", M.GIRO), "_enquadrar": ("foto.enquadrar", M.ENQUADRAR),
             "_legenda": ("legenda.modo", M.LEGENDA), "_alinhar": ("legenda.alinhar", M.ALINHAR)}
    TEXTOS = {"legenda.texto", "folha.modelo", "polaroid.modelo", "moldura_cor", "contorno_cor",
              "marcas.cor", "legenda.cor"}

    @staticmethod
    def _pegar(cfg, chave):
        d = cfg
        for parte in chave.split("."):
            d = d[parte]
        return d

    @staticmethod
    def _por(cfg, chave, valor):
        partes = chave.split(".")
        d = cfg
        for parte in partes[:-1]:
            d = d.setdefault(parte, {})
        d[partes[-1]] = valor

    def _para_tela(self, cfg):
        self._carregando = True
        try:
            for chave, var in self.vars.items():
                if chave.startswith("_"):
                    continue
                try:
                    v = self._pegar(cfg, chave)
                except (KeyError, TypeError):
                    continue
                if isinstance(var, tk.BooleanVar):
                    var.set(bool(v))
                elif chave in self.TEXTOS:
                    var.set(str(v))
                else:
                    var.set(fmt(v))
            for chave, (caminho, mapa) in self.MAPAS.items():
                self.vars[chave].set(mapa.get(self._pegar(cfg, caminho), next(iter(mapa.values()))))
            self._mostrar_fonte(cfg["legenda"].get("fonte", ""))
        finally:
            self._carregando = False

    def _da_tela(self):
        cfg = M.completar(self.cfg)
        for chave, var in self.vars.items():
            if chave.startswith("_"):
                continue
            if isinstance(var, tk.BooleanVar):
                v = bool(var.get())
            elif chave in self.TEXTOS:
                v = var.get()
            else:
                v = numero(var.get(), self._pegar(M.PADRAO, chave) if chave != "copias" else 1)
            self._por(cfg, chave, v)
        for chave, (caminho, mapa) in self.MAPAS.items():
            inv = {t: k for k, t in mapa.items()}
            self._por(cfg, caminho, inv.get(self.vars[chave].get(), next(iter(mapa))))
        nome_fonte = self.vars["_fonte"].get() if "_fonte" in self.vars else ""
        if self.fontes:                     # lista pronta: o nome escolhido manda
            cfg["legenda"]["fonte"] = self.fontes.get(nome_fonte, "")
        # lista ainda carregando: mantém a fonte que já estava (senão ela se perdia)
        cfg["copias"] = max(1, int(cfg["copias"]))
        cfg["dpi"] = int(min(1200, max(72, cfg["dpi"])))
        cfg["qualidade"] = int(min(100, max(30, cfg["qualidade"])))
        return cfg

    # ── mudanças ──────────────────────────────────────────────────────────────
    def _mudou(self):
        if self._carregando:
            return
        self._marcar_personalizada()
        self._agendar()

    def _marcar_personalizada(self):
        """Mexeu num número que não bate com o modelo escolhido: vira 'Personalizada'."""
        cfg = self._da_tela()
        self._carregando = True
        try:
            f = M.FOLHAS.get(cfg["folha"]["modelo"])
            if f and (abs(min(cfg["folha"]["w"], cfg["folha"]["h"]) - min(f)) > 0.01 or
                      abs(max(cfg["folha"]["w"], cfg["folha"]["h"]) - max(f)) > 0.01):
                self.vars["folha.modelo"].set(M.FOLHA_PERSONALIZADA)
            p = M.POLAROIDS.get(cfg["polaroid"]["modelo"])
            if p and any(abs(cfg["polaroid"][k] - p[k]) > 0.01 for k in p):
                self.vars["polaroid.modelo"].set(M.POLAROID_PERSONALIZADA)
        finally:
            self._carregando = False

    def _trocou_folha(self):
        nome = self.vars["folha.modelo"].get()
        if nome in M.FOLHAS:
            w, h = M.FOLHAS[nome]
            self._carregando = True
            self.vars["folha.w"].set(fmt(w)); self.vars["folha.h"].set(fmt(h))
            self._carregando = False
        self._agendar()

    def _trocou_polaroid(self):
        nome = self.vars["polaroid.modelo"].get()
        if nome in M.POLAROIDS:
            self._carregando = True
            for k, v in M.POLAROIDS[nome].items():
                self.vars[f"polaroid.{k}"].set(fmt(v))
            self._carregando = False
        self._agendar()

    def _margem_todas(self):
        v = self.vars["_margem_todas"].get()
        for ch in ("margem.topo", "margem.base", "margem.esq", "margem.dir"):
            self.vars[ch].set(v)

    def _agendar(self, ms=250):
        if self._agenda:
            self.raiz.after_cancel(self._agenda)
        self._agenda = self.raiz.after(ms, self._atualizar)

    def _atualizar(self):
        self._agenda = None
        self.cfg = self._da_tela()
        R.gravar_json(R.ARQ_CONFIG, {"cfg": self.cfg, "pasta": self.pasta})
        try:
            pol = M.medidas_polaroid(self.cfg)
            self.lbl_pol.configure(text=f"Foto {fmt(round(pol['foto_w'], 2))} × {fmt(round(pol['foto_h'], 2))} mm  ·  "
                                        f"base (legenda) {fmt(round(pol['base'], 2))} mm", fg=ACCENT)
            lay, total, paginas = M.resumo(self.fotos, self.cfg)
        except M.ConfigInvalida as e:
            self.lbl_erro.configure(text=f"⚠ {e}")
            self.lbl_info.configure(text="")
            self.bt_gerar.configure(state="disabled")
            self.palco.delete("all")
            return
        self.lbl_erro.configure(text="" if lay["por_folha"] else
                                "⚠ Nenhuma polaroid cabe nessa folha — diminua as margens ou a polaroid.")
        self.bt_gerar.configure(state="normal" if (lay["por_folha"] and self.fotos and not self.gerando) else "disabled")
        mr = lay["margem_real"]
        giro = "  ·  deitadas" if lay["girada"] else ""
        self.lbl_info.configure(text=(
            f"{lay['cols']} × {lay['rows']} = {lay['por_folha']} por folha{giro}  ·  "
            f"{total} polaroid(s) em {paginas} folha(s)  ·  aproveita {lay['aproveitamento'] * 100:.0f}% do papel\n"
            f"Margem real: {fmt(mr[1])} em cima, {fmt(mr[3])} embaixo, {fmt(mr[0])} à esquerda, {fmt(mr[2])} à direita (mm)"))
        self.paginas = max(1, paginas)
        self.pagina = min(self.pagina, self.paginas - 1)
        self.lbl_pag.configure(text=f"{self.pagina + 1} / {self.paginas}")
        rosto = M.tem_detector_de_rosto()
        self.lbl_rosto.configure(text="" if rosto else "Detector de rosto indisponível neste computador — "
                                                       "'Centralizar no rosto' corta pelo centro.")
        self._desenhar_previa()

    def _virar(self, d):
        self.pagina = max(0, min(getattr(self, "paginas", 1) - 1, self.pagina + d))
        self._agendar(10)

    # ── prévia (numa thread: abrir foto grande não pode travar a janela) ──────
    def _miniatura(self, caminho):
        chave = str(caminho)
        if chave not in self._miniaturas:
            img = M.abrir_foto(caminho)
            img.thumbnail((900, 900))
            self._miniaturas[chave] = img
        return self._miniaturas[chave].copy()

    def _desenhar_previa(self):
        self._previa_ger += 1
        ger = self._previa_ger
        larg = max(200, self.palco.winfo_width() - 30)
        alt = max(200, self.palco.winfo_height() - 30)
        cfg = self.cfg
        fotos = list(self.fotos)
        pagina = self.pagina

        def trabalho():
            try:
                fw, fh = M.medidas_folha(cfg)
                largura = int(min(larg, alt * fw / fh))
                img, _ = M.previa(fotos, cfg, largura, pagina, self._cache_prev, self._miniatura)
                self.fila.put(("previa", ger, img))
            except Exception as e:
                R.tombo("prévia", e)

        if len(self._cache_prev) > 300:
            self._cache_prev.clear()
        threading.Thread(target=trabalho, daemon=True).start()

    def _mostrar_previa(self, img):
        self._previa_img = ImageTk.PhotoImage(img)
        self.palco.delete("all")
        w, h = self.palco.winfo_width(), self.palco.winfo_height()
        self.palco.create_rectangle(w / 2 - img.width / 2 + 4, h / 2 - img.height / 2 + 4,
                                    w / 2 + img.width / 2 + 4, h / 2 + img.height / 2 + 4, fill="#0B0B12", width=0)
        self.palco.create_image(w / 2, h / 2, image=self._previa_img)

    # ── fotos ─────────────────────────────────────────────────────────────────
    def _escolher_pasta(self):
        p = filedialog.askdirectory(title="Pasta com as fotos", initialdir=self.pasta or str(Path.home()))
        if p:
            self._carregar_pasta(p)

    def _carregar_pasta(self, p):
        self.pasta = p
        self.fotos = M.listar_fotos(p)
        self._miniaturas.clear()
        self._cache_prev.clear()
        self.pagina = 0
        self.lbl_pasta.configure(text=Path(p).name, fg=FG)
        self.lbl_qtd.configure(text=f"{len(self.fotos)} foto(s)" if self.fotos else "nenhuma foto nessa pasta",
                               fg=OK if self.fotos else AVISO)
        R.anotar(f"pasta: {p} — {len(self.fotos)} fotos")
        self._agendar(10)

    # ── fontes ────────────────────────────────────────────────────────────────
    PADRAO_FONTE = "(padrão do sistema)"

    def _ler_fontes(self):
        try:
            self.fila.put(("fontes", fontes.listar()))
        except Exception as e:
            R.tombo("fontes", e)
            self.fila.put(("fontes", {}))

    def _mostrar_fonte(self, caminho):
        nome = next((n for n, c in self.fontes.items() if c == caminho), None)
        if nome is None:
            nome = self.PADRAO_FONTE if not caminho else (Path(caminho).stem if not self.fontes else self.PADRAO_FONTE)
        self.vars.setdefault("_fonte", tk.StringVar()).set(nome)

    # ── perfis ────────────────────────────────────────────────────────────────
    def _salvar_perfil(self):
        janela = tk.Toplevel(self.raiz, bg=CARD, padx=16, pady=14)
        janela.title("Salvar perfil")
        janela.transient(self.raiz)
        janela.grab_set()
        self._rotulo(janela, "Nome do perfil", FG, 9).pack(anchor="w")
        var = tk.StringVar(value=self.vars["_perfil"].get())
        e = tk.Entry(janela, textvariable=var, width=34, bg=CAMPO, fg=FG, insertbackground=FG, relief="flat",
                     font=("Segoe UI", 10))
        e.pack(pady=6, ipady=3)
        e.focus_set()

        def ok(_=None):
            nome = var.get().strip()
            if not nome:
                return
            self.perfis[nome] = self._da_tela()
            R.gravar_json(R.ARQ_PERFIS, self.perfis)
            self.cb_perfil.configure(values=sorted(self.perfis))
            self.vars["_perfil"].set(nome)
            self._status(f"Perfil “{nome}” salvo.", OK)
            janela.destroy()

        e.bind("<Return>", ok)
        self._botao(janela, "Salvar", ok, primario=True).pack(anchor="e")

    def _carregar_perfil(self):
        nome = self.vars["_perfil"].get()
        if nome in self.perfis:
            self.cfg = M.completar(self.perfis[nome])
            self._para_tela(self.cfg)
            self._agendar(10)
            self._status(f"Perfil “{nome}” aberto.", OK)

    def _excluir_perfil(self):
        nome = self.vars["_perfil"].get()
        if nome in self.perfis and messagebox.askyesno("Excluir perfil", f"Excluir o perfil “{nome}”?", parent=self.raiz):
            del self.perfis[nome]
            R.gravar_json(R.ARQ_PERFIS, self.perfis)
            self.cb_perfil.configure(values=sorted(self.perfis))
            self.vars["_perfil"].set("")

    def _restaurar(self):
        if messagebox.askyesno("Voltar ao padrão", "Voltar todas as configurações ao padrão?\n"
                               "(os perfis salvos não são apagados)", parent=self.raiz):
            self.cfg = M.completar({})
            self._para_tela(self.cfg)
            self._agendar(10)

    # ── gerar ─────────────────────────────────────────────────────────────────
    def _status(self, texto, cor=MUTED):
        self.lbl_status.configure(text=texto, fg=cor)

    def _gerar(self):
        if self.gerando:
            self._cancelar = True
            self._status("Cancelando…", AVISO)
            return
        cfg = self._da_tela()
        try:
            lay, total, paginas = M.resumo(self.fotos, cfg)
        except M.ConfigInvalida as e:
            messagebox.showerror("Configuração", str(e), parent=self.raiz)
            return
        if not self.fotos:
            messagebox.showinfo("Sem fotos", "Escolha a pasta com as fotos primeiro.", parent=self.raiz)
            return
        nome = f"polaroids-{Path(self.pasta).name or 'fotos'}.pdf"
        destino = filedialog.asksaveasfilename(title="Salvar PDF", defaultextension=".pdf", initialfile=nome,
                                               initialdir=self.pasta or str(Path.home()),
                                               filetypes=[("PDF", "*.pdf")])
        if not destino:
            return
        self.gerando, self._cancelar = True, False
        self.bt_gerar.configure(text="Cancelar", bg=PERIGO)
        self.barra.configure(maximum=total, value=0)
        R.anotar(f"gerar: {total} polaroids, {paginas} folhas → {destino}")
        fotos = list(self.fotos)

        def trabalho():
            try:
                info = M.gerar_pdf(fotos, cfg, destino,
                                   progresso=lambda i, n, nome: self.fila.put(("prog", i, n, nome)),
                                   cancelar=lambda: self._cancelar)
                self.fila.put(("fim", info))
            except Exception as e:
                R.tombo("gerar", e)
                self.fila.put(("erro", str(e)))

        threading.Thread(target=trabalho, daemon=True).start()

    def _fim(self, info):
        self.gerando = False
        self.bt_gerar.configure(text="Gerar PDF", bg=ACCENT)
        if info.get("cancelado"):
            self._status("Cancelado — o PDF ficou com o que já tinha saído.", AVISO)
            return
        txt = f"{info['polaroids']} polaroid(s) em {info['paginas']} folha(s)"
        if self.cfg["foto"].get("enquadrar") == "rosto":
            txt += f" · rosto achado em {info['com_rosto']}"
        self._status("PDF gerado! " + txt, OK)
        R.anotar("ok: " + txt)
        aviso = ""
        if info["problemas"]:
            aviso = "\n\nNão consegui usar:\n" + "\n".join(f"• {n}: {e}" for n, e in info["problemas"][:10])
        if messagebox.askyesno("PDF pronto", f"{txt}.{aviso}\n\nAbrir o PDF agora?", parent=self.raiz):
            abrir_no_sistema(info["arquivo"])
        self._agendar(10)

    # ── fila da thread → janela ───────────────────────────────────────────────
    def _bombear(self):
        try:
            while True:
                msg = self.fila.get_nowait()
                tipo = msg[0]
                if tipo == "previa" and msg[1] == self._previa_ger:
                    self._mostrar_previa(msg[2])
                elif tipo == "fontes":
                    self.fontes = msg[1]
                    atual = self.cfg["legenda"].get("fonte", "")
                    self.cb_fonte.configure(values=[self.PADRAO_FONTE] + list(self.fontes))
                    self._carregando = True
                    self._mostrar_fonte(atual)
                    self._carregando = False
                elif tipo == "prog":
                    _, i, n, nome = msg
                    self.barra.configure(value=i)
                    self._status(f"{i}/{n} · {nome}")
                elif tipo == "fim":
                    self._fim(msg[1])
                elif tipo == "erro":
                    self.gerando = False
                    self.bt_gerar.configure(text="Gerar PDF", bg=ACCENT)
                    self._status("Erro ao gerar.", PERIGO)
                    messagebox.showerror("Não deu pra gerar", msg[1], parent=self.raiz)
        except queue.Empty:
            pass
        self.raiz.after(80, self._bombear)


def abrir_no_sistema(caminho):
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(caminho))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(caminho)])
        else:
            subprocess.Popen(["xdg-open", str(caminho)])
    except Exception as e:
        R.tombo("abrir PDF", e)


def principal():
    R.iniciar()
    raiz = tk.Tk()
    try:
        icone = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "icone.ico"
        if icone.exists() and sys.platform.startswith("win"):
            raiz.iconbitmap(str(icone))
    except Exception:
        pass
    App(raiz)
    raiz.mainloop()
