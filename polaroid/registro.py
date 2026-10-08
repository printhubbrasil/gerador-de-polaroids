#!/usr/bin/env python3
"""Onde o programa guarda a configuração e anota o que aconteceu.

Windows: %APPDATA%\\PrintHub\\Gerador de Polaroids · Mac: ~/Library/Application Support/...
Nada aqui pode derrubar o programa: toda gravação é "se der". O erro sai PRIMEIRO
num arquivo, depois no console — a caixa da janela vem por último, porque se o
problema for justamente a janela, o aviso não pode morrer junto.
"""
import datetime
import json
import os
import platform
import sys
import tempfile
import traceback
from pathlib import Path

NOME = "Gerador de Polaroids"


def pasta():
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    for candidata in (base / "PrintHub" / NOME, Path(tempfile.gettempdir()) / "PrintHub-Polaroids"):
        try:
            candidata.mkdir(parents=True, exist_ok=True)
            teste = candidata / ".escrita"
            teste.write_text("ok", encoding="utf-8")
            teste.unlink()
            return candidata
        except OSError:
            continue
    return Path(tempfile.gettempdir())


PASTA = pasta()
ARQ_CONFIG = PASTA / "config.json"
ARQ_PERFIS = PASTA / "perfis.json"
ARQ_LOG = PASTA / "registro.txt"


def anotar(texto):
    linha = f"{datetime.datetime.now():%d/%m %H:%M:%S}  {texto}\n"
    try:
        with open(ARQ_LOG, "a", encoding="utf-8") as f:
            f.write(linha)
    except OSError:
        pass


def iniciar():
    """Reescreve o registro com o diagnóstico da máquina — é o que se pede quando quebra."""
    try:
        ARQ_LOG.write_text(
            f"{NOME} — aberto em {datetime.datetime.now():%d/%m/%Y %H:%M}\n"
            f"Sistema: {platform.platform()}\nPython: {sys.version.split()[0]}\n"
            f"Empacotado: {'sim' if getattr(sys, 'frozen', False) else 'não'}\n\n",
            encoding="utf-8")
    except OSError:
        pass


def tombo(onde, erro):
    """Erro inesperado: arquivo próprio com a pilha inteira (o registro.txt é reescrito
    na próxima abertura, e o erro se perderia justo quando a pessoa tentasse de novo)."""
    pilha = "".join(traceback.format_exception(type(erro), erro, erro.__traceback__))
    try:
        (PASTA / f"erro-{datetime.datetime.now():%Y%m%d-%H%M%S}.txt").write_text(
            f"{onde}\n\n{pilha}", encoding="utf-8")
    except OSError:
        pass
    anotar(f"ERRO em {onde}: {erro}")
    try:
        print(f"[ERRO] {onde}: {erro}", file=sys.stderr)
    except Exception:
        pass


def ler_json(arq, padrao):
    try:
        return json.loads(Path(arq).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def gravar_json(arq, dados):
    try:
        tmp = Path(arq).with_suffix(".tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(arq)
        return True
    except OSError:
        return False
