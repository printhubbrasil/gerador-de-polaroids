#!/usr/bin/env python3
"""As fontes instaladas no computador, pra escolher a da legenda.

Windows: as pastas de fontes do sistema e a do usuário (fonte instalada "só pra
mim" mora em %LOCALAPPDATA% e o programa antigo não via). Mac e Linux: as pastas
de sempre. O nome mostrado é o da FONTE ("Arial Negrito"), não o do arquivo.
"""
import os
import sys
from pathlib import Path

EXT = {".ttf", ".otf", ".ttc"}


def _pastas():
    if sys.platform.startswith("win"):
        win = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"
        return [win, local]
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
                Path("/Library/Fonts"), Path.home() / "Library" / "Fonts"]
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
            Path.home() / ".local" / "share" / "fonts"]


def listar():
    """{nome bonito: caminho}, em ordem alfabética. Arquivo ilegível é pulado."""
    from PIL import ImageFont
    achadas = {}
    for pasta in _pastas():
        if not pasta.is_dir():
            continue
        for arq in pasta.rglob("*"):
            if arq.suffix.lower() not in EXT:
                continue
            try:
                familia, estilo = ImageFont.truetype(str(arq), 12).getname()
            except Exception:
                continue
            nome = familia if estilo in ("Regular", "Normal", "Book", "Roman", "") else f"{familia} {estilo}"
            achadas.setdefault(nome, str(arq))
    return dict(sorted(achadas.items(), key=lambda kv: kv[0].lower()))
