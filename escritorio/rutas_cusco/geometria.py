"""
geometria.py
------------
Convierte recorridos del grafo (listas de lugares) en coordenadas para dibujar.

* Con datos de OpenStreetMap (osm.py): cada calle sigue el trazo real de las
  vías y cada lugar se ubica en el nodo vial más cercano.
* Sin ellos: cada calle es un segmento recto entre sus dos lugares.

También interpola la posición de un vehículo que avanza por una calle
(para la simulación en tiempo real).
"""
from __future__ import annotations

import math

from datos import LUGARES


def _m(p, q) -> float:
    """Distancia aproximada en metros entre dos (lat, lon) cercanos."""
    lat = math.radians((p[0] + q[0]) / 2)
    dy = (q[0] - p[0]) * 111_320.0
    dx = (q[1] - p[1]) * 111_320.0 * math.cos(lat)
    return math.hypot(dx, dy)


class Geometria:
    def __init__(self, datos_osm: dict | None = None) -> None:
        self.pos: dict[str, tuple[float, float]] = {n: (l.lat, l.lon) for n, l in LUGARES.items()}
        self._tramos: dict[tuple[str, str], list[tuple[float, float]]] = {}
        self.nombre_real: dict[frozenset, str] = {}
        self.real = False
        if datos_osm:
            for n, (la, lo) in datos_osm.get("lugares", {}).items():
                if n in self.pos:
                    self.pos[n] = (la, lo)
            for c in datos_osm.get("calles", []):
                pts = [tuple(p) for p in c.get("geometria") or []]
                if len(pts) >= 2:
                    self._tramos[(c["a"], c["b"])] = pts
                    self._tramos[(c["b"], c["a"])] = pts[::-1]
                    self.real = True
                if c.get("nombre_osm"):
                    self.nombre_real[frozenset((c["a"], c["b"]))] = c["nombre_osm"]
        self._acum: dict[tuple[str, str], list[float]] = {}

    # ------------------------------------------------------------------
    def tramo(self, a: str, b: str) -> list[tuple[float, float]]:
        """Trazo de la calle a → b (real si existe, si no, recto)."""
        return self._tramos.get((a, b)) or [self.pos[a], self.pos[b]]

    def camino(self, nodos: list[str]) -> list[tuple[float, float]]:
        """Trazo continuo de un recorrido [n0, n1, ..., nk]."""
        if len(nodos) == 1:
            return [self.pos[nodos[0]]]
        pts: list[tuple[float, float]] = []
        for a, b in zip(nodos, nodos[1:]):
            seg = self.tramo(a, b)
            pts.extend(seg if not pts else seg[1:])
        return pts

    def punto(self, a: str, b: str, frac: float) -> tuple[float, float]:
        """Coordenada a la fracción `frac` (0..1) del recorrido de la calle a → b."""
        seg = self.tramo(a, b)
        if (a, b) not in self._acum:
            acc = [0.0]
            for p, q in zip(seg, seg[1:]):
                acc.append(acc[-1] + _m(p, q))
            self._acum[(a, b)] = acc
        acc = self._acum[(a, b)]
        objetivo = max(0.0, min(1.0, frac)) * acc[-1]
        for i in range(1, len(acc)):
            if acc[i] >= objetivo:
                largo = acc[i] - acc[i - 1]
                t = 0.0 if largo == 0 else (objetivo - acc[i - 1]) / largo
                p, q = seg[i - 1], seg[i]
                return p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        return seg[-1]

    def resto(self, a: str, b: str, frac: float) -> list[tuple[float, float]]:
        """Trazo desde la fracción `frac` de la calle a → b hasta b."""
        seg = self.tramo(a, b)
        inicio = self.punto(a, b, frac)
        acc = self._acum[(a, b)]
        objetivo = frac * acc[-1]
        k = next((i for i in range(1, len(acc)) if acc[i] > objetivo), len(seg) - 1)
        return [inicio] + seg[k:]

    def lugar_cercano(self, lat: float, lon: float, maximo: float = 250.0) -> str | None:
        """Lugar más cercano a un clic (o None si está a más de `maximo` metros)."""
        mejor = min(self.pos, key=lambda n: _m((lat, lon), self.pos[n]))
        return mejor if _m((lat, lon), self.pos[mejor]) <= maximo else None
