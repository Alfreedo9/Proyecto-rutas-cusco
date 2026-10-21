"""
divide_venceras.py
------------------
DIVIDE Y VENCERÁS: segmentación de la ciudad en zonas.

En lugar de calcular una sola ruta para todos los pedidos de Cusco (problema
exponencial), el mapa se divide recursivamente en sub-zonas y cada repartidor
resuelve la ruta óptima SOLO de su sub-zona.

* DIVIDIR   : se corta el conjunto de pedidos por la mediana de la longitud
              (corte vertical) o de la latitud (corte horizontal), alternando.
              Así cada corte deja dos mitades con la misma cantidad de pedidos.
* VENCER    : cuando quedan k = 1 zonas, se resuelve la ruta de esa zona con
              Held-Karp (programación dinámica, óptima) si la zona es pequeña,
              o con el vecino más cercano si es grande.
* COMBINAR  : se juntan las rutas de todas las zonas (distancia total y la de la
              zona más larga, que marca el tiempo de la operación).

Recurrencia de la división:  T(n) = 2 T(n/2) + O(n log n)  =>  O(n log^2 n)
(se ordena por coordenada en cada nivel con merge sort; hay log k niveles).
"""
from __future__ import annotations

from algoritmos.ordenacion import merge_sort
from algoritmos.prog_dinamica import held_karp
from algoritmos.voraz import ruta_vecino_mas_cercano
from datos import LUGARES

LIMITE_HELD_KARP = 12   # zonas con más puntos usan la heurística voraz


def dividir(pedidos: list, k: int, profundidad: int = 0, caja=None) -> list[dict]:
    """Divide `pedidos` en k zonas balanceadas (árbol k-d).

    Retorna una lista de zonas: {"pedidos": [...], "caja": (lat_min, lat_max,
    lon_min, lon_max)} — la caja sirve para dibujar la zona en el mapa.
    """
    if caja is None:
        lats = [LUGARES[p.lugar].lat for p in pedidos] or [0]
        lons = [LUGARES[p.lugar].lon for p in pedidos] or [0]
        m = 0.002
        caja = (min(lats) - m, max(lats) + m, min(lons) - m, max(lons) + m)

    if k <= 1 or len(pedidos) <= 1:                        # caso base
        return [{"pedidos": pedidos, "caja": caja}]

    # Eje de corte: alterna longitud (vertical) y latitud (horizontal)
    eje_lon = profundidad % 2 == 0
    coord = (lambda p: LUGARES[p.lugar].lon) if eje_lon else (lambda p: LUGARES[p.lugar].lat)
    ordenados = merge_sort(pedidos, clave=coord)           # O(n log n)

    k_izq = k // 2
    corte = round(len(ordenados) * k_izq / k)              # reparto proporcional
    corte = min(max(corte, 1), len(ordenados) - 1)
    izq, der = ordenados[:corte], ordenados[corte:]
    frontera = (coord(izq[-1]) + coord(der[0])) / 2

    lat0, lat1, lon0, lon1 = caja
    if eje_lon:
        caja_i, caja_d = (lat0, lat1, lon0, frontera), (lat0, lat1, frontera, lon1)
    else:
        caja_i, caja_d = (lat0, frontera, lon0, lon1), (frontera, lat1, lon0, lon1)

    return (dividir(izq, k_izq, profundidad + 1, caja_i) +          # vencer
            dividir(der, k - k_izq, profundidad + 1, caja_d))       # (y combinar)


def asignar_zonas(zonas: list[dict], repartidores: list) -> None:
    """Empareja cada zona con el repartidor libre más cercano a su centro (voraz)."""
    libres = list(repartidores)
    for z in zonas:
        if not z["pedidos"]:
            z["repartidor"] = None
            continue
        clat = sum(LUGARES[p.lugar].lat for p in z["pedidos"]) / len(z["pedidos"])
        clon = sum(LUGARES[p.lugar].lon for p in z["pedidos"]) / len(z["pedidos"])
        r = min(libres, key=lambda r: (LUGARES[r.ubicacion].lat - clat) ** 2 +
                                      (LUGARES[r.ubicacion].lon - clon) ** 2)
        z["repartidor"] = r
        if len(libres) > 1:
            libres.remove(r)


def resolver_zonas(pedidos: list, repartidores: list, grafo) -> dict:
    """Divide la ciudad en tantas zonas como repartidores y resuelve cada zona."""
    zonas = dividir(pedidos, len(repartidores))
    asignar_zonas(zonas, repartidores)
    total, maxima = 0.0, 0.0
    for z in zonas:
        r = z.get("repartidor")
        if r is None:
            z.update(ruta=[], costo=0.0, metodo="-", tramos=[])
            continue
        lugares = [r.ubicacion] + [p.lugar for p in z["pedidos"]]
        D, caminos = grafo.matriz_distancias(lugares)
        if len(lugares) <= LIMITE_HELD_KARP:
            orden, costo = held_karp(D, 0)
            metodo = "Held-Karp (PD, óptimo)"
        else:
            orden, costo = ruta_vecino_mas_cercano(D, 0)
            metodo = "Vecino más cercano (voraz)"
        z["ruta"] = [lugares[i] for i in orden]
        z["orden_pedidos"] = [z["pedidos"][i - 1] for i in orden[1:]]
        z["tramos"] = [caminos[(orden[t], orden[t + 1])] for t in range(len(orden) - 1)]
        z["costo"], z["metodo"] = costo, metodo
        total += costo
        maxima = max(maxima, costo)
    return {"zonas": zonas, "total": total, "maxima": maxima}
