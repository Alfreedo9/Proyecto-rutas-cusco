"""
ordenacion.py
-------------
Algoritmos de ordenación implementados desde cero (sin usar sorted()).

* merge_sort : Divide y vencerás, ESTABLE.  Tiempo O(n log n) en todos los casos,
               espacio O(n).
* quick_sort : Divide y vencerás con pivote aleatorio. Tiempo O(n log n) en promedio,
               O(n^2) en el peor caso (muy improbable con pivote aleatorio),
               espacio O(log n) promedio (pila de recursión).

Las funciones reciben una función `clave(pedido)` que devuelve el valor (o la
tupla de valores) por el cual se ordena.
"""
from __future__ import annotations

import random
from typing import Callable

# --------------------------------------------------------------- criterios
CRITERIOS: dict[str, Callable] = {
    # Más urgentes primero; si empatan, el más cercano primero.
    "Prioridad (urgente primero)": lambda p: (-p.prioridad, p.distancia),
    "Distancia (más cercano primero)": lambda p: (p.distancia, -p.prioridad),
    "Valor (mayor primero)": lambda p: (-p.valor, p.id),
    "Peso (menor primero)": lambda p: (p.peso, p.id),
    "ID": lambda p: p.id,
}


# --------------------------------------------------------------- merge sort
def merge_sort(lista: list, clave: Callable = lambda x: x) -> list:
    """Devuelve una NUEVA lista ordenada (la original no se modifica).

    T(n) = 2 T(n/2) + O(n)  =>  O(n log n)   (Teorema maestro, caso 2)
    """
    if len(lista) <= 1:                      # caso base
        return lista[:]
    medio = len(lista) // 2
    izq = merge_sort(lista[:medio], clave)   # dividir
    der = merge_sort(lista[medio:], clave)
    return _mezclar(izq, der, clave)         # combinar


def _mezclar(a: list, b: list, clave: Callable) -> list:
    """Mezcla dos listas ordenadas en O(len(a) + len(b))."""
    res, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        if clave(a[i]) <= clave(b[j]):       # <= mantiene la estabilidad
            res.append(a[i]); i += 1
        else:
            res.append(b[j]); j += 1
    res.extend(a[i:])
    res.extend(b[j:])
    return res


# --------------------------------------------------------------- quick sort
def quick_sort(lista: list, clave: Callable = lambda x: x) -> list:
    """Devuelve una NUEVA lista ordenada usando Quicksort in-place sobre una copia."""
    arr = lista[:]
    _quick(arr, 0, len(arr) - 1, clave)
    return arr


def _quick(arr: list, lo: int, hi: int, clave: Callable) -> None:
    while lo < hi:
        p = _particion(arr, lo, hi, clave)
        # Recursión sobre la parte más pequeña => pila O(log n)
        if p - lo < hi - p:
            _quick(arr, lo, p - 1, clave)
            lo = p + 1
        else:
            _quick(arr, p + 1, hi, clave)
            hi = p - 1


def _particion(arr: list, lo: int, hi: int, clave: Callable) -> int:
    """Partición de Lomuto con pivote aleatorio. O(hi - lo)."""
    k = random.randint(lo, hi)
    arr[k], arr[hi] = arr[hi], arr[k]
    pivote = clave(arr[hi])
    i = lo
    for j in range(lo, hi):
        if clave(arr[j]) < pivote:
            arr[i], arr[j] = arr[j], arr[i]
            i += 1
    arr[i], arr[hi] = arr[hi], arr[i]
    return i


ALGORITMOS = {"Merge Sort": merge_sort, "Quick Sort": quick_sort}
