#!/usr/bin/env python3
"""Bateria do Gerador de Polaroids — mede o PDF gerado, não confia na conta.

Roda com:  python3 testes/rodar.py
Os arquivos de teste nascem no temporário do sistema, nunca na pasta do programa.
"""
import sys
import tempfile
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
from PIL import Image, ImageDraw

from polaroid import motor as M

TMP = Path(tempfile.mkdtemp(prefix="polaroid_teste_"))
ok = falhas = 0


def conferir(nome, cond, extra=""):
    global ok, falhas
    if cond:
        ok += 1
        print(f"  ✓ {nome}")
    else:
        falhas += 1
        print(f"  ✗ {nome}  →  {extra}")


def perto(a, b, tol=0.06):
    return abs(a - b) <= tol


def foto(nome, cor, w=1200, h=900):
    """Foto sintética: fundo de uma cor e um quadrado branco no meio (pra achar o centro)."""
    img = Image.new("RGB", (w, h), cor)
    d = ImageDraw.Draw(img)
    d.rectangle([w * 0.45, h * 0.45, w * 0.55, h * 0.55], fill=(255, 255, 255))
    p = TMP / nome
    img.save(p, quality=95)
    return p


FOTOS = [foto(f"foto{i}.jpg", c) for i, c in enumerate(
    [(200, 30, 30), (30, 150, 60), (30, 60, 200), (220, 160, 20), (120, 40, 160)], start=1)]
foto("foto10.jpg", (10, 10, 10))


def gerar(cfg, nome="t.pdf", fotos=None):
    destino = TMP / nome
    info = M.gerar_pdf(fotos or FOTOS, cfg, destino)
    return fitz.open(str(destino)), info


def mm(v):
    return v / M.MM


print("\n1 · os modelos do programa antigo continuam iguais")
lay = M.layout({"margem": {"topo": 0, "base": 0, "esq": 0, "dir": 0}, "espaco": {"h": 0, "v": 0},
                "centralizar": False, "giro": "em_pe"})
conferir("Clássica na A4 sem margem: 2 × 2 (igual ao antigo)", (lay["cols"], lay["rows"]) == (2, 2), (lay["cols"], lay["rows"]))
pol = M.medidas_polaroid(M.completar({}))
conferir("  foto 79 × 79 e base de 23,5 mm", (pol["foto_w"], pol["foto_h"], pol["base"]) == (79.0, 79.0, 23.5), pol)
lay = M.layout({"polaroid": {"modelo": "Mini (5 × 7 cm)", **M.POLAROIDS["Mini (5 × 7 cm)"]},
                "margem": {"topo": 0, "base": 0, "esq": 0, "dir": 0}, "espaco": {"h": 0, "v": 0},
                "centralizar": False, "giro": "em_pe"})
conferir("Mini na A4 sem margem: 4 × 4 (igual ao antigo)", (lay["cols"], lay["rows"]) == (4, 4), (lay["cols"], lay["rows"]))

print("\n2 · folha, posições e tamanho de cada polaroid no PDF")
cfg = {"folha": {"modelo": "33 × 48 cm", "w": 330, "h": 480, "paisagem": False},
       "margem": {"topo": 10, "base": 10, "esq": 8, "dir": 8}, "espaco": {"h": 3, "v": 4},
       "giro": "em_pe", "marcas": {"ligado": False}}
doc, info = gerar(cfg)
pg = doc[0]
conferir("folha 330 × 480 mm", perto(mm(pg.rect.width), 330) and perto(mm(pg.rect.height), 480),
         (mm(pg.rect.width), mm(pg.rect.height)))
lay = info["layout"]
imgs = sorted(pg.get_image_info(), key=lambda i: (round(i["bbox"][1]), i["bbox"][0]))
conferir(f"{len(FOTOS)} polaroids na página", len(imgs) == len(FOTOS), len(imgs))
certas = all(perto(mm(i["bbox"][0]), x) and perto(mm(i["bbox"][1]), y)
             and perto(mm(i["bbox"][2] - i["bbox"][0]), 88) and perto(mm(i["bbox"][3] - i["bbox"][1]), 107)
             for i, (x, y) in zip(imgs, lay["posicoes"]))
conferir("  cada uma no lugar e com 88 × 107 mm", certas, [(round(mm(i["bbox"][0]), 2), round(mm(i["bbox"][1]), 2)) for i in imgs[:3]])
x1 = mm(imgs[1]["bbox"][0]) - mm(imgs[0]["bbox"][2])
conferir("  espaço entre colunas = 3 mm", perto(x1, 3), x1)
conferir("  grade centralizada (sobra igual dos dois lados)",
         perto(lay["margem_real"][0], lay["margem_real"][2]), lay["margem_real"])
conferir("  a imagem tem a resolução pedida (300 dpi)",
         abs(imgs[0]["width"] - round(88 / 25.4 * 300)) <= 1, (imgs[0]["width"], round(88 / 25.4 * 300)))
doc.close()

print("\n3 · janela da foto, moldura e legenda (medindo os pixels)")
cfg = {"giro": "em_pe", "marcas": {"ligado": False}, "moldura_cor": "#FFFFFF", "contorno_foto": False,
       "legenda": {"modo": "texto", "texto": "Feliz Aniversário Maria", "cor": "#000000"},
       "foto": {"enquadrar": "centro"}}
doc, info = gerar(cfg, "janela.pdf", FOTOS[:1])
lay = info["layout"]; x, y = lay["posicoes"][0]
pix = doc[0].get_pixmap(dpi=150)
k = 150 / 25.4
cor = lambda mx, my: pix.pixel(int(mx * k), int(my * k))[:3]
c_foto = cor(x + 4.5 + 10, y + 4.5 + 10)
c_borda = cor(x + 2, y + 50)
conferir("dentro da janela da foto: a foto (vermelha)", c_foto[0] > 150 and c_foto[1] < 90, c_foto)
conferir("na borda lateral: moldura branca", min(c_borda) > 240, c_borda)
escuros = sum(1 for mx in range(int((x + 10) * 10), int((x + 78) * 10), 5)
              for my in range(int((y + 4.5 + 79 + 4) * 10), int((y + 107 - 4) * 10), 5)
              if max(cor(mx / 10, my / 10)) < 100)
conferir("a legenda aparece na base", escuros > 20, escuros)
doc.close()

print("\n4 · sangria")
cfg = {"giro": "em_pe", "marcas": {"ligado": False}, "sangria": 2.0, "moldura_cor": "#FFE0F0",
       "espaco": {"h": 3, "v": 0}, "margem": {"topo": 10, "base": 10, "esq": 10, "dir": 10}}
doc, info = gerar(cfg, "sangria.pdf", FOTOS[:4])
lay = info["layout"]
fundos = [d["rect"] for d in doc[0].get_drawings() if d.get("fill") and abs(d["fill"][1] - 0xE0 / 255) < 0.01]
conferir("um fundo de sangria por polaroid", len(fundos) == 4, len(fundos))
r0 = sorted(fundos, key=lambda r: (round(r.y0), r.x0))[0]
x, y = lay["posicoes"][0]
conferir("  pra fora do bloco passa 2 mm do corte", perto(mm(r0.x0), x - 2) and perto(mm(r0.y0), y - 2),
         (mm(r0.x0), x - 2, mm(r0.y0), y - 2))
conferir("  entre vizinhos (espaço 3) passa só 1,5 mm", perto(mm(r0.x1), x + 88 + 1.5), (mm(r0.x1), x + 88 + 1.5))
conferir("  espaço zero na vertical: sangria zero entre fileiras", perto(mm(r0.y1), y + 107), (mm(r0.y1), y + 107))
doc.close()

print("\n5 · marcas de corte")
cfg = {"giro": "em_pe", "marcas": {"ligado": True, "comprimento": 4, "afastamento": 1.5},
       "margem": {"topo": 12, "base": 12, "esq": 12, "dir": 12}, "espaco": {"h": 4, "v": 4}}
doc, info = gerar(cfg, "marcas.pdf", FOTOS[:4])
lay = info["layout"]
linhas = [d for d in doc[0].get_drawings() if d.get("items") and d["items"][0][0] == "l"]
segs = [it for d in linhas for it in d["items"]]
x0, y0 = lay["origem"]; uw, uh = lay["usado"]
dentro = [s for s in segs if x0 - 0.01 < mm(s[1].x) < x0 + uw + 0.01 and y0 - 0.01 < mm(s[1].y) < y0 + uh + 0.01
          and x0 - 0.01 < mm(s[2].x) < x0 + uw + 0.01 and y0 - 0.01 < mm(s[2].y) < y0 + uh + 0.01]
esperadas = 2 * (2 * lay["cols"]) + 2 * (2 * lay["rows"])
conferir(f"{esperadas} marcas (as duas bordas de cada coluna e fileira, dos dois lados)", len(segs) == esperadas, len(segs))
conferir("  nenhuma marca em cima das polaroids", not dentro, len(dentro))
topo = [s for s in segs if perto(s[1].x, s[2].x, 0.01) and mm(min(s[1].y, s[2].y)) < y0]
conferir("  a marca de cima começa 1,5 mm antes do corte e tem 4 mm",
         topo and perto(y0 - mm(max(topo[0][1].y, topo[0][2].y)), 1.5) and perto(abs(mm(topo[0][1].y - topo[0][2].y)), 4),
         topo[:1])
doc.close()

print("\n6 · giro automático, cópias, foto inteira")
cfg = {"polaroid": {"modelo": "Instax Wide (10,8 × 8,6 cm)", **M.POLAROIDS["Instax Wide (10,8 × 8,6 cm)"]},
       "giro": "auto", "margem": {"topo": 5, "base": 5, "esq": 5, "dir": 5}, "espaco": {"h": 2, "v": 2}}
lay = M.layout(cfg)
em_pe = M.layout({**cfg, "giro": "em_pe"})
conferir("automático gira quando cabe mais", lay["por_folha"] >= em_pe["por_folha"] and
         (lay["girada"] == (lay["por_folha"] > em_pe["por_folha"])), (lay["por_folha"], em_pe["por_folha"], lay["girada"]))
doc, info = gerar({**cfg, "giro": "deitada", "marcas": {"ligado": False}}, "giro.pdf", FOTOS[:1])
i = doc[0].get_image_info()[0]
conferir("  deitada: a caixa no PDF tem 86 × 108", perto(mm(i["bbox"][2] - i["bbox"][0]), 86) and
         perto(mm(i["bbox"][3] - i["bbox"][1]), 108), (mm(i["bbox"][2] - i["bbox"][0]), mm(i["bbox"][3] - i["bbox"][1])))
doc.close()
doc, info = gerar({"copias": 2, "giro": "em_pe"}, "copias.pdf", FOTOS[:3])
conferir("3 fotos × 2 cópias = 6 polaroids", info["polaroids"] == 6, info["polaroids"])
conferir("  em 2 páginas (4 por folha A4)", info["paginas"] == 2 and len(doc) == 2, (info["paginas"], len(doc)))
doc.close()
alta = foto("alta.jpg", (30, 30, 200), 600, 1800)
p, _ = M.montar_polaroid(M.abrir_foto(alta), M.completar({"foto": {"enquadrar": "inteira"}, "contorno_foto": False}), "", 100)
ppm = 100 / 25.4
canto = p.getpixel((int((4.5 + 2) * ppm), int((4.5 + 2) * ppm)))
meio = p.getpixel((int((4.5 + 39.5) * ppm), int((4.5 + 39.5) * ppm)))
conferir("foto inteira: não corta (sobra moldura do lado da foto alta)", min(canto) > 240 and meio[2] > 150, (canto, meio))

print("\n7 · ordem, validação e perfis antigos")
nomes = [q.name for q in M.listar_fotos(TMP) if q.name.startswith("foto")]
conferir("ordem natural: foto2 antes de foto10", nomes.index("foto2.jpg") < nomes.index("foto10.jpg"), nomes)
for desc, c in (("foto maior que a polaroid", {"polaroid": {"foto_h": 120}}),
                ("bordas comendo a largura", {"polaroid": {"lat": 50}}),
                ("margem maior que a folha", {"margem": {"esq": 150, "dir": 150}})):
    try:
        M.layout(c); conferir(f"recusa: {desc}", False, "não recusou")
    except M.ConfigInvalida as e:
        conferir(f"recusa: {desc}", True)
try:
    M.gerar_pdf(FOTOS, {"polaroid": {"w": 400, "h": 500, "foto_h": 300}}, TMP / "x.pdf")
    conferir("polaroid maior que a folha avisa", False, "não avisou")
except M.ConfigInvalida:
    conferir("polaroid maior que a folha avisa", True)
velho = M.completar({"folha": {"w": 210, "h": 297}})
conferir("perfil antigo (faltando chaves) abre com o padrão", velho["marcas"]["comprimento"] == 3.0 and velho["sangria"] == 0)
info = M.gerar_pdf(FOTOS[:2] + [TMP / "nao_existe.jpg"], {"giro": "em_pe"}, TMP / "falta.pdf")
conferir("foto que sumiu vira problema anotado, não derruba", info["polaroids"] == 2 and len(info["problemas"]) == 1, info["problemas"])
parar = iter([False, False, True])
info = M.gerar_pdf(FOTOS, {"giro": "em_pe"}, TMP / "cancel.pdf", cancelar=lambda: next(parar, True))
conferir("cancelar para no meio e fecha o PDF", info["cancelado"] and fitz.open(str(TMP / "cancel.pdf")).page_count >= 1)

print("\n8 · rosto e prévia")
conferir("detector de rosto disponível (OpenCV)", M.tem_detector_de_rosto(), "sem OpenCV: cai pro centro")
img, achou = M.recortar(M.abrir_foto(FOTOS[0]), 79, 79, "rosto")
conferir("sem rosto na foto: recorta pelo centro, quadrado", abs(img.width - img.height) <= 1 and not achou, img.size)
# rosto FORA do centro (uma arte real com pessoa, se estiver na máquina): o recorte
# pelo rosto tem que conter o rosto; o recorte pelo centro, não
REAL = Path.home() / "Desktop" / "Pastas 80 Artes" / "frente-sozinha" / "Eng. Mecânica 4.jpg"
if REAL.exists() and M.tem_detector_de_rosto():
    import shutil
    copia = TMP / "rosto.jpg"; shutil.copy(REAL, copia)
    im = M.abrir_foto(copia)
    rostos = M.achar_rostos(im)
    if rostos:
        rx, ry, rw, rh = rostos[0]; cx = rx + rw / 2
        W = im.width; cw = im.height * 46 / 62            # janela em pé de Instax Mini
        def contem(left):
            return left <= cx <= left + cw
        left_rosto = min(max(0, cx - cw / 2), W - cw)
        rec, achou = M.recortar(im, 46, 62, "rosto")
        conferir("foto real: achou o rosto e o recorte contém ele", achou and contem(left_rosto), (rostos[0], left_rosto))
        # o rosto está perto da borda direita: o recorte vai até onde dá (encosta nela)
        esperado = im.crop((round(left_rosto), 0, round(left_rosto + cw), im.height))
        igual = rec.size == esperado.size and list(rec.resize((40, 40)).getdata()) == list(esperado.resize((40, 40)).getdata())
        dist_rosto = abs((left_rosto + cw / 2) - cx); dist_centro = abs(W / 2 - cx)
        conferir("  o recorte foi pro lado do rosto (o mais perto que a foto deixa)",
                 igual and dist_rosto < dist_centro, (round(left_rosto), round(dist_rosto), round(dist_centro)))
    else:
        conferir("foto real: achou o rosto", False, "não achou")
else:
    print("  (pulado: sem a foto real ou sem OpenCV)")
prev, lay = M.previa(FOTOS, {"giro": "em_pe"}, 400)
conferir("prévia tem a proporção da folha", abs(prev.width / prev.height - 210 / 297) < 0.01, prev.size)

print(f"\n{'═' * 70}\n{ok}/{ok + falhas} passaram" + ("  — tudo certo" if not falhas else ""))
sys.exit(1 if falhas else 0)
