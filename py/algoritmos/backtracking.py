"""
backtracking.py
---------------
BACKTRACKING (búsqueda exhaustiva con retroceso).

1. todas_las_rutas : enumera TODOS los caminos simples (sin repetir lugares)
                     entre un origen y un destino evitando las calles cerradas,
                     y al final elige el más corto.
                     Peor caso O(V!) caminos; espacio O(V) (profundidad).
2. ruta_mas_corta_poda : igual, pero con PODA (ramificación y acotamiento):
                     si el camino parcial ya es más largo que la mejor ruta
                     encontrada, se abandona esa rama.
3. tsp_backtracking : ruta exacta que visita todos los puntos (para comparar con
                     el voraz y con Held-Karp). O(n!) en el peor caso.

Esquema de backtracking: elegir → verificar → avanzar → retroceder.
"""
from __future__ import annotations

import math


def _arista(a: str, b: str) -> frozenset:
    return frozenset((a, b))


# ------------------------------------------------------------------ 1. todas las rutas
def todas_las_rutas(grafo, origen: str, destino: str, cerradas: set | None = None,
                    max_rutas: int = 200_000) -> dict:
    """Enumera todos los caminos simples origen→destino.

    Retorna {"rutas": [(dist, camino), ...] ordenadas, "mejor": (dist, camino) | None,
             "nodos": nodos del árbol de búsqueda visitados, "truncado": bool}.
    """
    cerradas = cerradas or set()
    rutas: list[tuple[float, list[str]]] = []
    camino = [origen]
    visitado = {origen}
    nodos = 0
    truncado = False

    def bt(actual: str, dist: float) -> None:
        nonlocal nodos, truncado
        nodos += 1
        if len(rutas) >= max_rutas:
            truncado = True
            return
        if actual == destino:                          # solución completa
            rutas.append((dist, camino[:]))
            return
        for vecino, w, _ in grafo.adj[actual]:         # elegir
            if vecino in visitado or _arista(actual, vecino) in cerradas:
                continue                               # verificar (poda por restricción)
            visitado.add(vecino); camino.append(vecino)   # avanzar
            bt(vecino, dist + w)
            camino.pop(); visitado.remove(vecino)         # retroceder

    bt(origen, 0.0)
    # Selección final: la más corta (se ordenan con merge sort propio)
    from algoritmos.ordenacion import merge_sort
    rutas = merge_sort(rutas, clave=lambda r: r[0])
    return {"rutas": rutas, "mejor": rutas[0] if rutas else None,
            "nodos": nodos, "truncado": truncado}


# ------------------------------------------------------------------ 2. con poda
def ruta_mas_corta_poda(grafo, origen: str, destino: str, cerradas: set | None = None) -> dict:
    """Backtracking con poda: solo busca la mejor ruta, no todas."""
    cerradas = cerradas or set()
    mejor = [math.inf, None]
    camino = [origen]
    visitado = {origen}
    nodos = 0

    def bt(actual: str, dist: float) -> None:
        nonlocal nodos
        nodos += 1
        if dist >= mejor[0]:                           # PODA: ya no puede mejorar
            return
        if actual == destino:
            mejor[0], mejor[1] = dist, camino[:]
            return
        # Heurística de orden: probar primero las calles más cortas
        for vecino, w, _ in sorted(grafo.adj[actual], key=lambda t: t[1]):
            if vecino in visitado or _arista(actual, vecino) in cerradas:
                continue
            visitado.add(vecino); camino.append(vecino)
            bt(vecino, dist + w)
            camino.pop(); visitado.remove(vecino)

    bt(origen, 0.0)
    return {"mejor": (mejor[0], mejor[1]) if mejor[1] else None, "nodos": nodos}


# ------------------------------------------------------------------ 3. TSP exacto
def tsp_backtracking(D: list[list[float]], inicio: int = 0):
    """Ruta abierta óptima que visita todos los puntos, por backtracking con poda."""
    n = len(D)
    mejor = [math.inf, None]
    orden = [inicio]
    usado = [False] * n
    usado[inicio] = True

    def bt(actual: int, costo: float) -> None:
        if costo >= mejor[0]:                          # poda
            return
        if len(orden) == n:
            mejor[0], mejor[1] = costo, orden[:]
            return
        for j in range(n):
            if not usado[j]:
                usado[j] = True; orden.append(j)
                bt(j, costo + D[actual][j])
                orden.pop(); usado[j] = False

    bt(inicio, 0.0)
    return mejor[1], mejor[0]
