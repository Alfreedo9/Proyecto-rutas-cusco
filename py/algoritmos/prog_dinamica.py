"""
prog_dinamica.py
----------------
PROGRAMACIÓN DINÁMICA: se resuelve cada subproblema UNA vez y se guarda su
resultado en una tabla.

1. mochila_01  : carga óptima del vehículo (máximo valor sin exceder el peso).
                 Estado  dp[i][w] = mejor valor usando los primeros i pedidos
                                    con capacidad w.
                 Tiempo O(n·W), espacio O(n·W)  (pseudo-polinomial).
2. held_karp   : ruta ÓPTIMA que visita todos los puntos (TSP, ruta abierta).
                 Estado  dp[S][j] = costo mínimo de salir de `inicio`, visitar
                                    exactamente el conjunto S y terminar en j.
                 Tiempo O(n^2 · 2^n), espacio O(n · 2^n).
                 Exponencial, pero mucho mejor que probar las (n-1)! rutas.
"""
from __future__ import annotations

import math


# ------------------------------------------------------------------ mochila 0/1
def mochila_01(pedidos: list, capacidad: int):
    """Mochila 0/1 con reconstrucción de la solución.

    Recurrencia:
        dp[i][w] = dp[i-1][w]                                   si peso_i > w
        dp[i][w] = max(dp[i-1][w], dp[i-1][w-peso_i] + valor_i)  en otro caso
    Casos base: dp[0][w] = 0.
    Retorna (seleccionados, valor_total, peso_total, tabla_dp).
    """
    n = len(pedidos)
    W = capacidad
    dp = [[0] * (W + 1) for _ in range(n + 1)]            # (n+1) x (W+1)
    for i in range(1, n + 1):                              # n filas
        p, v = pedidos[i - 1].peso, pedidos[i - 1].valor
        fila, previa = dp[i], dp[i - 1]
        for w in range(W + 1):                             # W+1 columnas
            fila[w] = previa[w]                            # no tomar el pedido i
            if p <= w and previa[w - p] + v > fila[w]:
                fila[w] = previa[w - p] + v                # tomar el pedido i

    # Reconstrucción: se recorre la tabla de abajo hacia arriba. O(n)
    seleccion, w = [], W
    for i in range(n, 0, -1):
        if dp[i][w] != dp[i - 1][w]:                       # el pedido i fue tomado
            seleccion.append(pedidos[i - 1])
            w -= pedidos[i - 1].peso
    seleccion.reverse()
    peso_total = sum(p.peso for p in seleccion)
    return seleccion, dp[n][W], peso_total, dp


# ------------------------------------------------------------------ Held-Karp
def held_karp(D: list[list[float]], inicio: int = 0, regresar: bool = False):
    """Ruta óptima que sale de `inicio` y visita todos los demás puntos.

    D: matriz de distancias (n x n). Los conjuntos S se representan con máscaras
    de bits sobre los n-1 puntos distintos de `inicio`.
    Retorna (orden_de_indices, costo_minimo).
    """
    n = len(D)
    if n == 1:
        return [inicio], 0.0
    otros = [i for i in range(n) if i != inicio]
    m = len(otros)
    TOTAL = 1 << m
    INF = math.inf
    # dp[mask][j]: costo mínimo visitando el conjunto `mask` y terminando en otros[j]
    dp = [[INF] * m for _ in range(TOTAL)]
    padre = [[-1] * m for _ in range(TOTAL)]
    for j in range(m):                                     # casos base
        dp[1 << j][j] = D[inicio][otros[j]]

    for mask in range(1, TOTAL):                           # 2^m conjuntos
        for j in range(m):                                 # m posibles finales
            if not (mask >> j) & 1 or dp[mask][j] == INF:
                continue
            base = dp[mask][j]
            for k in range(m):                             # m posibles siguientes
                if (mask >> k) & 1:
                    continue
                nmask = mask | (1 << k)
                c = base + D[otros[j]][otros[k]]
                if c < dp[nmask][k]:                       # se guarda el mejor
                    dp[nmask][k] = c
                    padre[nmask][k] = j

    lleno = TOTAL - 1
    extra = (lambda j: D[otros[j]][inicio]) if regresar else (lambda j: 0.0)
    fin = min(range(m), key=lambda j: dp[lleno][j] + extra(j))
    costo = dp[lleno][fin] + extra(fin)

    # Reconstrucción de la ruta siguiendo los padres
    orden, mask, j = [], lleno, fin
    while j != -1:
        orden.append(otros[j])
        pj = padre[mask][j]
        mask ^= 1 << j
        j = pj
    orden.append(inicio)
    orden.reverse()
    if regresar:
        orden.append(inicio)
    return orden, costo
