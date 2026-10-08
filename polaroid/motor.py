#!/usr/bin/env python3
"""
O motor do Gerador de Polaroids — tudo que decide ONDE e COMO cada foto sai.

Nada aqui conhece a janela: entra um dicionário de configuração e uma lista de
fotos, sai um PDF. É assim que dá pra testar a geometria medindo o PDF, sem abrir
interface nenhuma (testes/rodar.py).

Medidas sempre em MILÍMETROS. O PDF é desenhado em pontos (1 mm = 72/25,4 pt).

Como uma polaroid é montada (olhando ela em pé):

    ┌──────────────────────┐  ← corte
    │      borda topo      │
    │  ┌────────────────┐  │
    │  │                │  │
    │  │      FOTO      │  │  borda lateral dos dois lados
    │  │                │  │
    │  └────────────────┘  │
    │   base (legenda)     │  ← o que sobra embaixo
    └──────────────────────┘

A foto tem a largura da polaroid menos as duas bordas laterais. A altura da foto
é escolhida (quadrada por padrão). A base é o resto: altura − topo − foto.

Sangria: a moldura passa do corte, pra não sobrar fio de papel na borda quando a
guilhotina ou o plotter variam meio milímetro. Entre duas polaroids vizinhas a
sangria nunca passa da metade do espaço entre elas — senão uma invadiria a outra.
"""
import copy
import io
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

MM = 72.0 / 25.4                     # pontos por milímetro
SUPORTADAS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"}

# ── folhas ────────────────────────────────────────────────────────────────────
# (largura, altura) em pé, em mm
FOLHAS = {
    "A4 (21 × 29,7 cm)": (210.0, 297.0),
    "A3 (29,7 × 42 cm)": (297.0, 420.0),
    "A5 (14,8 × 21 cm)": (148.0, 210.0),
    "Carta (21,6 × 27,9 cm)": (215.9, 279.4),
    "Ofício (21,6 × 35,6 cm)": (215.9, 355.6),
    "Foto 10 × 15 cm": (100.0, 150.0),
    "Foto 13 × 18 cm": (130.0, 180.0),
    "Foto 15 × 21 cm": (150.0, 210.0),
    "Foto 20 × 25 cm": (200.0, 250.0),
    "Foto 20 × 30 cm": (200.0, 300.0),
    "30 × 40 cm": (300.0, 400.0),
    "SRA3 (32 × 45 cm)": (320.0, 450.0),
    "33 × 48 cm": (330.0, 480.0),
    "40 × 60 cm": (400.0, 600.0),
}
FOLHA_PERSONALIZADA = "Personalizada"

# ── modelos de polaroid ───────────────────────────────────────────────────────
# Os dois primeiros são os do programa antigo, nas MESMAS medidas — quem já
# imprimia com ele continua tirando o mesmo resultado.
POLAROIDS = {
    "Polaroid Clássica (8,8 × 10,7 cm)": dict(w=88.0, h=107.0, lat=4.5, topo=4.5, foto_h=79.0),
    "Mini (5 × 7 cm)": dict(w=50.0, h=70.0, lat=2.5, topo=2.5, foto_h=45.0),
    "Instax Mini (5,4 × 8,6 cm)": dict(w=54.0, h=86.0, lat=4.0, topo=7.0, foto_h=62.0),
    "Instax Square (7,2 × 8,6 cm)": dict(w=72.0, h=86.0, lat=5.0, topo=7.0, foto_h=62.0),
    "Instax Wide (10,8 × 8,6 cm)": dict(w=108.0, h=86.0, lat=4.5, topo=7.0, foto_h=62.0),
    "Polaroid Grande (10 × 12 cm)": dict(w=100.0, h=120.0, lat=5.0, topo=5.0, foto_h=90.0),
    "Polaroid 10 × 15 cm": dict(w=100.0, h=150.0, lat=6.0, topo=6.0, foto_h=110.0),
}
POLAROID_PERSONALIZADA = "Personalizada"

ENQUADRAR = {"rosto": "Centralizar no rosto", "centro": "Cortar pelo centro",
             "inteira": "Foto inteira (sem cortar)"}
LEGENDA = {"nenhuma": "Sem legenda", "texto": "Mesmo texto em todas",
           "nome": "Nome do arquivo"}
ALINHAR = {"centro": "Centro", "esquerda": "Esquerda", "direita": "Direita"}
GIRO = {"auto": "Automático (o que couber mais)", "em_pe": "Em pé", "deitada": "Deitada"}

PADRAO = {
    "folha": {"modelo": "A4 (21 × 29,7 cm)", "w": 210.0, "h": 297.0, "paisagem": False},
    "margem": {"topo": 5.0, "base": 5.0, "esq": 5.0, "dir": 5.0},
    "centralizar": True,
    "espaco": {"h": 2.0, "v": 2.0},
    "polaroid": {"modelo": "Polaroid Clássica (8,8 × 10,7 cm)", **POLAROIDS["Polaroid Clássica (8,8 × 10,7 cm)"]},
    "giro": "auto",
    "sangria": 0.0,
    "moldura_cor": "#FFFFFF",
    "contorno_foto": True,
    "contorno_cor": "#C8C8C8",
    "marcas": {"ligado": True, "comprimento": 3.0, "afastamento": 1.0, "espessura": 0.3,
               "linha_corte": False, "cor": "#000000"},
    "foto": {"enquadrar": "rosto", "subir_rosto": 4.0},
    "legenda": {"modo": "nenhuma", "texto": "", "fonte": "", "tamanho": 0.0,
                "cor": "#3C3C3C", "alinhar": "centro", "deslocar": 0.0},
    "copias": 1,
    "dpi": 300,
    "qualidade": 92,
}


class ConfigInvalida(Exception):
    """A configuração não fecha (ex.: a foto não cabe na polaroid). A mensagem diz por quê."""


def completar(cfg):
    """A config do usuário por cima do padrão — chave que faltar vem do padrão.
    Assim um perfil salvo numa versão antiga continua abrindo na nova."""
    base = copy.deepcopy(PADRAO)
    for k, v in (cfg or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    return base


def _num(v, padrao=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return padrao


def cor_rgb(hexa, padrao=(255, 255, 255)):
    h = str(hexa or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return padrao


# ── geometria ─────────────────────────────────────────────────────────────────
def medidas_polaroid(cfg):
    """Medidas da polaroid EM PÉ: w, h, lat, topo, foto_w, foto_h, base. Valida."""
    p = cfg["polaroid"]
    w, h = _num(p.get("w")), _num(p.get("h"))
    lat, topo, foto_h = _num(p.get("lat")), _num(p.get("topo")), _num(p.get("foto_h"))
    if w <= 0 or h <= 0:
        raise ConfigInvalida("o tamanho da polaroid tem que ser maior que zero")
    if lat < 0 or topo < 0:
        raise ConfigInvalida("borda não pode ser negativa")
    foto_w = w - 2 * lat
    if foto_w <= 0:
        raise ConfigInvalida(f"as bordas laterais ({lat:g} mm cada) comem a polaroid inteira")
    if foto_h <= 0:
        raise ConfigInvalida("a altura da foto tem que ser maior que zero")
    base = h - topo - foto_h
    if base < -1e-6:
        raise ConfigInvalida(
            f"a foto ({foto_h:g} mm) mais a borda de cima ({topo:g} mm) passam da "
            f"altura da polaroid ({h:g} mm)")
    return dict(w=w, h=h, lat=lat, topo=topo, foto_w=foto_w, foto_h=foto_h, base=max(0.0, base))


def medidas_folha(cfg):
    f = cfg["folha"]
    w, h = _num(f.get("w")), _num(f.get("h"))
    if w <= 0 or h <= 0:
        raise ConfigInvalida("o tamanho da folha tem que ser maior que zero")
    if f.get("paisagem"):
        w, h = max(w, h), min(w, h)
    else:
        w, h = min(w, h), max(w, h)
    return w, h


def _grade(area_w, area_h, cw, ch, gh, gv):
    cols = int(math.floor((area_w + gh + 1e-6) / (cw + gh))) if cw + gh > 0 else 0
    rows = int(math.floor((area_h + gv + 1e-6) / (ch + gv))) if ch + gv > 0 else 0
    return max(0, cols), max(0, rows)


def layout(cfg):
    """Onde cada polaroid cai na folha. Devolve um dicionário com tudo que a
    janela mostra e o PDF usa. Posições = canto de cima-esquerda do CORTE, em mm
    medidos do canto de cima-esquerda da folha."""
    cfg = completar(cfg)
    pol = medidas_polaroid(cfg)
    fw, fh = medidas_folha(cfg)
    m = {k: max(0.0, _num(cfg["margem"].get(k))) for k in ("topo", "base", "esq", "dir")}
    gh, gv = max(0.0, _num(cfg["espaco"].get("h"))), max(0.0, _num(cfg["espaco"].get("v")))
    area_w, area_h = fw - m["esq"] - m["dir"], fh - m["topo"] - m["base"]
    if area_w <= 0 or area_h <= 0:
        raise ConfigInvalida("as margens são maiores que a folha")

    em_pe = _grade(area_w, area_h, pol["w"], pol["h"], gh, gv)
    deitada = _grade(area_w, area_h, pol["h"], pol["w"], gh, gv)
    giro = cfg.get("giro", "auto")
    if giro == "deitada" or (giro == "auto" and deitada[0] * deitada[1] > em_pe[0] * em_pe[1]):
        girada, (cols, rows) = True, deitada
        cw, ch = pol["h"], pol["w"]
    else:
        girada, (cols, rows) = False, em_pe
        cw, ch = pol["w"], pol["h"]

    usado_w = cols * cw + max(0, cols - 1) * gh
    usado_h = rows * ch + max(0, rows - 1) * gv
    x0, y0 = m["esq"], m["topo"]
    if cfg.get("centralizar", True):
        x0 += (area_w - usado_w) / 2
        y0 += (area_h - usado_h) / 2
    posicoes = [(x0 + c * (cw + gh), y0 + r * (ch + gv)) for r in range(rows) for c in range(cols)]

    s = max(0.0, _num(cfg.get("sangria")))
    return dict(folha=(fw, fh), polaroid=pol, cols=cols, rows=rows, por_folha=cols * rows,
                celula=(cw, ch), girada=girada, posicoes=posicoes, espaco=(gh, gv),
                origem=(x0, y0), usado=(usado_w, usado_h), sangria=s,
                sangria_entre=(min(s, gh / 2), min(s, gv / 2)),
                aproveitamento=(cols * rows * pol["w"] * pol["h"]) / (fw * fh) if fw * fh else 0,
                margem_real=(round(x0, 2), round(y0, 2),
                             round(fw - x0 - usado_w, 2), round(fh - y0 - usado_h, 2)))


def sangria_da_posicao(lay, indice):
    """Quanto a moldura passa do corte em cada lado (esq, topo, dir, base), em mm.
    Pra fora do bloco: a sangria inteira. Entre vizinhos: no máximo meio espaço."""
    s = lay["sangria"]
    if s <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    cols, rows = lay["cols"], lay["rows"]
    c, r = indice % cols, indice // cols
    sh, sv = lay["sangria_entre"]
    return (s if c == 0 else sh, s if r == 0 else sv,
            s if c == cols - 1 else sh, s if r == rows - 1 else sv)


# ── fotos ─────────────────────────────────────────────────────────────────────
def _ordem_natural(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", Path(p).name)]


def listar_fotos(pasta):
    """As fotos da pasta, na ordem que o explorador mostra (foto2 antes de foto10)."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return []
    return sorted((p for p in pasta.iterdir()
                   if p.is_file() and p.suffix.lower() in SUPORTADAS and not p.name.startswith(".")),
                  key=_ordem_natural)


def abrir_foto(caminho):
    """Abre já virada certa (foto de celular guarda a orientação no EXIF)."""
    img = Image.open(str(caminho))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        fundo = Image.new("RGB", img.size, (255, 255, 255))
        if "A" in img.getbands():
            fundo.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        else:
            fundo.paste(img.convert("RGB"))
        img = fundo
    return img.convert("RGB")


_CASCATA = None


def _detector():
    """OpenCV é opcional: sem ele, 'centralizar no rosto' vira 'cortar pelo centro'."""
    global _CASCATA
    if _CASCATA is None:
        try:
            import cv2
            _CASCATA = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            if _CASCATA.empty():
                _CASCATA = False
        except Exception:
            _CASCATA = False
    return _CASCATA or None


def tem_detector_de_rosto():
    return _detector() is not None


def achar_rostos(img):
    """[(x, y, w, h)] em px da imagem, ou []."""
    det = _detector()
    if det is None:
        return []
    try:
        import numpy as np
        import cv2
        pequena = img.copy()
        pequena.thumbnail((900, 900))                 # rápido e suficiente pra achar rosto
        k = img.width / pequena.width
        cinza = np.array(pequena.convert("L"))
        achados = det.detectMultiScale(cinza, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        return [(int(x * k), int(y * k), int(w * k), int(h * k)) for (x, y, w, h) in achados]
    except Exception:
        return []


# ── enquadramento (automático ou ajustado à mão) ──────────────────────────────
# Um AJUSTE diz qual pedaço da foto aparece na janela da polaroid:
#   {"cx": 0..1, "cy": 0..1, "zoom": z, "giro": 0|90|180|270}
# cx/cy = centro do recorte, em fração da foto (depois de girada).
# zoom 1 = a foto cobre a janela inteira (o que o automático faz); acima disso aproxima;
# abaixo diminui até a foto inteira caber (o que sobra fica da cor da moldura).
# Fração em vez de pixel: vale igual pra miniatura da prévia e pra foto cheia do PDF.
ZOOM_MAX = 6.0


def _cobrir(W, H, prop):
    """Maior pedaço da foto na proporção da janela (largura, altura) em px."""
    return (H * prop, H) if W / H > prop else (W, W / prop)


def zoom_minimo(W, H, alvo_w, alvo_h):
    """O zoom em que a foto inteira cabe na janela."""
    prop = alvo_w / alvo_h
    return _cobrir(W, H, prop)[0] / max(W, H * prop)


def girar(img, giro):
    """Gira no sentido do relógio, em passos de 90°."""
    g = int(_num(giro)) % 360
    return img.rotate(-g, expand=True) if g else img


def ajuste_auto(img, alvo_w, alvo_h, modo="rosto", subir_pct=4.0):
    """O ajuste que o programa escolhe sozinho. Devolve (ajuste, achou_rosto)."""
    W, H = img.size
    if modo == "inteira":
        return dict(cx=0.5, cy=0.5, zoom=zoom_minimo(W, H, alvo_w, alvo_h), giro=0), False
    cw, ch = _cobrir(W, H, alvo_w / alvo_h)
    cx, cy = W / 2, H / 2
    rostos = achar_rostos(img) if modo == "rosto" else []
    if rostos:
        x1 = min(x for x, y, w, h in rostos); y1 = min(y for x, y, w, h in rostos)
        x2 = max(x + w for x, y, w, h in rostos); y2 = max(y + h for x, y, w, h in rostos)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        cy -= H * subir_pct / 100.0                   # rosto um pouco acima do meio fica melhor
    left = min(max(0, cx - cw / 2), W - cw)
    top = min(max(0, cy - ch / 2), H - ch)
    return dict(cx=(left + cw / 2) / W, cy=(top + ch / 2) / H, zoom=1.0, giro=0), bool(rostos)


def limpar_ajuste(img, alvo_w, alvo_h, aj):
    """O ajuste dentro do que a foto permite: zoom entre a foto inteira e ZOOM_MAX, e o
    centro onde o recorte não passa da foto (no lado em que ela é maior que a janela)."""
    W, H = img.size
    z = min(ZOOM_MAX, max(zoom_minimo(W, H, alvo_w, alvo_h), _num(aj.get("zoom"), 1.0)))
    bw, bh = _cobrir(W, H, alvo_w / alvo_h)
    cw, ch = bw / z, bh / z

    def prender(c, tam, lim):
        if tam >= lim:                               # recorte maior que a foto: ela fica no meio
            return 0.5
        return min(max(tam / 2, c * lim), lim - tam / 2) / lim

    return dict(cx=prender(_num(aj.get("cx"), 0.5), cw, W), cy=prender(_num(aj.get("cy"), 0.5), ch, H),
                zoom=z, giro=int(_num(aj.get("giro"))) % 360)


def caixa_do_recorte(W, H, alvo_w, alvo_h, aj):
    """(left, top, largura, altura) do recorte em px da foto. Passa da foto quando zoom < 1."""
    bw, bh = _cobrir(W, H, alvo_w / alvo_h)
    cw, ch = bw / aj["zoom"], bh / aj["zoom"]
    return aj["cx"] * W - cw / 2, aj["cy"] * H - ch / 2, cw, ch


def desenhar_janela(img, alvo_w, alvo_h, aj, fundo=(255, 255, 255)):
    """A janela da foto (alvo_w × alvo_h px) com o recorte do ajuste. `img` já girada."""
    aj = limpar_ajuste(img, alvo_w, alvo_h, aj)
    W, H = img.size
    l, t, cw, ch = caixa_do_recorte(W, H, alvo_w, alvo_h, aj)
    k = alvo_w / cw
    saida = Image.new("RGB", (alvo_w, alvo_h), fundo)
    il, it, ir, ib = max(0.0, l), max(0.0, t), min(float(W), l + cw), min(float(H), t + ch)
    if ir - il <= 0 or ib - it <= 0:
        return saida
    dx, dy = int(round((il - l) * k)), int(round((it - t) * k))
    pw = max(1, min(alvo_w - dx, int(round((ir - il) * k))))
    ph = max(1, min(alvo_h - dy, int(round((ib - it) * k))))
    saida.paste(img.resize((pw, ph), Image.LANCZOS, box=(il, it, ir, ib)), (dx, dy))
    return saida


def recortar(img, alvo_w, alvo_h, modo="rosto", subir_pct=4.0):
    """O pedaço da foto que vai na janela da polaroid, na proporção alvo_w:alvo_h.
    'inteira' não corta: devolve a foto inteira e quem cola centraliza com borda."""
    if modo == "inteira":
        return img, False
    aj, achou = ajuste_auto(img, alvo_w, alvo_h, modo, subir_pct)
    l, t, cw, ch = caixa_do_recorte(*img.size, alvo_w, alvo_h, aj)
    return img.crop((round(l), round(t), round(l + cw), round(t + ch))), achou


# ── legenda ───────────────────────────────────────────────────────────────────
_FONTES = {}
RESERVA = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
           "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
           "/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def carregar_fonte(caminho, tamanho_px):
    chave = (caminho, tamanho_px)
    if chave not in _FONTES:
        fonte = None
        for c in ([caminho] if caminho else []) + RESERVA:
            try:
                fonte = ImageFont.truetype(c, max(1, int(tamanho_px)))
                break
            except Exception:
                continue
        _FONTES[chave] = fonte or ImageFont.load_default()
    return _FONTES[chave]


def texto_da_legenda(cfg, caminho):
    leg = cfg["legenda"]
    if leg.get("modo") == "texto":
        return str(leg.get("texto") or "").strip()
    if leg.get("modo") == "nome" and caminho:
        return Path(caminho).stem.replace("_", " ").strip()
    return ""


# ── uma polaroid ──────────────────────────────────────────────────────────────
def montar_polaroid(img, cfg, legenda="", dpi=None, ajuste=None):
    """A polaroid EM PÉ, como imagem RGB no tamanho do CORTE, no dpi pedido.
    `ajuste` = o enquadramento feito à mão (ver ajuste_auto); sem ele, o automático.
    Devolve (imagem, achou_rosto)."""
    cfg = completar(cfg)
    pol = medidas_polaroid(cfg)
    dpi = int(dpi or cfg.get("dpi") or 300)
    ppm = dpi / 25.4
    px = lambda mm: max(1, int(round(mm * ppm)))
    W, H = px(pol["w"]), px(pol["h"])
    moldura = cor_rgb(cfg.get("moldura_cor"), (255, 255, 255))
    folha = Image.new("RGB", (W, H), moldura)

    fx, fy = int(round(pol["lat"] * ppm)), int(round(pol["topo"] * ppm))
    fw, fh = px(pol["foto_w"]), px(pol["foto_h"])
    if ajuste:
        img, achou = girar(img, ajuste.get("giro")), False
    else:
        ajuste, achou = ajuste_auto(img, fw, fh, cfg["foto"].get("enquadrar", "rosto"),
                                    _num(cfg["foto"].get("subir_rosto"), 4.0))
    folha.paste(desenhar_janela(img, fw, fh, ajuste, moldura), (fx, fy))

    d = ImageDraw.Draw(folha)
    if cfg.get("contorno_foto"):
        d.rectangle([fx, fy, fx + fw - 1, fy + fh - 1],
                    outline=cor_rgb(cfg.get("contorno_cor"), (200, 200, 200)),
                    width=max(1, int(round(0.15 * ppm))))

    if legenda and pol["base"] > 0:
        leg = cfg["legenda"]
        topo_base = fy + fh
        alt_base = H - topo_base
        tam_pt = _num(leg.get("tamanho"))
        larg_util = W - 2 * fx
        if tam_pt > 0:
            tam_px = tam_pt / 72.0 * dpi
        else:                                            # automático: cabe na base e na largura
            tam_px = alt_base * 0.36
        fonte = carregar_fonte(leg.get("fonte") or "", tam_px)
        caixa = d.textbbox((0, 0), legenda, font=fonte)
        tw, th = caixa[2] - caixa[0], caixa[3] - caixa[1]
        if tam_pt <= 0 and tw > larg_util and tw > 0:    # automático encolhe pra caber na largura
            tam_px = tam_px * larg_util / tw
            fonte = carregar_fonte(leg.get("fonte") or "", tam_px)
            caixa = d.textbbox((0, 0), legenda, font=fonte)
            tw, th = caixa[2] - caixa[0], caixa[3] - caixa[1]
        al = leg.get("alinhar", "centro")
        if al == "esquerda":
            x = fx
        elif al == "direita":
            x = W - fx - tw
        else:
            x = (W - tw) / 2
        y = topo_base + (alt_base - th) / 2 + _num(leg.get("deslocar")) * ppm
        d.text((x - caixa[0], y - caixa[1]), legenda, font=fonte,
               fill=cor_rgb(leg.get("cor"), (60, 60, 60)))
    return folha, achou


# ── o PDF ─────────────────────────────────────────────────────────────────────
def fila_de_fotos(fotos, cfg):
    """Cada foto repetida pelo número de cópias, na ordem."""
    n = max(1, int(_num(cfg.get("copias"), 1)))
    return [f for f in fotos for _ in range(n)]


def resumo(fotos, cfg):
    lay = layout(cfg)
    total = len(fila_de_fotos(fotos, completar(cfg)))
    paginas = math.ceil(total / lay["por_folha"]) if lay["por_folha"] else 0
    return lay, total, paginas


def _marcas(c, lay, cfg, fh_pt):
    """Marcas de corte pra FORA do bloco, em cada linha de corte (as duas bordas de
    cada coluna e de cada fileira). Com espaço zero, vizinhos dividem a mesma linha."""
    mk = cfg["marcas"]
    comp, afast = _num(mk.get("comprimento"), 3.0), _num(mk.get("afastamento"), 1.0)
    cor = [v / 255 for v in cor_rgb(mk.get("cor"), (0, 0, 0))]
    c.setStrokeColorRGB(*cor)
    c.setLineWidth(max(0.05, _num(mk.get("espessura"), 0.3)))
    cw, ch = lay["celula"]
    gh, gv = lay["espaco"]
    x0, y0 = lay["origem"]
    uw, uh = lay["usado"]
    xs = sorted({round(x0 + i * (cw + gh) + d, 4) for i in range(lay["cols"]) for d in (0, cw)})
    ys = sorted({round(y0 + j * (ch + gv) + d, 4) for j in range(lay["rows"]) for d in (0, ch)})
    s = lay["sangria"]
    fora = afast + s                                     # a marca começa depois da sangria
    Y = lambda mm: fh_pt - mm * MM
    for x in xs:
        c.line(x * MM, Y(y0 - fora), x * MM, Y(y0 - fora - comp))
        c.line(x * MM, Y(y0 + uh + fora), x * MM, Y(y0 + uh + fora + comp))
    for y in ys:
        c.line((x0 - fora) * MM, Y(y), (x0 - fora - comp) * MM, Y(y))
        c.line((x0 + uw + fora) * MM, Y(y), (x0 + uw + fora + comp) * MM, Y(y))
    return len(xs), len(ys)


def gerar_pdf(fotos, cfg, destino, progresso=None, cancelar=None, ajustes=None):
    """Gera o PDF. `progresso(i, total, nome)` é chamado a cada foto.
    `ajustes` = {caminho: ajuste} das fotos enquadradas à mão.
    Devolve um resumo: páginas, polaroids, fotos com rosto, problemas."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    cfg = completar(cfg)
    lay = layout(cfg)
    if not lay["por_folha"]:
        raise ConfigInvalida("nenhuma polaroid cabe nessa folha com essas medidas e margens")
    fila = fila_de_fotos(fotos, cfg)
    if not fila:
        raise ConfigInvalida("nenhuma foto pra gerar")
    fw, fh = lay["folha"]
    fw_pt, fh_pt = fw * MM, fh * MM
    dpi = int(_num(cfg.get("dpi"), 300)) or 300
    qual = int(_num(cfg.get("qualidade"), 92)) or 92
    moldura = [v / 255 for v in cor_rgb(cfg.get("moldura_cor"), (255, 255, 255))]
    cw, ch = lay["celula"]

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(destino), pagesize=(fw_pt, fh_pt))
    c.setTitle(destino.stem)
    c.setAuthor("Gerador de Polaroids — PrintHub Brasil")
    problemas, com_rosto, feitas, paginas = [], 0, 0, 0
    cache = {}                                           # cópias da mesma foto: monta uma vez só
    porf = lay["por_folha"]
    for ini in range(0, len(fila), porf):
        bloco = fila[ini:ini + porf]
        paginas += 1
        for k, caminho in enumerate(bloco):
            if cancelar and cancelar():
                c.save()
                return dict(paginas=paginas, polaroids=feitas, com_rosto=com_rosto,
                            problemas=problemas, cancelado=True, arquivo=destino, layout=lay)
            n_global = ini + k + 1
            if progresso:
                progresso(n_global, len(fila), Path(caminho).name)
            x, y = lay["posicoes"][k]
            yb = fh_pt - (y + ch) * MM                   # PDF conta de baixo pra cima
            se, st, sd, sb = sangria_da_posicao(lay, k)
            if se or st or sd or sb:
                c.setFillColorRGB(*moldura)
                c.rect((x - se) * MM, yb - sb * MM, (cw + se + sd) * MM, (ch + st + sb) * MM,
                       stroke=0, fill=1)
            try:
                if caminho not in cache:
                    img = abrir_foto(caminho)
                    pol, achou = montar_polaroid(img, cfg, texto_da_legenda(cfg, caminho), dpi,
                                                 (ajustes or {}).get(str(caminho)))
                    img.close()
                    if lay["girada"]:
                        pol = pol.transpose(Image.ROTATE_90)
                    buf = io.BytesIO()
                    pol.save(buf, "JPEG", quality=qual, dpi=(dpi, dpi), subsampling=0)
                    pol.close()
                    cache.clear()                        # só a última: cópias vêm em sequência
                    cache[caminho] = (buf.getvalue(), achou)
                dados, achou = cache[caminho]
                com_rosto += 1 if achou else 0
                c.drawImage(ImageReader(io.BytesIO(dados)), x * MM, yb, cw * MM, ch * MM)
                feitas += 1
            except Exception as e:
                problemas.append((Path(caminho).name, str(e)))
            if cfg["marcas"].get("linha_corte"):
                c.setStrokeColorRGB(*[v / 255 for v in cor_rgb(cfg["marcas"].get("cor"), (0, 0, 0))])
                c.setLineWidth(0.25)
                c.rect(x * MM, yb, cw * MM, ch * MM, stroke=1, fill=0)
        if cfg["marcas"].get("ligado"):
            _marcas(c, lay, cfg, fh_pt)
        c.showPage()
    c.save()
    return dict(paginas=paginas, polaroids=feitas, com_rosto=com_rosto, problemas=problemas,
                cancelado=False, arquivo=destino, layout=lay)


def previa(fotos, cfg, largura_px=520, pagina=0, cache=None, abrir=None, ajustes=None):
    """Imagem da página `pagina` em baixa resolução, igual ao PDF (mesma geometria).
    `abrir(caminho)` devolve a foto (a janela passa uma que guarda miniaturas, pra
    não reabrir foto de 12 MP a cada número que a pessoa digita)."""
    cfg = completar(cfg)
    lay = layout(cfg)
    fw, fh = lay["folha"]
    k = largura_px / fw                                  # px por mm
    img = Image.new("RGB", (max(1, int(fw * k)), max(1, int(fh * k))), (255, 255, 255))
    d = ImageDraw.Draw(img)
    cw, ch = lay["celula"]
    moldura = cor_rgb(cfg.get("moldura_cor"), (255, 255, 255))
    fila = fila_de_fotos(fotos, cfg)
    porf = lay["por_folha"] or 1
    bloco = fila[pagina * porf:(pagina + 1) * porf] if fila else []
    dpi_prev = max(20, int(k * 25.4))
    cache = cache if cache is not None else {}
    for i, (x, y) in enumerate(lay["posicoes"]):
        se, st, sd, sb = sangria_da_posicao(lay, i)
        if se or st or sd or sb:
            d.rectangle([(x - se) * k, (y - st) * k, (x + cw + sd) * k, (y + ch + sb) * k], fill=moldura)
        if i < len(bloco):
            chave = (str(bloco[i]), dpi_prev, repr(sorted(cfg["polaroid"].items())),
                     repr(sorted(cfg["foto"].items())), repr(sorted(cfg["legenda"].items())),
                     cfg.get("moldura_cor"), cfg.get("contorno_foto"), cfg.get("contorno_cor"), lay["girada"],
                     repr(sorted((ajustes or {}).get(str(bloco[i]), {}).items())))
            if chave not in cache:
                try:
                    foto = abrir(bloco[i]) if abrir else abrir_foto(bloco[i])
                    if not abrir:
                        foto.thumbnail((1200, 1200))
                    pol, _ = montar_polaroid(foto, cfg, texto_da_legenda(cfg, bloco[i]), dpi_prev,
                                             (ajustes or {}).get(str(bloco[i])))
                    if lay["girada"]:
                        pol = pol.transpose(Image.ROTATE_90)
                    cache[chave] = pol
                except Exception:
                    cache[chave] = None
            pol = cache[chave]
            if pol is not None:
                img.paste(pol.resize((max(1, int(cw * k)), max(1, int(ch * k)))), (int(x * k), int(y * k)))
                continue
        # sem foto: o lugar da polaroid, com a janela da foto marcada
        d.rectangle([x * k, y * k, (x + cw) * k, (y + ch) * k], fill=moldura, outline=(170, 170, 170))
        pol = lay["polaroid"]
        if lay["girada"]:
            jx, jy, jw, jh = pol["topo"], pol["lat"], pol["foto_h"], pol["foto_w"]
        else:
            jx, jy, jw, jh = pol["lat"], pol["topo"], pol["foto_w"], pol["foto_h"]
        d.rectangle([(x + jx) * k, (y + jy) * k, (x + jx + jw) * k, (y + jy + jh) * k], fill=(222, 226, 235))
    # linhas de corte e marcas, pra ver na tela
    vermelho = (224, 27, 36)
    for i, (x, y) in enumerate(lay["posicoes"]):
        d.rectangle([x * k, y * k, (x + cw) * k, (y + ch) * k], outline=vermelho)
    return img, lay
