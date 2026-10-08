#!/usr/bin/env python3
"""Editor de uma foto: abre ao clicar numa polaroid da prévia.

Mostra a polaroid grande, desenhada pelo MESMO motor do PDF (motor.montar_polaroid),
e deixa arrastar a foto dentro da janela, aproximar/afastar e girar. O resultado é
um "ajuste" (ver motor.ajuste_auto) guardado por foto na App — a prévia e o PDF usam.

⚠ No Mac (Tk 9) a roda do mouse não chega no tkinter: o zoom tem barra e botões,
a roda é só um extra pra quem tem.
"""
import sys
import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from . import motor as M

PASSO_ZOOM = 1.15


class Editor(tk.Toplevel):
    def __init__(self, app, indice, mostrar=True):
        super().__init__(app.raiz)
        if not mostrar:
            self.withdraw()
        from .app import BG, CARD, FG, MUTED, ACCENT, ACCENT_H, OK, CAMPO
        self.cores = dict(BG=BG, CARD=CARD, FG=FG, MUTED=MUTED, ACCENT=ACCENT, ACCENT_H=ACCENT_H, OK=OK, CAMPO=CAMPO)
        self.app = app
        self.configure(bg=BG)
        self.title("Ajustar foto")
        self.transient(app.raiz)
        self.resizable(False, False)
        self._pendente = None
        self._arrasto = None
        self._img_tk = None
        self._mexendo_barra = False

        self.tela = tk.Canvas(self, bg="#141420", highlightthickness=0, cursor="fleur")
        rod = tk.Frame(self, bg=BG)
        rod.pack(side="bottom", fill="x", padx=14, pady=(0, 14))      # fixo antes do que expande
        self.lbl_nome = tk.Label(self, bg=BG, fg=FG, font=("Segoe UI", 10, "bold"), anchor="w")
        self.lbl_nome.pack(side="top", fill="x", padx=14, pady=(12, 0))
        self.lbl_estado = tk.Label(self, bg=BG, fg=MUTED, font=("Segoe UI", 8), anchor="w")
        self.lbl_estado.pack(side="top", fill="x", padx=14)
        self.tela.pack(side="top", padx=14, pady=10)

        linha1 = tk.Frame(rod, bg=BG); linha1.pack(fill="x")
        b = self._botao
        b(linha1, "−", lambda: self._zoom_vezes(1 / PASSO_ZOOM)).pack(side="left")
        self.var_zoom = tk.DoubleVar(value=1.0)
        self.barra = ttk.Scale(linha1, variable=self.var_zoom, orient="horizontal", length=220,
                               command=self._barra_mudou)
        self.barra.pack(side="left", padx=6, fill="x", expand=True)
        b(linha1, "+", lambda: self._zoom_vezes(PASSO_ZOOM)).pack(side="left")
        self.lbl_zoom = tk.Label(linha1, bg=BG, fg=MUTED, font=("Segoe UI", 9), width=6)
        self.lbl_zoom.pack(side="left", padx=(6, 0))

        linha2 = tk.Frame(rod, bg=BG); linha2.pack(fill="x", pady=(8, 0))
        b(linha2, "↻ Girar", self._girar).pack(side="left")
        b(linha2, "Automático", self._automatico).pack(side="left", padx=6)
        self.bt_pronto = b(linha2, "Pronto", self.fechar, primario=True)
        self.bt_pronto.pack(side="right")
        b(linha2, "›", lambda: self._ir(1)).pack(side="right", padx=(0, 10))
        self.lbl_pos = tk.Label(linha2, bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_pos.pack(side="right", padx=4)
        b(linha2, "‹", lambda: self._ir(-1)).pack(side="right")

        dica = ("Arraste a foto pra mover · use a barra ou − / + pra aproximar"
                + ("" if sys.platform == "darwin" else " (ou a roda do mouse)"))
        tk.Label(rod, text=dica, bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(fill="x", pady=(8, 0))

        self.tela.bind("<ButtonPress-1>", self._pegou)
        self.tela.bind("<B1-Motion>", self._arrastou)
        self.tela.bind("<ButtonRelease-1>", lambda e: setattr(self, "_arrasto", None))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.tela.bind(ev, self._roda)
        self.bind("<Escape>", lambda e: self.fechar())
        self.bind("<Return>", lambda e: self.fechar())
        self.bind("<Left>", lambda e: self._ir(-1))
        self.bind("<Right>", lambda e: self._ir(1))
        self.protocol("WM_DELETE_WINDOW", self.fechar)

        self._abrir(indice)
        if mostrar:
            self.update_idletasks()
            x = app.raiz.winfo_rootx() + (app.raiz.winfo_width() - self.winfo_reqwidth()) // 2
            y = app.raiz.winfo_rooty() + max(0, (app.raiz.winfo_height() - self.winfo_reqheight()) // 2)
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
            self.grab_set()
            self.focus_set()

    def _botao(self, pai, texto, cmd, primario=False):
        """Botão feito de Label: no Mac o tk.Button ignora a cor e sai branco com texto
        branco (ilegível). Label respeita a cor nos dois sistemas."""
        c = self.cores
        fundo, sobre = (c["ACCENT"], c["ACCENT_H"]) if primario else (c["CAMPO"], c["CARD"])
        b = tk.Label(pai, text=texto, bg=fundo, fg=c["FG"], cursor="hand2", padx=14, pady=6 if primario else 4,
                     font=("Segoe UI", 10, "bold") if primario else ("Segoe UI", 10))
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg=sobre))
        b.bind("<Leave>", lambda e: b.configure(bg=fundo))
        return b

    # ── qual foto ─────────────────────────────────────────────────────────────
    def _abrir(self, indice):
        app = self.app
        self.indice = indice % len(app.fotos)
        self.caminho = app.fotos[self.indice]
        self.chave = str(self.caminho)
        self.cfg = M.completar(app.cfg)
        pol = M.medidas_polaroid(self.cfg)
        # tamanho na tela: a polaroid em pé com até ~60% da altura da tela
        alt_max = max(320, min(620, int(self.winfo_screenheight() * 0.6)))
        larg_max = 460
        ppm = min(alt_max / pol["h"], larg_max / pol["w"])
        self.dpi = ppm * 25.4
        self.janela = (round(pol["lat"] * ppm), round(pol["topo"] * ppm),
                       max(1, round(pol["foto_w"] * ppm)), max(1, round(pol["foto_h"] * ppm)))
        self.tela.configure(width=max(1, round(pol["w"] * ppm)), height=max(1, round(pol["h"] * ppm)))

        self.original = app._miniatura(self.caminho)
        self.legenda = M.texto_da_legenda(self.cfg, self.caminho)
        salvo = app.ajustes.get(self.chave)
        self.mexeu = False
        if salvo:
            self._usar(dict(salvo), manual=True)
        else:
            self._usar(self._auto(), manual=False)
        self.lbl_nome.configure(text=self.caminho.name if hasattr(self.caminho, "name") else self.chave)
        self.lbl_pos.configure(text=f"{self.indice + 1} / {len(app.fotos)}")

    def _auto(self):
        _, _, fw, fh = self.janela
        aj, _ = M.ajuste_auto(self.original, fw, fh, self.cfg["foto"].get("enquadrar", "rosto"),
                              M._num(self.cfg["foto"].get("subir_rosto"), 4.0))
        return aj

    def _usar(self, aj, manual):
        self.foto = M.girar(self.original, aj.get("giro"))
        _, _, fw, fh = self.janela
        self.aj = M.limpar_ajuste(self.foto, fw, fh, aj)
        self.manual = manual
        zmin = M.zoom_minimo(*self.foto.size, fw, fh)
        self._mexendo_barra = True
        self.barra.configure(from_=round(zmin, 2), to=M.ZOOM_MAX)
        self.var_zoom.set(self.aj["zoom"])
        self._mexendo_barra = False
        self._desenhar()

    # ── mexer ─────────────────────────────────────────────────────────────────
    def _mudou(self):
        _, _, fw, fh = self.janela
        self.aj = M.limpar_ajuste(self.foto, fw, fh, self.aj)
        self.mexeu = self.manual = True
        self._mexendo_barra = True
        self.var_zoom.set(self.aj["zoom"])
        self._mexendo_barra = False
        if self._pendente is None:                       # junta os movimentos do mouse
            self._pendente = self.after(15, self._desenhar)

    def _pegou(self, e):
        self._arrasto = (e.x, e.y)

    def _arrastou(self, e):
        if not self._arrasto:
            return
        x0, y0 = self._arrasto
        self._arrasto = (e.x, e.y)                       # passo a passo: na borda não "gruda"
        W, H = self.foto.size
        _, _, fw, fh = self.janela
        _, _, cw, _ = M.caixa_do_recorte(W, H, fw, fh, self.aj)
        px_foto = cw / fw                                # px da foto por px da tela
        # arrastar pra direita leva a FOTO pra direita: o recorte anda pra esquerda
        self.aj["cx"] -= (e.x - x0) * px_foto / W
        self.aj["cy"] -= (e.y - y0) * px_foto / H
        self._mudou()

    def _zoom_vezes(self, f):
        self.aj["zoom"] = self.aj["zoom"] * f
        self._mudou()

    def _barra_mudou(self, valor):
        # o Tk chama isto DEPOIS (no ocioso) também quando o programa põe o valor na
        # barra: só vale se a pessoa levou a barra pra outro zoom
        if self._mexendo_barra or abs(float(valor) - self.aj["zoom"]) < 0.006:
            return
        self.aj["zoom"] = float(valor)
        self._mudou()

    def _roda(self, e):
        if e.num == 4 or (e.num != 5 and e.delta > 0):
            self._zoom_vezes(PASSO_ZOOM ** 0.5)
        else:
            self._zoom_vezes(PASSO_ZOOM ** -0.5)

    def _girar(self):
        giro = (int(self.aj.get("giro", 0)) + 90) % 360
        self.mexeu = True
        self._usar(dict(cx=0.5, cy=0.5, zoom=1.0, giro=giro), manual=True)

    def _automatico(self):
        self.app.ajustes.pop(self.chave, None)
        self.app._ajustes_mudaram()
        self.mexeu = False
        self._usar(self._auto(), manual=False)

    # ── tela ──────────────────────────────────────────────────────────────────
    def _desenhar(self):
        self._pendente = None
        pol, _ = M.montar_polaroid(self.original, self.cfg, self.legenda, self.dpi, self.aj)
        self._img_tk = ImageTk.PhotoImage(pol)
        self.tela.delete("all")
        self.tela.create_image(0, 0, image=self._img_tk, anchor="nw")
        fx, fy, fw, fh = self.janela
        self.tela.create_rectangle(fx, fy, fx + fw - 1, fy + fh - 1, outline=self.cores["ACCENT"], dash=(3, 3))
        self.lbl_zoom.configure(text=f"{self.aj['zoom'] * 100:.0f}%")
        self.lbl_estado.configure(text="Ajustada à mão" if self.manual else "Automático (como o programa escolheu)",
                                  fg=self.cores["OK"] if self.manual else self.cores["MUTED"])

    # ── guardar e sair ────────────────────────────────────────────────────────
    def _guardar(self):
        if self.mexeu:
            self.app.ajustes[self.chave] = {k: (round(v, 5) if isinstance(v, float) else v)
                                            for k, v in self.aj.items()}
            self.app._ajustes_mudaram()
            self.mexeu = False

    def _ir(self, d):
        self._guardar()
        self._abrir(self.indice + d)

    def fechar(self):
        self._guardar()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        self.app.editor = None
