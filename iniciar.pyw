#!/usr/bin/env python3
"""Abre o Gerador de Polaroids. (.pyw = no Windows abre sem a janela preta do console)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from polaroid import registro
except Exception as e:                       # nem o registro abriu: avisa no console
    print("Não consegui iniciar:", e)
    raise

try:
    from polaroid.app import principal
    principal()
except Exception as e:
    registro.tombo("abrir o programa", e)
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk(); r.withdraw()
        messagebox.showerror("Gerador de Polaroids", f"O programa não abriu:\n\n{e}\n\n"
                             f"O detalhe ficou em:\n{registro.PASTA}")
    except Exception:
        pass
    raise
