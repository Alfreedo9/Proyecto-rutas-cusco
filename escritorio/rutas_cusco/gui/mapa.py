"""
gui/mapa.py
-----------
Lienzo (tk.Canvas) que dibuja el mapa de Cusco: calles, lugares, pedidos,
rutas, zonas y calles cerradas. Se redibuja solo al cambiar de tamaño.

Es el mapa SIMPLIFICADO: se usa cuando no está instalada la librería
tkintermapview (ver gui/mapa_real.py). Si existe data/cusco_osm.json, las
calles igual se dibujan con su forma real.
"""
from __future__ import annotations

import math
import tkinter as tk

from datos import ALMACEN, LUGARES
from geometria import Geometria

COLOR_FONDO = "#F4F1EA"
COLOR_CALLE = "#C9C2B3"
COLOR_NODO = "#5B5B5B"
COLOR_TEXTO = "#3A3A3A"
COLOR_PRIORIDAD = {5: "#D7263D", 4: "#F46036", 3: "#E2A100", 2: "#2E86AB", 1: "#6C757D"}
PALETA_RUTAS = ["#2A78D6", "#D7263D", "#1BAF7A", "#8E44AD", "#E67E22", "#16A085"]
PALETA_ZONAS = ["#DCEBFB", "#FBE0E3", "#DDF5EA", "#EEE2F5", "#FDEBD9", "#D9F2EE"]


class MapaCanvas(tk.Canvas):
    def __init__(self, master, grafo, datos_osm: dict | None = None, **kw):
        super().__init__(master, bg=COLOR_FONDO, highlightthickness=0, **kw)
        self.grafo = grafo
        self.geo = Geometria(datos_osm)
        self.entregados: set = set()
        self.moviles: dict = {}       # id → dict(lat, lon, color)   (simulación)
        self.rutas_vivas: dict = {}   # id → dict(coords, color)
        self.mostrar_nombres = True
        self.pedidos: list = []
        self.repartidores: list = []
        self.rutas: list = []        # dicts: tramos, color, dash, ancho, numerar
        self.zonas: list = []        # dicts: caja, color, etiqueta
        self.cerradas: set = set()   # frozenset({a, b})
        self.resaltados: set = set() # lugares resaltados
        self.on_click_lugar = None   # callback(nombre_lugar)
        self.on_click_calle = None   # callback(frozenset)
        self.titulo = ""
        self._margen = 40
        lats = [l.lat for l in LUGARES.values()]
        lons = [l.lon for l in LUGARES.values()]
        self._lat0, self._lat1 = min(lats), max(lats)
        self._lon0, self._lon1 = min(lons), max(lons)
        self.bind("<Configure>", lambda e: self.redibujar())
        self.bind("<Button-1>", self._click)

    # ------------------------------------------------------------ proyección
    def xy(self, lat: float, lon: float) -> tuple[float, float]:
        """Convierte (lat, lon) a píxeles manteniendo la proporción del mapa."""
        w = max(self.winfo_width(), 200) - 2 * self._margen - 90   # espacio para etiquetas
        h = max(self.winfo_height(), 200) - 2 * self._margen - 20
        # 1° de longitud mide cos(lat) veces lo que mide 1° de latitud
        ancho_geo = (self._lon1 - self._lon0) * math.cos(math.radians(self._lat0))
        alto_geo = self._lat1 - self._lat0
        esc = min(w / ancho_geo, h / alto_geo)
        ox = self._margen + (w - ancho_geo * esc) / 2
        oy = self._margen + 20 + (h - alto_geo * esc) / 2
        x = ox + (lon - self._lon0) * math.cos(math.radians(self._lat0)) * esc
        y = oy + (self._lat1 - lat) * esc
        return x, y

    def xy_lugar(self, nombre: str) -> tuple[float, float]:
        return self.xy(*self.geo.pos[nombre])

    def _pts(self, coords) -> list[float]:
        pts: list[float] = []
        for la, lo in coords:
            pts.extend(self.xy(la, lo))
        return pts

    # ------------------------------------------------------------ API
    def limpiar_capas(self) -> None:
        self.rutas, self.zonas, self.resaltados = [], [], set()
        self.titulo = ""

    def agregar_ruta(self, tramos: list[list[str]], color: str, dash=None,
                     ancho: int = 4, numerar: bool = True) -> None:
        self.rutas.append(dict(tramos=tramos, color=color, dash=dash,
                               ancho=ancho, numerar=numerar))

    def usar_osm(self, datos_osm: dict | None) -> None:
        self.geo = Geometria(datos_osm)
        self.redibujar()

    def centrar(self) -> None:
        self.redibujar()

    # --- capa dinámica (simulación en tiempo real)
    def limpiar_dinamica(self) -> None:
        self.moviles, self.rutas_vivas, self.entregados = {}, {}, set()

    def mover_movil(self, ident: str, lat: float, lon: float, color: str = "#1B998B") -> None:
        self.moviles[ident] = dict(lat=lat, lon=lon, color=color)
        self.delete("movil_" + ident)
        x, y = self.xy(lat, lon)
        self.create_oval(x - 11, y - 11, x + 11, y + 11, fill=color, outline="white", width=2,
                         tags=("movil_" + ident,))
        self.create_text(x, y, text=ident, fill="white", font=("Helvetica", 9, "bold"),
                         tags=("movil_" + ident,))

    def poner_ruta_viva(self, ident: str, coords: list, color: str) -> None:
        self.rutas_vivas[ident] = dict(coords=coords, color=color)
        self.delete("viva_" + ident)
        if len(coords) >= 2:
            self.create_line(*self._pts(coords), fill=color, width=5, arrow="last",
                             arrowshape=(12, 14, 5), capstyle="round", joinstyle="round",
                             tags=("viva_" + ident,))
            self.tag_raise("movil_" + ident)

    # ------------------------------------------------------------ dibujo
    def redibujar(self) -> None:
        self.delete("all")
        # zonas (divide y vencerás)
        for z in self.zonas:
            lat0, lat1, lon0, lon1 = z["caja"]
            x0, y0 = self.xy(lat1, lon0)
            x1, y1 = self.xy(lat0, lon1)
            self.create_rectangle(x0, y0, x1, y1, fill=z["color"], outline=z["borde"],
                                  width=2, dash=(6, 4))
            self.create_text(x0 + 6, y0 + 4, text=z["etiqueta"], anchor="nw",
                             fill=z["borde"], font=("Helvetica", 11, "bold"))
        # calles
        for a, b, _, _ in self.grafo.calles:
            pts = self._pts(self.geo.tramo(a, b))
            if frozenset((a, b)) in self.cerradas:
                self.create_line(*pts, fill="#D7263D", width=4, dash=(4, 3))
                mx, my = self.xy(*self.geo.punto(a, b, 0.5))
                self.create_text(mx, my, text="✕", fill="#D7263D", font=("Helvetica", 14, "bold"))
            else:
                self.create_line(*pts, fill=COLOR_CALLE, width=5, capstyle="round", joinstyle="round")
        # rutas
        for r in self.rutas:
            self._dibujar_ruta(r)
        for ident, rv in self.rutas_vivas.items():
            if len(rv["coords"]) >= 2:
                self.create_line(*self._pts(rv["coords"]), fill=rv["color"], width=5, arrow="last",
                                 arrowshape=(12, 14, 5), capstyle="round", joinstyle="round",
                                 tags=("viva_" + ident,))
        # lugares
        for n in LUGARES:
            x, y = self.xy_lugar(n)
            rad = 7 if n in self.resaltados else 4
            col = "#FFD23F" if n in self.resaltados else COLOR_NODO
            self.create_oval(x - rad, y - rad, x + rad, y + rad, fill=col, outline="#222")
            if self.mostrar_nombres or n in self.resaltados:
                self.create_text(x + 7, y - 7, text=n, anchor="sw", fill=COLOR_TEXTO,
                                 font=("Helvetica", 8))
        # almacén
        x, y = self.xy_lugar(ALMACEN)
        self.create_rectangle(x - 9, y - 9, x + 9, y + 9, fill="#222", outline="")
        self.create_text(x, y, text="A", fill="white", font=("Helvetica", 9, "bold"))
        # repartidores
        for r in self.repartidores:
            if r.id in self.moviles:
                continue
            x, y = self.xy_lugar(r.ubicacion)
            self.create_oval(x - 11, y + 5, x + 11, y + 27, fill="#1B998B", outline="white", width=2)
            self.create_text(x, y + 16, text=r.id, fill="white", font=("Helvetica", 8, "bold"))
        # pedidos
        conteo: dict[str, int] = {}
        for p in self.pedidos:
            k = conteo.get(p.lugar, 0)
            conteo[p.lugar] = k + 1
            x, y = self.xy_lugar(p.lugar)
            x += 10 + 30 * k
            y += 4
            col = "#9E9E9E" if p.id in self.entregados else COLOR_PRIORIDAD.get(p.prioridad, "#666")
            self.create_rectangle(x, y, x + 28, y + 13, fill=col, outline="white")
            self.create_text(x + 14, y + 6.5, text=p.id, fill="white", font=("Helvetica", 7, "bold"))
        for ident, mv in self.moviles.items():
            self.mover_movil(ident, mv["lat"], mv["lon"], mv["color"])
        self._leyenda()
        if self.titulo:
            self.create_text(12, 10, text=self.titulo, anchor="nw",
                             font=("Helvetica", 12, "bold"), fill="#222")

    def _dibujar_ruta(self, r: dict) -> None:
        parada = 0
        for tramo in r["tramos"]:
            if len(tramo) < 2:
                continue
            pts = self._pts(self.geo.camino(tramo))
            self.create_line(*pts, fill=r["color"], width=r["ancho"], dash=r["dash"],
                             arrow="last", arrowshape=(12, 14, 5), capstyle="round",
                             joinstyle="round", smooth=False)
            parada += 1
            if r["numerar"]:
                x, y = self.xy_lugar(tramo[-1])
                self.create_oval(x - 9, y - 20, x + 9, y - 2, fill=r["color"], outline="white")
                self.create_text(x, y - 11, text=str(parada), fill="white",
                                 font=("Helvetica", 8, "bold"))

    def _leyenda(self) -> None:
        h = self.winfo_height()
        x, y = 12, h - 24
        self.create_rectangle(x - 6, y - 8, x + 520, y + 12, fill="white", outline="#BBB")
        items = [("#222", "Almacén"), ("#1B998B", "Repartidor")] + \
                [(COLOR_PRIORIDAD[k], f"Prio {k}") for k in (5, 4, 3, 2, 1)]
        for col, txt in items:
            self.create_rectangle(x, y - 3, x + 10, y + 7, fill=col, outline="")
            self.create_text(x + 14, y + 2, text=txt, anchor="w", font=("Helvetica", 8))
            x += 70

    # ------------------------------------------------------------ clic
    def _click(self, e) -> None:
        # ¿Clic sobre un lugar?
        mejor, dmin = None, 14.0
        for n in LUGARES:
            x, y = self.xy_lugar(n)
            d = math.hypot(e.x - x, e.y - y)
            if d < dmin:
                mejor, dmin = n, d
        if mejor and self.on_click_lugar:
            self.on_click_lugar(mejor)
            return
        # ¿Clic sobre una calle?
        mejor, dmin = None, 8.0
        for a, b, _, _ in self.grafo.calles:
            pts = self._pts(self.geo.tramo(a, b))
            for k in range(0, len(pts) - 2, 2):
                d = _dist_segmento(e.x, e.y, *pts[k:k + 4])
                if d < dmin:
                    mejor, dmin = frozenset((a, b)), d
        if mejor and self.on_click_calle:
            self.on_click_calle(mejor)


def _dist_segmento(px, py, x0, y0, x1, y1) -> float:
    dx, dy = x1 - x0, y1 - y0
    if dx == dy == 0:
        return math.hypot(px - x0, py - y0)
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))
