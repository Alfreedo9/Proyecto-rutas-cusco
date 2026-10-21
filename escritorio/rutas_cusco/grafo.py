"""
grafo.py
--------
Grafo de calles de Cusco (lista de adyacencia) y algoritmo de Dijkstra.

Dijkstra se usa para conocer la distancia REAL por calles entre dos lugares;
todos los demás algoritmos (voraz, divide y vencerás, programación dinámica)
trabajan sobre esas distancias.

Complejidad de Dijkstra con montículo binario (heapq):
    tiempo  O((V + E) log V)
    espacio O(V)
"""
from __future__ import annotations

import heapq
import math

from datos import CALLES_DEF, LUGARES, longitud_calle


class Grafo:
    """Grafo no dirigido y ponderado: adj[u] = [(v, metros, nombre_calle), ...].

    longitudes: opcional, {frozenset({a, b}): metros} con la longitud REAL de
    cada calle medida sobre OpenStreetMap (ver osm.py). Si no se da, se usa la
    estimación Haversine x 1.25 de datos.py.
    """

    def __init__(self, longitudes: dict | None = None) -> None:
        self.adj: dict[str, list[tuple[str, float, str]]] = {n: [] for n in LUGARES}
        self.calles: list[tuple[str, str, float, str]] = []
        self.peso: dict[frozenset, float] = {}
        self.reales = bool(longitudes)
        for a, b, nombre in CALLES_DEF:
            metros = (longitudes or {}).get(frozenset((a, b))) or longitud_calle(a, b)
            self.agregar_calle(a, b, metros, nombre)

    def agregar_calle(self, a: str, b: str, metros: float, nombre: str) -> None:
        self.adj[a].append((b, metros, nombre))
        self.adj[b].append((a, metros, nombre))
        self.calles.append((a, b, metros, nombre))
        self.peso[frozenset((a, b))] = metros

    # ------------------------------------------------------------------
    def dijkstra(self, origen: str, cerradas: set | None = None):
        """Distancias mínimas desde `origen` a todos los lugares.

        cerradas: conjunto de aristas frozenset({a, b}) que no se pueden usar.
        Retorna (dist, previo) para reconstruir los caminos.
        """
        cerradas = cerradas or set()
        dist = {n: math.inf for n in self.adj}
        previo: dict[str, str | None] = {n: None for n in self.adj}
        dist[origen] = 0.0
        heap = [(0.0, origen)]                       # (distancia, nodo)
        while heap:
            d, u = heapq.heappop(heap)               # O(log V)
            if d > dist[u]:                          # entrada vieja, se ignora
                continue
            for v, w, _ in self.adj[u]:              # cada arista se relaja 1 vez
                if frozenset((u, v)) in cerradas:
                    continue
                nd = d + w
                if nd < dist[v]:                     # relajación (decisión voraz)
                    dist[v] = nd
                    previo[v] = u
                    heapq.heappush(heap, (nd, v))
        return dist, previo

    @staticmethod
    def reconstruir(previo: dict, destino: str) -> list[str]:
        """Camino origen → destino a partir del diccionario `previo`."""
        camino = []
        nodo = destino
        while nodo is not None:
            camino.append(nodo)
            nodo = previo[nodo]
        return camino[::-1]

    def camino_minimo(self, a: str, b: str, cerradas: set | None = None) -> tuple[float, list[str]]:
        dist, prev = self.dijkstra(a, cerradas)
        if dist[b] == math.inf:
            return math.inf, []
        return dist[b], self.reconstruir(prev, b)

    # ------------------------------------------------------------------
    def matriz_distancias(self, lugares: list[str], cerradas: set | None = None):
        """Distancias por calle entre todos los pares de `lugares`.

        Ejecuta Dijkstra una vez por lugar distinto: O(k (V+E) log V).
        Retorna (D, caminos) donde D[i][j] es la distancia y
        caminos[(i, j)] la lista de lugares que forman el recorrido.
        Con `cerradas`, las calles cortadas no se usan (D = inf si no hay camino).
        """
        k = len(lugares)
        D = [[0.0] * k for _ in range(k)]
        caminos: dict[tuple[int, int], list[str]] = {}
        cache = {}
        for i, a in enumerate(lugares):
            if a not in cache:
                cache[a] = self.dijkstra(a, cerradas)
            dist, prev = cache[a]
            for j, b in enumerate(lugares):
                D[i][j] = dist[b]
                caminos[(i, j)] = self.reconstruir(prev, b)
        return D, caminos

    def calle_entre(self, a: str, b: str) -> str:
        for v, _, nombre in self.adj[a]:
            if v == b:
                return nombre
        return "?"
