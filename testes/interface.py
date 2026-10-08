#!/usr/bin/env python3
"""Teste da janela — abre ESCONDIDA (withdraw) e mexe como o usuário mexeria.
⚠ Nunca deixar janela aparecer: a bateria roda no computador de quem está trabalhando."""
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# console do Windows (cp1252) não imprime ✓ ✗ — sem isto a bateria cai no primeiro print
for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
sys.path.insert(0, str(RAIZ))

import fitz
from PIL import Image

from polaroid import registro as R

CAIXA = Path(tempfile.mkdtemp(prefix="polaroid_ui_"))
R.PASTA = CAIXA
R.ARQ_CONFIG, R.ARQ_PERFIS, R.ARQ_LOG = CAIXA / "config.json", CAIXA / "perfis.json", CAIXA / "registro.txt"

import tkinter as tk
from tkinter import filedialog, messagebox

from polaroid import app as A, motor as M

ok = falhas = 0


def conferir(nome, cond, extra=""):
    global ok, falhas
    ok += bool(cond); falhas += not cond
    print(("  ✓ " if cond else "  ✗ ") + nome + ("" if cond else f"  →  {extra}"))


FOTOS = CAIXA / "fotos"; FOTOS.mkdir()
for i, c in enumerate([(200, 40, 40), (40, 160, 70), (40, 70, 200), (230, 170, 30), (130, 50, 170), (20, 20, 20)], 1):
    Image.new("RGB", (1500, 1100), c).save(FOTOS / f"img{i}.jpg")

# caixas de diálogo não podem esperar clique
avisos = []
messagebox.showinfo = lambda *a, **k: avisos.append(("info", a))
messagebox.showerror = lambda *a, **k: avisos.append(("erro", a))
messagebox.askyesno = lambda *a, **k: False
SAIDA = CAIXA / "saida.pdf"
filedialog.asksaveasfilename = lambda **k: str(SAIDA)

raiz = tk.Tk()
raiz.withdraw()
app = A.App(raiz)


def girar(seg=0.6):
    fim = time.time() + seg
    while time.time() < fim:
        raiz.update()
        time.sleep(0.02)


def esperar(cond, seg=20):
    fim = time.time() + seg
    while time.time() < fim:
        raiz.update()
        if cond():
            return True
        time.sleep(0.03)
    return False


print("\n1 · abrir e carregar a pasta")
app._carregar_pasta(str(FOTOS)); girar()
conferir("achou as 6 fotos", len(app.fotos) == 6, len(app.fotos))
conferir("info mostra 4 por folha e 2 folhas", "4 por folha" in app.lbl_info.cget("text") and "2 folha" in app.lbl_info.cget("text"),
         app.lbl_info.cget("text"))
conferir("a prévia foi desenhada", esperar(lambda: app._previa_img is not None), "")

print("\n2 · trocar folha e polaroid")
app.vars["folha.modelo"].set("33 × 48 cm"); app._trocou_folha(); girar()
conferir("33 × 48 preenche as medidas", (app.vars["folha.w"].get(), app.vars["folha.h"].get()) == ("330", "480"),
         (app.vars["folha.w"].get(), app.vars["folha.h"].get()))
app.vars["polaroid.modelo"].set("Instax Mini (5,4 × 8,6 cm)"); app._trocou_polaroid(); girar()
conferir("Instax Mini preenche as medidas", app.vars["polaroid.w"].get() == "54" and app.vars["polaroid.foto_h"].get() == "62",
         (app.vars["polaroid.w"].get(), app.vars["polaroid.foto_h"].get()))
conferir("  mostra a janela da foto e a base", "46 × 62" in app.lbl_pol.cget("text"), app.lbl_pol.cget("text"))
app.vars["polaroid.lat"].set("4,5"); girar()
conferir("digitar com vírgula vale (4,5)", abs(app.cfg["polaroid"]["lat"] - 4.5) < 1e-9, app.cfg["polaroid"]["lat"])
conferir("  e o modelo virou 'Personalizada'", app.vars["polaroid.modelo"].get() == M.POLAROID_PERSONALIZADA,
         app.vars["polaroid.modelo"].get())
app.vars["folha.w"].set("300"); girar()
conferir("mexer na folha vira 'Personalizada'", app.vars["folha.modelo"].get() == M.FOLHA_PERSONALIZADA, app.vars["folha.modelo"].get())

print("\n3 · erro de configuração aparece e trava o Gerar")
app.vars["polaroid.foto_h"].set("200"); girar()
conferir("aviso em vermelho", "passam da altura" in app.lbl_erro.cget("text"), app.lbl_erro.cget("text"))
conferir("  botão Gerar desligado", str(app.bt_gerar.cget("state")) == "disabled", app.bt_gerar.cget("state"))
app.vars["polaroid.foto_h"].set("62"); girar()
conferir("  corrigiu: aviso some e Gerar volta", app.lbl_erro.cget("text") == "" and str(app.bt_gerar.cget("state")) == "normal",
         (app.lbl_erro.cget("text"), app.bt_gerar.cget("state")))

print("\n4 · margem, espaço, sangria, marcas e legenda pela tela")
app.vars["_margem_todas"].set("12"); app._margem_todas(); girar()
conferir("'Aplicar nas 4' põe a mesma margem", all(app.cfg["margem"][k] == 12 for k in ("topo", "base", "esq", "dir")), app.cfg["margem"])
app.vars["espaco.h"].set("3"); app.vars["sangria"].set("1,5"); app.vars["marcas.comprimento"].set("5")
app.vars["_legenda"].set(M.LEGENDA["nome"]); app.vars["_enquadrar"].set(M.ENQUADRAR["centro"])
app.vars["_giro"].set(M.GIRO["em_pe"]); app._mudou(); girar()
c = app.cfg
conferir("tudo chega na configuração", (c["espaco"]["h"], c["sangria"], c["marcas"]["comprimento"], c["legenda"]["modo"],
                                        c["foto"]["enquadrar"], c["giro"]) == (3, 1.5, 5, "nome", "centro", "em_pe"),
         (c["espaco"]["h"], c["sangria"], c["marcas"]["comprimento"], c["legenda"]["modo"], c["foto"]["enquadrar"], c["giro"]))

print("\n5 · gerar o PDF pela janela")
app._gerar()
conferir("terminou de gerar", esperar(lambda: not app.gerando, 60), "")
conferir("  o PDF existe", SAIDA.exists(), SAIDA)
if SAIDA.exists():
    d = fitz.open(str(SAIDA))
    conferir("  folha 300 × 480 mm", abs(d[0].rect.width / M.MM - 300) < 0.1 and abs(d[0].rect.height / M.MM - 480) < 0.1,
             (d[0].rect.width / M.MM, d[0].rect.height / M.MM))
    conferir("  6 polaroids numa folha só", len(d) == 1 and len(d[0].get_image_info()) == 6, (len(d), len(d[0].get_image_info())))
    d.close()
conferir("  status diz que deu certo", "PDF gerado" in app.lbl_status.cget("text"), app.lbl_status.cget("text"))

print("\n6 · perfis e memória")
app.perfis["Festa"] = app._da_tela(); R.gravar_json(R.ARQ_PERFIS, app.perfis)
app._restaurar = lambda: None
app.cfg = M.completar({}); app._para_tela(app.cfg); girar()
conferir("voltar ao padrão: A4", app.vars["folha.w"].get() == "210", app.vars["folha.w"].get())
app.vars["_perfil"].set("Festa"); app._carregar_perfil(); girar()
conferir("abrir o perfil 'Festa' volta tudo", app.vars["folha.w"].get() == "300" and app.vars["sangria"].get() == "1,5",
         (app.vars["folha.w"].get(), app.vars["sangria"].get()))
salvo = R.ler_json(R.ARQ_CONFIG, {})
conferir("a configuração ficou salva pra próxima abertura", salvo.get("cfg", {}).get("folha", {}).get("w") == 300 and
         salvo.get("pasta") == str(FOTOS), (salvo.get("cfg", {}).get("folha"), salvo.get("pasta")))
raiz.destroy()
raiz = tk.Tk(); raiz.withdraw()
app2 = A.App(raiz); girar()
conferir("reabrindo: mesma folha e mesma pasta", app2.vars["folha.w"].get() == "300" and len(app2.fotos) == 6,
         (app2.vars["folha.w"].get(), len(app2.fotos)))

print("\n7 · roda do mouse")
col = app2.col
col.tela.yview_moveto(0); girar(0.2)
antes = col.tela.yview()[0]
campo = next(w for w in col.dentro.winfo_children()[2].winfo_children() if isinstance(w, tk.Frame))
col._roda(True)
campo.event_generate("<MouseWheel>", delta=-120, when="now"); girar(0.2)
conferir("rolar em cima de um campo rola a coluna", col.tela.yview()[0] > antes, (antes, col.tela.yview()[0]))
cb = app2.cb_folha; antes_v = cb.get()
cb.event_generate("<MouseWheel>", delta=-120, when="now"); girar(0.2)
conferir("rolar em cima da caixa da folha NÃO troca a folha", cb.get() == antes_v, (antes_v, cb.get()))
col._roda(False)
raiz.destroy()

print(f"\n{'═' * 70}\n{ok}/{ok + falhas} passaram" + ("  — tudo certo" if not falhas else ""))
sys.exit(1 if falhas else 0)
