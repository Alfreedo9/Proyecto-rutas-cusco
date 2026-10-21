"""
Sistema de Gestión de Rutas Óptimas en Cusco
Programación III — UNSAAC

Ejecutar:   python main.py
Requisitos: Python 3.10+ (solo biblioteca estándar: tkinter, heapq, dataclasses).
"""
import os
import sys

# Permite ejecutar desde cualquier carpeta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import main  # noqa: E402

if __name__ == "__main__":
    main()
