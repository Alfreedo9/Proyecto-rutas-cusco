"""
comparacion.py
--------------
Experimentos para comparar los enfoques (los usa la pestaña "Comparación" de la
GUI y el informe técnico).

    python comparacion.py      # imprime las tablas en consola
"""
from __future__ import annotations

import random
import time

from algoritmos.backtracking import tsp_backtracking
from algoritmos.busqueda import busqueda_binaria, busqueda_secuencial, preparar_busqueda
from algoritmos.ordenacion import merge_sort, quick_sort
from algoritmos.prog_dinamica import held_karp, mochila_01
from algoritmos.voraz import mochila_voraz, ruta_vecino_mas_cercano
from datos import ALMACEN, LUGARES, pedidos_aleatorios
from grafo import Grafo


def _cronometrar(f, *args):
    t0 = time.perf_counter()
    r = f(*args)
    return r, (time.perf_counter() - t0) * 1000.0      # ms


def comparar_rutas(ns=range(3, 11), instancias: int = 5, semilla: int = 7,
                   limite_bt: int = 10) -> list[dict]:
    """Ruta que visita n paradas: Voraz (vecino más cercano) vs PD (Held-Karp)
    vs Backtracking (exacto con poda). Promedio sobre varias instancias."""
    g = Grafo()
    rnd = random.Random(semilla)
    nombres = [n for n in LUGARES if n != ALMACEN]
    filas = []
    for n in ns:
        acum = dict(c_nn=0.0, c_hk=0.0, t_nn=0.0, t_hk=0.0, t_bt=0.0, peor=1.0, optimos=0)
        for _ in range(instancias):
            lugares = [ALMACEN] + rnd.sample(nombres, n)
            D, _ = g.matriz_distancias(lugares)
            (_, c_nn), t_nn = _cronometrar(ruta_vecino_mas_cercano, D, 0)
            (_, c_hk), t_hk = _cronometrar(held_karp, D, 0)
            if n <= limite_bt:
                (_, c_bt), t_bt = _cronometrar(tsp_backtracking, D, 0)
                assert abs(c_bt - c_hk) < 1e-6          # ambos exactos
                acum["t_bt"] += t_bt
            acum["c_nn"] += c_nn; acum["c_hk"] += c_hk
            acum["t_nn"] += t_nn; acum["t_hk"] += t_hk
            acum["peor"] = max(acum["peor"], c_nn / c_hk)
            acum["optimos"] += abs(c_nn - c_hk) < 1e-6
        k = instancias
        filas.append(dict(
            n=n,
            costo_voraz=acum["c_nn"] / k, costo_optimo=acum["c_hk"] / k,
            exceso=100 * (acum["c_nn"] / acum["c_hk"] - 1),
            peor=100 * (acum["peor"] - 1), optimos=acum["optimos"], instancias=k,
            t_voraz=acum["t_nn"] / k, t_pd=acum["t_hk"] / k,
            t_bt=acum["t_bt"] / k if n <= limite_bt else None,
        ))
    return filas


def comparar_mochila(ns=(10, 20, 40, 80, 160), capacidad: int = 30,
                     instancias: int = 5, semilla: int = 3) -> list[dict]:
    """Mochila 0/1: voraz (valor/peso) vs programación dinámica."""
    filas = []
    for n in ns:
        a = dict(v_g=0, v_dp=0, t_g=0.0, t_dp=0.0, iguales=0)
        for s in range(instancias):
            ped = pedidos_aleatorios(n, semilla=semilla * 1000 + n * 10 + s)
            (_, v_g, _), t_g = _cronometrar(mochila_voraz, ped, capacidad)
            (_, v_dp, _, _), t_dp = _cronometrar(mochila_01, ped, capacidad)
            a["v_g"] += v_g; a["v_dp"] += v_dp; a["t_g"] += t_g; a["t_dp"] += t_dp
            a["iguales"] += v_g == v_dp
        k = instancias
        filas.append(dict(n=n, capacidad=capacidad, valor_voraz=a["v_g"] / k,
                          valor_pd=a["v_dp"] / k, perdida=100 * (1 - a["v_g"] / a["v_dp"]),
                          iguales=a["iguales"], instancias=k,
                          t_voraz=a["t_g"] / k, t_pd=a["t_dp"] / k))
    return filas


def comparar_ordenacion(ns=(100, 1000, 5000, 20000), semilla: int = 1) -> list[dict]:
    filas = []
    for n in ns:
        ped = pedidos_aleatorios(n, semilla=semilla)
        for p in ped:
            p.distancia = random.Random(p.id).uniform(0, 7000)
        clave = lambda p: (-p.prioridad, p.distancia)
        r1, t_m = _cronometrar(merge_sort, ped, clave)
        r2, t_q = _cronometrar(quick_sort, ped, clave)
        assert [clave(p) for p in r1] == [clave(p) for p in r2]
        filas.append(dict(n=n, t_merge=t_m, t_quick=t_q))
    return filas


def comparar_busqueda(ns=(100, 1000, 10000, 100000)) -> list[dict]:
    filas = []
    for n in ns:
        ped = pedidos_aleatorios(n, semilla=5)
        ordenados = preparar_busqueda(ped)
        objetivo = ordenados[-1].id                      # peor caso secuencial
        _, c_sec = busqueda_secuencial(ped, objetivo)
        _, c_bin = busqueda_binaria(ordenados, objetivo)
        filas.append(dict(n=n, comp_secuencial=c_sec, comp_binaria=c_bin))
    return filas


if __name__ == "__main__":
    print("RUTAS (n paradas)")
    for f in comparar_rutas():
        print(f)
    print("\nMOCHILA")
    for f in comparar_mochila():
        print(f)
    print("\nORDENACIÓN")
    for f in comparar_ordenacion():
        print(f)
    print("\nBÚSQUEDA")
    for f in comparar_busqueda():
        print(f)
