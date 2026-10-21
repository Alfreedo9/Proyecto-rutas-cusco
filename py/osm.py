"""
osm.py
------
Calles REALES de Cusco desde OpenStreetMap (OSM).

El grafo del proyecto tiene 28 lugares y 46 calles (datos.py). Este módulo
descarga la red vial real de la zona con la API Overpass de OSM y, para cada
una de las 46 calles, encuentra su recorrido sobre las calles reales:

  1. Descarga las vías (highway=*) dentro del rectángulo que contiene los lugares.
  2. Construye el grafo vial de OSM (miles de nodos) con lista de adyacencia.
  3. Ajusta cada lugar al nodo de OSM más cercano (de la componente conexa mayor).
  4. Para cada calle (a, b) ejecuta Dijkstra sobre la red real y guarda el
     trazo (lista de coordenadas), su longitud real y el nombre de la vía.

El resultado se guarda en data/cusco_osm.json; así la aplicación funciona
sin internet una vez generado (los algoritmos siguen usando el grafo de 28
lugares, pero dibujan las rutas por las calles reales).

Uso:
    python osm.py            # descarga y genera data/cusco_osm.json

Datos: © colaboradores de OpenStreetMap, licencia ODbL.
Solo usa la biblioteca estándar (urllib, json, heapq).
"""
from __future__ import annotations

import heapq
import json
import math
import os
import time
import urllib.parse
import urllib.request
from collections import deque

from datos import CALLES_DEF, LUGARES

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RUTA_CACHE = os.path.join(CARPETA, "cusco_osm.json")

SERVIDORES = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Tipos de vía por los que puede circular una moto o una furgoneta de reparto
TIPOS_VIA = ("motorway|trunk|primary|secondary|tertiary|unclassified|residential|"
             "living_street|service|road|track|pedestrian|motorway_link|trunk_link|"
             "primary_link|secondary_link|tertiary_link")

AGENTE = "RutasCusco-UNSAAC/1.0 (proyecto academico Programacion III)"


# ---------------------------------------------------------------- utilidades
def metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia Haversine en metros."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def caja_lugares(margen: float = 0.006) -> tuple[float, float, float, float]:
    """(sur, oeste, norte, este) que contiene todos los lugares, con margen en grados."""
    lats = [l.lat for l in LUGARES.values()]
    lons = [l.lon for l in LUGARES.values()]
    return min(lats) - margen, min(lons) - margen, max(lats) + margen, max(lons) + margen


def consulta_overpass(caja=None) -> str:
    s, w, n, e = caja or caja_lugares()
    return (f'[out:json][timeout:120];'
            f'way["highway"~"^({TIPOS_VIA})$"]["access"!~"^(private|no)$"]'
            f'({s:.5f},{w:.5f},{n:.5f},{e:.5f});out geom;')


# ---------------------------------------------------------------- descarga
def _post(url: str, consulta: str, timeout: int) -> dict:
    """POST a Overpass. Usa `requests` si está (trae certificados propios, útil en
    macOS); si no, urllib de la biblioteca estándar."""
    try:
        import requests
        r = requests.post(url, data={"data": consulta}, headers={"User-Agent": AGENTE}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except ImportError:
        datos = urllib.parse.urlencode({"data": consulta}).encode()
        req = urllib.request.Request(url, data=datos, headers={"User-Agent": AGENTE})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)


def descargar(caja=None, timeout: int = 150, avisar=print) -> dict:
    """Descarga la red vial de la zona desde Overpass (prueba varios servidores)."""
    consulta = consulta_overpass(caja)
    errores = []
    for url in SERVIDORES:
        try:
            avisar(f"Descargando calles desde {url.split('/')[2]} ...")
            osm = _post(url, consulta, timeout)
            if osm.get("elements"):
                return osm
            errores.append(f"{url}: respuesta vacía")
        except Exception as ex:                                    # noqa: BLE001
            errores.append(f"{url}: {ex}")
    raise ConnectionError("No se pudo descargar la red de OpenStreetMap.\n" + "\n".join(errores))


# ---------------------------------------------------------------- grafo real
def construir_red(osm: dict):
    """Grafo vial de OSM: coords[id] = (lat, lon); adj[id] = [(id2, metros, nombre)]."""
    coords: dict[int, tuple[float, float]] = {}
    adj: dict[int, list[tuple[int, float, str]]] = {}
    for el in osm.get("elements", []):
        if el.get("type") != "way":
            continue
        ids, geom = el.get("nodes"), el.get("geometry")
        if not ids or not geom or len(ids) != len(geom):
            continue
        tags = el.get("tags", {})
        nombre = tags.get("name") or tags.get("ref") or ""
        for nid, g in zip(ids, geom):
            coords[nid] = (g["lat"], g["lon"])
        for u, v in zip(ids, ids[1:]):
            w = metros(*coords[u], *coords[v])
            adj.setdefault(u, []).append((v, w, nombre))
            adj.setdefault(v, []).append((u, w, nombre))
    return coords, adj


def componente_mayor(adj: dict) -> set:
    """Nodos de la componente conexa más grande (BFS)."""
    visto, mejor = set(), set()
    for s in adj:
        if s in visto:
            continue
        comp, cola = {s}, deque([s])
        visto.add(s)
        while cola:
            u = cola.popleft()
            for v, _, _ in adj[u]:
                if v not in visto:
                    visto.add(v)
                    comp.add(v)
                    cola.append(v)
        if len(comp) > len(mejor):
            mejor = comp
    return mejor


def nodo_cercano(coords: dict, lat: float, lon: float, permitidos: set) -> int:
    """Nodo de la red más cercano a (lat, lon). Búsqueda lineal O(V)."""
    return min(permitidos, key=lambda n: metros(lat, lon, *coords[n]))


def _dijkstra(adj: dict, origen: int, objetivos: set):
    """Dijkstra con montículo; se detiene al fijar todos los objetivos."""
    dist = {origen: 0.0}
    prev: dict[int, tuple[int, str]] = {}
    pendientes = set(objetivos)
    heap = [(0.0, origen)]
    fijados = set()
    while heap and pendientes:
        d, u = heapq.heappop(heap)
        if u in fijados:
            continue
        fijados.add(u)
        pendientes.discard(u)
        for v, w, nombre in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = (u, nombre)
                heapq.heappush(heap, (nd, v))
    return dist, prev


def trazar(osm: dict, avisar=print) -> dict:
    """Ajusta los lugares a la red real y traza cada calle del grafo sobre ella."""
    coords, adj = construir_red(osm)
    if not adj:
        raise ValueError("La respuesta de OpenStreetMap no contiene calles.")
    comp = componente_mayor(adj)
    avisar(f"Red vial: {len(coords):,} nodos, componente principal {len(comp):,}.")
    nodo = {n: nodo_cercano(coords, l.lat, l.lon, comp) for n, l in LUGARES.items()}

    destinos: dict[str, set] = {}
    for a, b, _ in CALLES_DEF:
        destinos.setdefault(a, set()).add(nodo[b])

    calles, cache = [], {}
    for a, b, nombre in CALLES_DEF:
        if a not in cache:
            cache[a] = _dijkstra(adj, nodo[a], destinos[a])
        dist, prev = cache[a]
        t = nodo[b]
        if t not in dist:
            calles.append({"a": a, "b": b, "nombre": nombre, "nombre_osm": "",
                           "metros": None, "geometria": []})
            continue
        camino, por_nombre = [t], {}
        while camino[-1] != nodo[a]:
            u, nm = prev[camino[-1]]
            if nm:
                por_nombre[nm] = por_nombre.get(nm, 0.0) + metros(*coords[u], *coords[camino[-1]])
            camino.append(u)
        camino.reverse()
        calles.append({
            "a": a, "b": b, "nombre": nombre,
            "nombre_osm": max(por_nombre, key=por_nombre.get) if por_nombre else "",
            "metros": round(dist[t], 1),
            "geometria": [[round(coords[x][0], 6), round(coords[x][1], 6)] for x in camino],
        })
    return {
        "fuente": "© colaboradores de OpenStreetMap (ODbL)",
        "fecha": time.strftime("%Y-%m-%d %H:%M"),
        "nodos_red": len(coords),
        "lugares": {n: [round(coords[i][0], 6), round(coords[i][1], 6)] for n, i in nodo.items()},
        "calles": calles,
    }


# ---------------------------------------------------------------- caché
def generar_cache(avisar=print) -> dict:
    """Descarga, procesa y guarda data/cusco_osm.json. Retorna los datos."""
    osm = descargar(avisar=avisar)
    avisar("Trazando las 46 calles sobre la red real ...")
    datos = trazar(osm, avisar)
    os.makedirs(CARPETA, exist_ok=True)
    with open(RUTA_CACHE, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    ok = sum(1 for c in datos["calles"] if c["geometria"])
    avisar(f"Listo: {ok}/{len(datos['calles'])} calles trazadas → {RUTA_CACHE}")
    return datos


def cargar() -> dict | None:
    """Datos de OSM guardados, o None si todavía no se descargaron."""
    try:
        with open(RUTA_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def longitudes(datos: dict | None) -> dict:
    """{frozenset({a, b}): metros reales} para construir Grafo(longitudes=...)."""
    if not datos:
        return {}
    return {frozenset((c["a"], c["b"])): c["metros"] for c in datos["calles"] if c.get("metros")}


if __name__ == "__main__":
    generar_cache()
