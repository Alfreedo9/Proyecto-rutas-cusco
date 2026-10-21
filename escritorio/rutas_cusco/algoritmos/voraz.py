"""
voraz.py
--------
Enfoque VORAZ (Greedy): en cada paso se toma la mejor decisión local y nunca se
revisa. Es rápido, pero no garantiza el óptimo global.

1. asignar_mas_cercano : cada pedido (de más urgente a menos urgente) se asigna al
                         repartidor más cercano que todavía tenga capacidad.
                         Tiempo O(m (V+E) log V + n log n + n·m), espacio O(m·V).
2. ruta_vecino_mas_cercano : el repartidor siempre va al punto pendiente más
                         próximo a su posición actual. Tiempo O(n^2), espacio O(n).
3. mochila_voraz       : carga pedidos por mayor razón valor/peso (para comparar
                         con la mochila 0/1 de programación dinámica). O(n log n).
"""
from __future__ import annotations

import math

from algoritmos.ordenacion import merge_sort


# ------------------------------------------------------------------ 1. asignación
def asignar_mas_cercano(pedidos: list, repartidores: list, grafo) -> dict:
    """Asigna pedidos a repartidores con el criterio "el más cercano".

    Retorna {id_repartidor: [pedidos]} y un registro de decisiones (para la GUI).
    El repartidor no se mueve: la distancia se mide desde su ubicación actual.
    """
    for r in repartidores:
        r.carga, r.pedidos = 0, []
    # Distancias desde cada repartidor: m ejecuciones de Dijkstra
    dist = {r.id: grafo.dijkstra(r.ubicacion)[0] for r in repartidores}

    asignacion = {r.id: [] for r in repartidores}
    registro = []
    sin_asignar = []
    # Los urgentes primero (merge sort, O(n log n))
    for p in merge_sort(pedidos, clave=lambda x: (-x.prioridad, x.id)):
        mejor, mejor_d = None, math.inf
        for r in repartidores:                         # O(m) por pedido
            d = dist[r.id][p.lugar]
            if r.libre() >= p.peso and d < mejor_d:     # decisión local
                mejor, mejor_d = r, d
        if mejor is None:
            sin_asignar.append(p)
            registro.append(f"{p.id}: ningún repartidor tiene capacidad ({p.peso} kg)")
            continue
        mejor.carga += p.peso
        mejor.pedidos.append(p.id)
        asignacion[mejor.id].append(p)
        registro.append(f"{p.id} (prio {p.prioridad}) → {mejor.id} a {mejor_d:,.0f} m")
    return {"asignacion": asignacion, "sin_asignar": sin_asignar, "registro": registro}


# ------------------------------------------------------------------ 2. ruta
def ruta_vecino_mas_cercano(D: list[list[float]], inicio: int = 0):
    """Heurística del vecino más cercano sobre la matriz de distancias D.

    Parte de `inicio` y en cada paso visita el punto no visitado más cercano.
    Retorna (orden_de_indices, costo_total). Ruta abierta (no regresa).
    """
    n = len(D)
    visitado = [False] * n
    visitado[inicio] = True
    orden, actual, costo = [inicio], inicio, 0.0
    for _ in range(n - 1):                             # n-1 pasos
        siguiente, d_min = -1, math.inf
        for j in range(n):                             # O(n) por paso
            if not visitado[j] and D[actual][j] < d_min:
                siguiente, d_min = j, D[actual][j]
        visitado[siguiente] = True
        orden.append(siguiente)
        costo += d_min
        actual = siguiente
    return orden, costo


# ------------------------------------------------------------------ 3. mochila voraz
def mochila_voraz(pedidos: list, capacidad: int):
    """Toma pedidos completos por mayor valor/peso mientras quepan.

    NO es óptima para la mochila 0/1 (sí lo sería para la fraccionaria).
    Retorna (seleccionados, valor_total, peso_total).
    """
    ordenados = merge_sort(pedidos, clave=lambda p: -p.valor / p.peso)
    sel, valor, peso = [], 0, 0
    for p in ordenados:
        if peso + p.peso <= capacidad:
            sel.append(p)
            peso += p.peso
            valor += p.valor
    return sel, valor, peso
