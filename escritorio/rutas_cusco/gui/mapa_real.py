"""
gui/mapa_real.py
----------------
Mapa REAL de Cusco con teselas de OpenStreetMap (librería tkintermapview).

* El fondo se descarga en vivo (zoom con la rueda, arrastrar para moverse).
* Las 46 calles del grafo se dibujan siguiendo el trazo real de las vías
  (si existe data/cusco_osm.json, ver osm.py) y se pueden cerrar con un clic.
* Lugares, almacén, repartidores, pedidos, rutas, zonas y vehículos en
  movimiento se dibujan encima.

Tiene la misma interfaz que gui/mapa.py (MapaCanvas), así la aplicación
puede usar cualquiera de los dos.
"""
from __future__ import annotations

import math
import os
import time
import tkinter as tk

import tkintermapview
from tkintermapview.utility_functions import decimal_to_osm

from datos import ALMACEN, LUGARES
from geometria import Geometria
from gui.mapa import COLOR_PRIORIDAD

# nombre → (URL de teselas, zoom máximo, atribución). Todos funcionan sin clave de API.
SERVIDORES_MAPA = {
    "Calles (OpenStreetMap)": ("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", 19,
                               "© OpenStreetMap"),
    "Claro (Esri)": ("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
                     "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", 16,
                     "© Esri · © OpenStreetMap"),
    "Satélite (Esri)": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/"
                        "MapServer/tile/{z}/{y}/{x}", 19, "© Esri · © OpenStreetMap"),
}
RUTA_TESELAS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "cusco_teselas.db")

COLOR_CALLE = "#2F7E9A"
COLOR_CERRADA = "#D7263D"
FUENTE = ("Helvetica", 9, "bold")


class Insignia:
    """Figura propia (círculo, cuadrado o píldora con texto) anclada a una coordenada.

    Se registra en la lista de marcadores del mapa, así tkintermapview la
    redibuja sola al mover o hacer zoom.
    """

    def __init__(self, mapa: "MapaReal", lat: float, lon: float, texto: str = "",
                 relleno: str = "#00404A", borde: str = "white", forma: str = "circulo",
                 radio: int = 10, color_texto: str = "white", fuente=FUENTE, dx: int = 0,
                 dy: int = 0, comando=None, etiqueta: str | None = None) -> None:
        self.mapa, self.lat, self.lon = mapa, lat, lon
        self.texto, self.relleno, self.borde, self.forma = texto, relleno, borde, forma
        self.radio, self.color_texto, self.fuente = radio, color_texto, fuente
        self.dx, self.dy, self.comando, self.etiqueta = dx, dy, comando, etiqueta
        self.items: list[int] = []
        self.x = self.y = 0.0
        self.deleted = False
        mapa.canvas_marker_list.append(self)
        self.draw()

    # posición en el lienzo (misma fórmula que tkintermapview)
    def _xy(self) -> tuple[float, float]:
        m = self.mapa
        tx, ty = decimal_to_osm(self.lat, self.lon, round(m.zoom))
        ancho = m.lower_right_tile_pos[0] - m.upper_left_tile_pos[0]
        alto = m.lower_right_tile_pos[1] - m.upper_left_tile_pos[1]
        if ancho == 0 or alto == 0:
            return -999.0, -999.0
        x = (tx - m.upper_left_tile_pos[0]) / ancho * m.width + self.dx
        y = (ty - m.upper_left_tile_pos[1]) / alto * m.height + self.dy
        return x, y

    def _crear(self, x: float, y: float) -> None:
        c, r = self.mapa.canvas, self.radio
        if self.forma == "circulo":
            fig = c.create_oval(x - r, y - r, x + r, y + r, fill=self.relleno, outline=self.borde,
                                width=2, tags="marker")
        elif self.forma == "cuadrado":
            fig = c.create_rectangle(x - r, y - r, x + r, y + r, fill=self.relleno,
                                     outline=self.borde, width=2, tags="marker")
        else:  # píldora con el ancho del texto
            w = max(r, 4 * len(self.texto) + 6)
            fig = c.create_rectangle(x - w, y - 8, x + w, y + 8, fill=self.relleno,
                                     outline=self.borde, width=1, tags="marker")
        self.items = [fig]
        if self.texto:
            self.items.append(c.create_text(x, y, text=self.texto, fill=self.color_texto,
                                            font=self.fuente, tags="marker"))
        if self.etiqueta:
            t = c.create_text(x + r + 4, y, text=self.etiqueta, anchor="w", fill="#1F2A30",
                              font=("Helvetica", 9), tags="marker")
            x0, y0, x1, y1 = c.bbox(t)
            fondo = c.create_rectangle(x0 - 2, y0 - 1, x1 + 2, y1 + 1, fill="white",
                                       outline="#9AA7AD", tags="marker")
            c.tag_lower(fondo, t)
            self.items += [fondo, t]
        if self.comando:
            for it in self.items:
                c.tag_bind(it, "<Button-1>", self._clic)
                c.tag_bind(it, "<Enter>", lambda e: self.mapa.canvas.config(cursor="hand2"))
                c.tag_bind(it, "<Leave>", lambda e: self.mapa.canvas.config(cursor=""))
        self.x, self.y = x, y

    def draw(self, event=None) -> None:
        if self.deleted:
            return
        x, y = self._xy()
        visible = -80 < x < self.mapa.width + 80 and -80 < y < self.mapa.height + 80
        if not visible:
            self._borrar_items()
            return
        if not self.items:
            self._crear(x, y)
        else:
            for it in self.items:
                self.mapa.canvas.move(it, x - self.x, y - self.y)
            self.x, self.y = x, y

    def set_position(self, lat: float, lon: float) -> None:
        self.lat, self.lon = lat, lon
        self.draw()
        for it in self.items:
            self.mapa.canvas.tag_raise(it)

    def _clic(self, _e=None) -> None:
        self.mapa.ultimo_clic_objeto = time.time()
        self.comando(self)

    def _borrar_items(self) -> None:
        for it in self.items:
            self.mapa.canvas.delete(it)
        self.items = []

    def delete(self) -> None:
        if self in self.mapa.canvas_marker_list:
            self.mapa.canvas_marker_list.remove(self)
        self._borrar_items()
        self.deleted = True


class MapaReal(tkintermapview.TkinterMapView):
    def __init__(self, master, grafo, datos_osm: dict | None = None, **kw):
        base = RUTA_TESELAS if os.path.exists(RUTA_TESELAS) else None
        super().__init__(master, corner_radius=0, database_path=base, **kw)
        self.grafo = grafo
        self.geo = Geometria(datos_osm)
        self.pedidos: list = []
        self.repartidores: list = []
        self.rutas: list = []
        self.zonas: list = []
        self.cerradas: set = set()
        self.resaltados: set = set()
        self.entregados: set = set()
        self.moviles: dict = {}           # id → dict(lat, lon, color)
        self.rutas_vivas: dict = {}       # id → dict(coords, color)
        self.on_click_lugar = None
        self.on_click_calle = None
        self.titulo = ""
        self.mostrar_nombres = False
        self.ultimo_clic_objeto = 0.0
        self._insignias: list[Insignia] = []
        self._obj_moviles: dict[str, Insignia] = {}
        self._obj_vivas: dict[str, object] = {}

        url, maximo, _ = SERVIDORES_MAPA["Calles (OpenStreetMap)"]
        self.set_tile_server(url, max_zoom=maximo)
        self.add_left_click_map_command(self._clic_mapa)
        self.lbl_titulo = tk.Label(self, text="", bg="white", fg="#1F2A30",
                                   font=("Helvetica", 12, "bold"), padx=8, pady=3)
        self._leyenda()
        self.lbl_fuente = tk.Label(self, text="© OpenStreetMap", bg="white", fg="#555",
                                   font=("Helvetica", 8))
        self.lbl_fuente.place(relx=1.0, rely=1.0, anchor="se")
        self.after(400, self.centrar)

    # ------------------------------------------------------------ vista
    def centrar(self) -> None:
        """Encuadra los 28 lugares con el mayor zoom posible."""
        self.update_idletasks()
        w, h = max(self.winfo_width(), 400), max(self.winfo_height(), 300)
        lats = [p[0] for p in self.geo.pos.values()]
        lons = [p[1] for p in self.geo.pos.values()]

        def merc_y(lat):          # coordenada y de Mercator en [0, 1]
            s = math.sin(math.radians(lat))
            return 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)

        ancho = (max(lons) - min(lons)) / 360.0
        alto = merc_y(min(lats)) - merc_y(max(lats))
        zoom = min(math.log2((w - 60) / (256 * ancho)), math.log2((h - 90) / (256 * alto)))
        self.set_position((max(lats) + min(lats)) / 2, (max(lons) + min(lons)) / 2)
        self.set_zoom(max(12, min(17, math.floor(zoom))))

    def cambiar_fondo(self, nombre: str) -> None:
        url, maximo, fuente = SERVIDORES_MAPA[nombre]
        self.set_tile_server(url, max_zoom=maximo)
        self.lbl_fuente.configure(text=fuente)
        if self.zoom > maximo:
            self.set_zoom(maximo)

    def usar_osm(self, datos_osm: dict | None) -> None:
        self.geo = Geometria(datos_osm)
        self.redibujar()

    def _leyenda(self) -> None:
        f = tk.Frame(self, bg="white", highlightbackground="#9AA7AD", highlightthickness=1)
        items = [("#222222", "Almacén"), ("#1B998B", "Repartidor")] + \
                [(COLOR_PRIORIDAD[k], f"Prio {k}") for k in (5, 4, 3, 2, 1)] + \
                [(COLOR_CERRADA, "Cerrada")]
        for col, txt in items:
            tk.Label(f, text="■", fg=col, bg="white", font=("Helvetica", 11)).pack(side="left")
            tk.Label(f, text=txt, bg="white", fg="#222222", font=("Helvetica", 9)).pack(side="left", padx=(0, 6))
        f.place(x=8, rely=1.0, y=-8, anchor="sw")

    # ------------------------------------------------------------ API común
    def limpiar_capas(self) -> None:
        self.rutas, self.zonas, self.resaltados = [], [], set()
        self.titulo = ""

    def agregar_ruta(self, tramos, color, dash=None, ancho=4, numerar=True) -> None:
        self.rutas.append(dict(tramos=tramos, color=color, dash=dash, ancho=ancho, numerar=numerar))

    def limpiar_dinamica(self) -> None:
        for o in self._obj_moviles.values():
            o.delete()
        for p in self._obj_vivas.values():
            p.delete()
        self._obj_moviles, self._obj_vivas = {}, {}
        self.moviles, self.rutas_vivas = {}, {}
        self.entregados = set()

    def mover_movil(self, ident: str, lat: float, lon: float, color: str = "#1B998B") -> None:
        self.moviles[ident] = dict(lat=lat, lon=lon, color=color)
        o = self._obj_moviles.get(ident)
        if o is None or o.deleted:
            self._obj_moviles[ident] = Insignia(self, lat, lon, ident, relleno=color, radio=13,
                                                fuente=("Helvetica", 10, "bold"))
        else:
            o.set_position(lat, lon)

    def poner_ruta_viva(self, ident: str, coords: list, color: str) -> None:
        self.rutas_vivas[ident] = dict(coords=coords, color=color)
        p = self._obj_vivas.get(ident)
        if len(coords) < 2:
            if p is not None:
                p.delete()
                self._obj_vivas.pop(ident, None)
            return
        if p is not None and not p.deleted:
            p.set_position_list(list(coords))          # reutiliza la línea: más fluido
        else:
            p = self.set_path(list(coords), color=color, width=6)
            self.canvas.itemconfigure(p.canvas_line, arrow="last", arrowshape=(14, 16, 6))
            self._obj_vivas[ident] = p
        mv = self._obj_moviles.get(ident)
        if mv is not None:
            for it in mv.items:
                self.canvas.tag_raise(it)

    # ------------------------------------------------------------ dibujo
    def _borrar_estatico(self) -> None:
        for ins in self._insignias:
            ins.delete()
        self._insignias = []
        vivos = set(map(id, self._obj_vivas.values()))
        for p in list(self.canvas_path_list):
            if id(p) not in vivos:
                p.delete()
        for poly in list(self.canvas_polygon_list):
            poly.delete()

    def _ins(self, *a, **k) -> Insignia:
        o = Insignia(self, *a, **k)
        self._insignias.append(o)
        return o

    def _path(self, pts, color, ancho, dash=None, flecha=False, comando=None, data=None):
        if len(pts) < 2:
            return None
        p = self.set_path(list(pts), color=color, width=ancho, command=comando, data=data)
        opciones = {}
        if dash:
            opciones["dash"] = dash
        if flecha:
            opciones.update(arrow="last", arrowshape=(14, 16, 6))
        if opciones and p.canvas_line:
            self.canvas.itemconfigure(p.canvas_line, **opciones)
        return p

    def redibujar(self) -> None:
        self._borrar_estatico()
        geo = self.geo
        # zonas (divide y vencerás): contorno discontinuo
        for z in self.zonas:
            lat0, lat1, lon0, lon1 = z["caja"]
            poly = self.set_polygon([(lat1, lon0), (lat1, lon1), (lat0, lon1), (lat0, lon0)],
                                    outline_color=z["borde"], fill_color=None, border_width=3)
            if poly.canvas_polygon:
                self.canvas.itemconfigure(poly.canvas_polygon, dash=(10, 6))
            self._ins(lat1, lon0, z["etiqueta"], relleno=z["borde"], forma="pildora", dx=40, dy=12)
        # calles del grafo (clic = cerrar / abrir)
        for a, b, _, _ in self.grafo.calles:
            arista = frozenset((a, b))
            cerrada = arista in self.cerradas
            self._path(geo.tramo(a, b), COLOR_CERRADA if cerrada else COLOR_CALLE,
                       7 if cerrada else 4, dash=(8, 5) if cerrada else None,
                       comando=self._clic_calle, data=arista)
            if cerrada:
                self._ins(*geo.punto(a, b, 0.5), "✕", relleno=COLOR_CERRADA, radio=9,
                          comando=lambda _o, ar=arista: self._avisar_calle(ar))
        # rutas calculadas
        for r in self.rutas:
            parada = 0
            for tramo in r["tramos"]:
                if len(tramo) < 2:
                    continue
                self._path(geo.camino(tramo), r["color"], r["ancho"] + 2, dash=r["dash"], flecha=True)
                parada += 1
                if r["numerar"]:
                    self._ins(*geo.pos[tramo[-1]], str(parada), relleno=r["color"], radio=9, dy=-18)
        # lugares
        for n in LUGARES:
            resaltado = n in self.resaltados
            self._ins(*geo.pos[n], relleno="#FFD23F" if resaltado else "#4A4A4A",
                      borde="#222" if resaltado else "white", radio=7 if resaltado else 4,
                      etiqueta=n if (self.mostrar_nombres or resaltado) else None,
                      comando=lambda _o, nombre=n: self._avisar_lugar(nombre))
        # almacén y repartidores
        self._ins(*geo.pos[ALMACEN], "A", relleno="#222222", forma="cuadrado", radio=10,
                  comando=lambda _o: self._avisar_lugar(ALMACEN))
        for r in self.repartidores:
            if r.id not in self.moviles:
                self._ins(*geo.pos[r.ubicacion], r.id, relleno="#1B998B", radio=11, dy=20)
        # pedidos (píldoras de color según prioridad)
        conteo: dict[str, int] = {}
        for p in self.pedidos:
            k = conteo.get(p.lugar, 0)
            conteo[p.lugar] = k + 1
            col = "#9E9E9E" if p.id in self.entregados else COLOR_PRIORIDAD.get(p.prioridad, "#666")
            texto = ("✓" + p.id) if p.id in self.entregados else p.id
            self._ins(*geo.pos[p.lugar], texto, relleno=col, forma="pildora", dx=30 + 38 * k, dy=8,
                      fuente=("Helvetica", 8, "bold"))
        # vehículos en movimiento (simulación)
        for ident, mv in self.moviles.items():
            o = self._obj_moviles.get(ident)
            if o is not None:
                o.delete()
            self._obj_moviles[ident] = Insignia(self, mv["lat"], mv["lon"], ident, relleno=mv["color"],
                                                radio=13, fuente=("Helvetica", 10, "bold"))
        for p in self._obj_vivas.values():        # rutas en vivo sobre las calles
            if p.canvas_line:
                self.canvas.tag_raise(p.canvas_line)
        # título
        if self.titulo:
            self.lbl_titulo.configure(text=self.titulo)
            self.lbl_titulo.place(x=60, y=10)
        else:
            self.lbl_titulo.place_forget()
        self.manage_z_order()

    # ------------------------------------------------------------ clics
    def _clic_calle(self, path) -> None:
        self.ultimo_clic_objeto = time.time()
        self._avisar_calle(path.data)

    def _avisar_calle(self, arista) -> None:
        self.ultimo_clic_objeto = time.time()
        if self.on_click_calle:
            self.on_click_calle(arista)

    def _avisar_lugar(self, nombre: str) -> None:
        self.ultimo_clic_objeto = time.time()
        if self.on_click_lugar:
            self.on_click_lugar(nombre)

    def _clic_mapa(self, coords) -> None:
        # un clic sobre una calle o un lugar también llega aquí: se ignora
        if time.time() - self.ultimo_clic_objeto < 0.5:
            return
        nombre = self.geo.lugar_cercano(*coords)
        if nombre and self.on_click_lugar:
            self.on_click_lugar(nombre)
