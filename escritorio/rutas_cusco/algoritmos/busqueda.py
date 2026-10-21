"""
busqueda.py
-----------
Búsqueda rápida de pedidos.

* busqueda_secuencial : O(n). Sirve como referencia.
* busqueda_binaria    : O(log n). Requiere la lista ordenada por ID.
* IndiceSector        : tabla hash (diccionario) sector -> pedidos.
                        Construcción O(n), consulta O(1) promedio + O(k)
                        para devolver los k pedidos del sector.
"""
from __future__ import annotations

from algoritmos.ordenacion import merge_sort


def busqueda_secuencial(pedidos: list, id_buscado: str):
    """Recorre la lista hasta encontrar el ID. Retorna (pedido|None, comparaciones)."""
    comparaciones = 0
    for p in pedidos:
        comparaciones += 1
        if p.id == id_buscado:
            return p, comparaciones
    return None, comparaciones


def busqueda_binaria(ordenados_por_id: list, id_buscado: str):
    """Búsqueda binaria iterativa. Retorna (pedido|None, comparaciones).

    En cada paso se descarta la mitad del intervalo:
    T(n) = T(n/2) + O(1)  =>  O(log n).
    """
    lo, hi = 0, len(ordenados_por_id) - 1
    comparaciones = 0
    while lo <= hi:
        medio = (lo + hi) // 2
        comparaciones += 1
        actual = ordenados_por_id[medio].id
        if actual == id_buscado:
            return ordenados_por_id[medio], comparaciones
        if actual < id_buscado:
            lo = medio + 1
        else:
            hi = medio - 1
    return None, comparaciones


class IndiceSector:
    """Índice invertido: sector -> lista de pedidos (tabla hash)."""

    def __init__(self, pedidos: list):
        self.tabla: dict[str, list] = {}
        for p in pedidos:                           # O(n)
            self.tabla.setdefault(p.sector, []).append(p)

    def buscar(self, sector: str) -> list:
        return self.tabla.get(sector, [])           # O(1) promedio


def preparar_busqueda(pedidos: list) -> list:
    """Ordena por ID (merge sort) para poder usar búsqueda binaria."""
    return merge_sort(pedidos, clave=lambda p: p.id)
