"""
gui/app.py
----------
Interfaz gráfica (Tkinter) del Sistema de Gestión de Rutas Óptimas en Cusco.

A la derecha está el mapa REAL de Cusco (OpenStreetMap, gui/mapa_real.py) y a
la izquierda un panel con pestañas:
  1. Pedidos        → ingreso, ordenación y búsqueda
  2. Voraz          → asignación al más cercano y ruta del vecino más cercano
  3. Divide y V.    → segmentación de la ciudad en zonas
  4. P. Dinámica    → mochila 0/1 y ruta óptima (Held-Karp)
  5. Backtracking   → todas las rutas evitando calles cerradas
  6. Comparación    → experimentos de tiempo y calidad
  7. En vivo        → simulación del reparto en tiempo real con cierres de calles

Si la librería tkintermapview no está instalada se usa el mapa simplificado
(gui/mapa.py) y todo lo demás funciona igual.
"""
from __future__ import annotations

import queue
import random
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import osm
from algoritmos import backtracking as bt
from algoritmos import busqueda, divide_venceras as dyv, ordenacion, voraz
from algoritmos import prog_dinamica as pd
from comparacion import comparar_mochila, comparar_rutas
from datos import ALMACEN, LUGARES, pedidos_aleatorios, pedidos_ejemplo, repartidores_ejemplo
from grafo import Grafo
from gui.mapa import PALETA_RUTAS, PALETA_ZONAS, MapaCanvas
from modelos import Pedido
from simulacion import Simulacion, planes_dyv, planes_voraz

try:
    from gui.mapa_real import SERVIDORES_MAPA, MapaReal
    MAPA_REAL = True
except ImportError:                     # sin tkintermapview → mapa simplificado
    MAPA_REAL = False

SECTORES = sorted({l.sector for l in LUGARES.values()})
PLANES = {"Divide y vencerás + Held-Karp": planes_dyv, "Voraz (más cercano)": planes_voraz}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Gestión de Rutas Óptimas en Cusco — Programación III")
        self.geometry("1480x860")
        self.minsize(1150, 720)

        self.datos_osm = osm.cargar()
        self.grafo = Grafo()
        self.dist_almacen, _ = self.grafo.dijkstra(ALMACEN)
        self.pedidos: list[Pedido] = []
        self.repartidores = repartidores_ejemplo()
        self._cargar_pedidos(pedidos_ejemplo())
        self.sim: Simulacion | None = None
        self._sim_activa = False
        self._sim_job = None
        self._descargando = False

        self._estilos()
        panel = ttk.Frame(self, padding=6)
        panel.pack(side="left", fill="y")
        derecha = ttk.Frame(self)
        derecha.pack(side="right", fill="both", expand=True)
        barra = ttk.Frame(derecha, padding=(6, 4))
        barra.pack(fill="x")
        Mapa = MapaReal if MAPA_REAL else MapaCanvas
        self.mapa = Mapa(derecha, self.grafo, self.datos_osm)
        self.mapa.pack(fill="both", expand=True)
        self.mapa.pedidos = self.pedidos
        self.mapa.repartidores = self.repartidores
        self.mapa.on_click_lugar = self._click_lugar
        self.mapa.on_click_calle = self._click_calle
        self._barra_mapa(barra)

        self.tabs = ttk.Notebook(panel, width=520)
        self.tabs.pack(fill="both", expand=True)
        self._tab_pedidos()
        self._tab_voraz()
        self._tab_dyv()
        self._tab_pd()
        self._tab_bt()
        self._tab_comparacion()
        self._tab_vivo()
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self._cambio_pestana())

        self.estado = tk.StringVar(value="Listo. Haga clic en un lugar del mapa para usarlo en el formulario.")
        ttk.Label(panel, textvariable=self.estado, wraplength=520, foreground="#444").pack(fill="x", pady=4)
        self.after(300, self.mapa.redibujar)
        if MAPA_REAL and self.datos_osm is None:
            self.after(800, lambda: self._descargar_osm(silencioso=True))

    # ================================================================ barra del mapa
    def _barra_mapa(self, barra):
        b = ttk.Frame(barra)
        b.pack(fill="x")
        b2 = ttk.Frame(barra)
        b2.pack(fill="x", pady=(3, 0))
        if MAPA_REAL:
            ttk.Label(b, text="Mapa:").pack(side="left")
            self.var_fondo = tk.StringVar(value=list(SERVIDORES_MAPA)[0])
            cb = ttk.Combobox(b, textvariable=self.var_fondo, values=list(SERVIDORES_MAPA),
                              width=21, state="readonly")
            cb.pack(side="left", padx=4)
            cb.bind("<<ComboboxSelected>>", lambda e: self.mapa.cambiar_fondo(self.var_fondo.get()))
        else:
            ttk.Label(b, text="Mapa simplificado (pip install tkintermapview para el mapa real)",
                      foreground="#B71C1C").pack(side="left")
        self.var_nombres = tk.BooleanVar(value=not MAPA_REAL)
        ttk.Checkbutton(b, text="Nombres", variable=self.var_nombres,
                        command=self._toggle_nombres).pack(side="left", padx=6)
        self.var_osm = tk.BooleanVar(value=False)
        ttk.Checkbutton(b, text="Distancias reales (OSM)", variable=self.var_osm,
                        command=self._aplicar_distancias).pack(side="left")
        ttk.Button(b, text="Centrar", command=self.mapa.centrar).pack(side="left", padx=6)
        ttk.Button(b2, text="Actualizar calles OSM", command=self._descargar_osm).pack(side="left")
        self.lbl_osm = ttk.Label(b2, text="", foreground="#00606A")
        self.lbl_osm.pack(side="left", padx=8)
        self._refrescar_lbl_osm()

    def _refrescar_lbl_osm(self):
        if self.datos_osm:
            ok = sum(1 for c in self.datos_osm["calles"] if c.get("geometria"))
            self.lbl_osm.configure(text=f"Calles reales OSM: {ok}/46 ({self.datos_osm['fecha']})")
        else:
            self.lbl_osm.configure(text="Calles: trazo recto (sin datos OSM)")

    def _toggle_nombres(self):
        self.mapa.mostrar_nombres = self.var_nombres.get()
        self.mapa.redibujar()

    def _aplicar_distancias(self):
        if self.var_osm.get() and not self.datos_osm:
            self.var_osm.set(False)
            messagebox.showinfo("Sin datos", "Primero pulse 'Actualizar calles OSM' (requiere internet).")
            return
        self._sim_reiniciar()
        self.grafo = Grafo(osm.longitudes(self.datos_osm) if self.var_osm.get() else None)
        self.mapa.grafo = self.grafo
        self.dist_almacen, _ = self.grafo.dijkstra(ALMACEN)
        for p in self.pedidos:
            p.distancia = self.dist_almacen[p.lugar]
        self._mostrar_pedidos(self.pedidos)
        self._limpiar_mapa()
        self.estado.set("Distancias: longitudes REALES medidas sobre OpenStreetMap." if self.var_osm.get()
                        else "Distancias: estimación Haversine × 1.25 (la del informe).")

    def _descargar_osm(self, silencioso: bool = False):
        if self._descargando:
            return
        self._descargando = True
        cola: queue.Queue = queue.Queue()

        def trabajo():
            try:
                cola.put(("ok", osm.generar_cache(avisar=lambda t: cola.put(("msg", t)))))
            except Exception as ex:                                   # noqa: BLE001
                cola.put(("error", str(ex)))

        def revisar():
            try:
                while True:
                    tipo, val = cola.get_nowait()
                    if tipo == "msg":
                        self.estado.set(val)
                    elif tipo == "ok":
                        self.datos_osm = val
                        self.mapa.usar_osm(val)
                        self._refrescar_lbl_osm()
                        self._descargando = False
                        self.estado.set("Calles reales de OpenStreetMap cargadas.")
                        return
                    else:
                        self._descargando = False
                        self.estado.set("No se pudieron descargar las calles de OSM (¿sin internet?).")
                        if not silencioso:
                            messagebox.showerror("OpenStreetMap", val[:600])
                        return
            except queue.Empty:
                pass
            self.after(250, revisar)

        threading.Thread(target=trabajo, daemon=True).start()
        self.estado.set("Descargando calles reales de OpenStreetMap…")
        self.after(250, revisar)

    def _cambio_pestana(self):
        self._sim_pausar()
        self.mapa.limpiar_dinamica()
        self._limpiar_mapa()

    # ================================================================ utilidades
    def _estilos(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("Treeview", rowheight=22)
        s.configure("Accent.TButton", font=("Helvetica", 10, "bold"))

    def _cargar_pedidos(self, nuevos: list[Pedido]):
        for p in nuevos:
            p.distancia = self.dist_almacen[p.lugar]
        self.pedidos[:] = nuevos

    def _tabla(self, padre, columnas, anchos, alto=8):
        frame = ttk.Frame(padre)
        tv = ttk.Treeview(frame, columns=columnas, show="headings", height=alto)
        for c, w in zip(columnas, anchos):
            tv.heading(c, text=c)
            tv.column(c, width=w, anchor="center")
        sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return frame, tv

    @staticmethod
    def _llenar(tv, filas):
        tv.delete(*tv.get_children())
        for f in filas:
            tv.insert("", "end", values=f)

    def _texto(self, padre, alto=8):
        t = tk.Text(padre, height=alto, wrap="word", font=("Courier", 10), bg="#FAFAFA",
                    fg="#1F2A30", insertbackground="#1F2A30")   # legible también en modo oscuro
        return t

    @staticmethod
    def _escribir(t: tk.Text, contenido: str):
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", contenido)
        t.configure(state="disabled")

    def _limpiar_mapa(self):
        self.mapa.limpiar_capas()
        self.mapa.pedidos = self.pedidos
        self.mapa.redibujar()

    def _tramos_de_orden(self, lugares, orden, caminos):
        return [caminos[(orden[i], orden[i + 1])] for i in range(len(orden) - 1)]

    def _click_lugar(self, nombre):
        self.var_lugar.set(nombre)
        if hasattr(self, "var_origen") and self.tabs.index("current") == 4:
            # En la pestaña de backtracking: 1er clic origen, 2do destino
            if self._bt_turno == 0:
                self.var_origen.set(nombre)
            else:
                self.var_destino.set(nombre)
            self._bt_turno ^= 1
        self.mapa.resaltados = {nombre}
        self.mapa.redibujar()
        self.estado.set(f"Lugar seleccionado: {nombre} ({LUGARES[nombre].sector})")

    def _click_calle(self, arista):
        pestana = self.tabs.index("current")
        if pestana == 6:
            self._sim_clic_calle(arista)
            return
        if pestana != 4:
            a, b = tuple(arista)
            real = self.mapa.geo.nombre_real.get(arista)
            self.estado.set(f"Calle: {self.grafo.calle_entre(a, b)} ({a} – {b}), "
                            f"{self.grafo.peso[arista]:,.0f} m" + (f"  ·  en OSM: {real}" if real else "")
                            + "  —  para cerrarla use la pestaña 5 o 7.")
            return
        if arista in self.mapa.cerradas:
            self.mapa.cerradas.remove(arista)
        else:
            self.mapa.cerradas.add(arista)
        self._refrescar_cerradas()
        self.mapa.redibujar()

    # ================================================================ 1. PEDIDOS
    def _tab_pedidos(self):
        f = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(f, text="1. Pedidos")

        cols = ("ID", "Cliente", "Lugar", "Sector", "Prio", "Peso", "S/.", "Dist (m)")
        fr, self.tv_ped = self._tabla(f, cols, (45, 95, 120, 90, 35, 40, 40, 60), alto=11)
        fr.pack(fill="both", expand=True)

        # --- formulario de ingreso
        lf = ttk.LabelFrame(f, text="Nuevo pedido (clic en el mapa para elegir el lugar)", padding=6)
        lf.pack(fill="x", pady=4)
        self.var_cliente = tk.StringVar(value="Nuevo cliente")
        self.var_lugar = tk.StringVar(value="San Blas")
        self.var_prio = tk.IntVar(value=3)
        self.var_peso = tk.IntVar(value=2)
        self.var_valor = tk.IntVar(value=30)
        ttk.Label(lf, text="Cliente").grid(row=0, column=0, sticky="w")
        ttk.Entry(lf, textvariable=self.var_cliente, width=16).grid(row=0, column=1)
        ttk.Label(lf, text="Lugar").grid(row=0, column=2, sticky="w", padx=(6, 0))
        ttk.Combobox(lf, textvariable=self.var_lugar, values=list(LUGARES), width=24,
                     state="readonly").grid(row=0, column=3, columnspan=3)
        ttk.Label(lf, text="Prioridad").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(lf, from_=1, to=5, textvariable=self.var_prio, width=5).grid(row=1, column=1, sticky="w")
        ttk.Label(lf, text="Peso kg").grid(row=1, column=2, sticky="w", padx=(6, 0))
        ttk.Spinbox(lf, from_=1, to=50, textvariable=self.var_peso, width=5).grid(row=1, column=3, sticky="w")
        ttk.Label(lf, text="Valor S/.").grid(row=1, column=4, sticky="w")
        ttk.Spinbox(lf, from_=1, to=999, textvariable=self.var_valor, width=6).grid(row=1, column=5, sticky="w")
        bf = ttk.Frame(lf)
        bf.grid(row=2, column=0, columnspan=6, pady=(6, 0), sticky="w")
        ttk.Button(bf, text="Agregar", command=self._agregar_pedido).pack(side="left")
        ttk.Button(bf, text="Eliminar seleccionado", command=self._eliminar_pedido).pack(side="left", padx=4)
        ttk.Button(bf, text="Datos de ejemplo", command=self._restaurar).pack(side="left")
        ttk.Button(bf, text="+10 aleatorios", command=self._aleatorios).pack(side="left", padx=4)

        # --- ordenación
        lo = ttk.LabelFrame(f, text="Ordenación", padding=6)
        lo.pack(fill="x", pady=4)
        self.var_criterio = tk.StringVar(value=list(ordenacion.CRITERIOS)[0])
        self.var_alg = tk.StringVar(value="Merge Sort")
        ttk.Combobox(lo, textvariable=self.var_criterio, values=list(ordenacion.CRITERIOS),
                     width=30, state="readonly").pack(side="left")
        ttk.Combobox(lo, textvariable=self.var_alg, values=list(ordenacion.ALGORITMOS),
                     width=11, state="readonly").pack(side="left", padx=4)
        ttk.Button(lo, text="Ordenar", command=self._ordenar, style="Accent.TButton").pack(side="left")

        # --- búsqueda
        lb = ttk.LabelFrame(f, text="Búsqueda", padding=6)
        lb.pack(fill="x", pady=4)
        self.var_id = tk.StringVar(value="P007")
        self.var_sector = tk.StringVar(value=SECTORES[0])
        ttk.Label(lb, text="ID").grid(row=0, column=0)
        ttk.Entry(lb, textvariable=self.var_id, width=8).grid(row=0, column=1)
        ttk.Button(lb, text="Búsqueda binaria", command=self._buscar_id).grid(row=0, column=2, padx=4)
        ttk.Label(lb, text="Sector").grid(row=0, column=3)
        ttk.Combobox(lb, textvariable=self.var_sector, values=SECTORES, width=15,
                     state="readonly").grid(row=0, column=4)
        ttk.Button(lb, text="Índice hash", command=self._buscar_sector).grid(row=0, column=5, padx=4)
        self.lbl_res = ttk.Label(f, text="", wraplength=500, foreground="#1B5E20")
        self.lbl_res.pack(fill="x")
        self._mostrar_pedidos(self.pedidos)

    def _mostrar_pedidos(self, lista):
        self._llenar(self.tv_ped, [(p.id, p.cliente, p.lugar, p.sector, p.prioridad, p.peso,
                                    p.valor, f"{p.distancia:,.0f}") for p in lista])

    def _siguiente_id(self):
        n = max((int(p.id[1:]) for p in self.pedidos), default=0) + 1
        return f"P{n:03d}"

    def _agregar_pedido(self):
        try:
            lugar = self.var_lugar.get()
            p = Pedido(self._siguiente_id(), self.var_cliente.get().strip() or "Cliente", lugar,
                       LUGARES[lugar].sector, int(self.var_prio.get()), int(self.var_peso.get()),
                       int(self.var_valor.get()), self.dist_almacen[lugar])
            if not 1 <= p.prioridad <= 5 or p.peso <= 0 or p.valor <= 0:
                raise ValueError
        except (ValueError, KeyError, tk.TclError):
            messagebox.showerror("Dato inválido", "Revise prioridad (1-5), peso y valor (> 0).")
            return
        self.pedidos.append(p)
        self._mostrar_pedidos(self.pedidos)
        self.mapa.redibujar()
        self.estado.set(f"Pedido {p.id} agregado en {p.lugar}.")

    def _eliminar_pedido(self):
        sel = self.tv_ped.selection()
        if not sel:
            return
        ids = {self.tv_ped.item(s)["values"][0] for s in sel}
        self.pedidos[:] = [p for p in self.pedidos if p.id not in ids]
        self._mostrar_pedidos(self.pedidos)
        self.mapa.redibujar()

    def _restaurar(self):
        self._cargar_pedidos(pedidos_ejemplo())
        self._mostrar_pedidos(self.pedidos)
        self._limpiar_mapa()

    def _aleatorios(self):
        n0 = int(self._siguiente_id()[1:])
        nuevos = pedidos_aleatorios(10, semilla=int(time.time()), inicio=n0)
        for p in nuevos:
            p.distancia = self.dist_almacen[p.lugar]
        self.pedidos.extend(nuevos)
        self._mostrar_pedidos(self.pedidos)
        self.mapa.redibujar()

    def _ordenar(self):
        clave = ordenacion.CRITERIOS[self.var_criterio.get()]
        alg = ordenacion.ALGORITMOS[self.var_alg.get()]
        t0 = time.perf_counter()
        res = alg(self.pedidos, clave)
        ms = (time.perf_counter() - t0) * 1000
        self.pedidos[:] = res
        self._mostrar_pedidos(self.pedidos)
        self.lbl_res.configure(text=f"{self.var_alg.get()} ordenó {len(res)} pedidos por "
                                    f"'{self.var_criterio.get()}' en {ms:.3f} ms  —  O(n log n)")

    def _buscar_id(self):
        ordenados = busqueda.preparar_busqueda(self.pedidos)
        p, comp = busqueda.busqueda_binaria(ordenados, self.var_id.get().strip().upper())
        _, comp_sec = busqueda.busqueda_secuencial(self.pedidos, self.var_id.get().strip().upper())
        if p is None:
            self.lbl_res.configure(text=f"No existe el pedido {self.var_id.get()} "
                                        f"({comp} comparaciones binaria / {comp_sec} secuencial).")
            return
        self.lbl_res.configure(text=f"Encontrado {p.id}: {p.cliente} en {p.lugar}, prioridad "
                                    f"{p.prioridad}. Binaria: {comp} comparaciones; "
                                    f"secuencial: {comp_sec}.")
        for item in self.tv_ped.get_children():
            if self.tv_ped.item(item)["values"][0] == p.id:
                self.tv_ped.selection_set(item)
                self.tv_ped.see(item)
        self.mapa.resaltados = {p.lugar}
        self.mapa.redibujar()

    def _buscar_sector(self):
        indice = busqueda.IndiceSector(self.pedidos)
        res = indice.buscar(self.var_sector.get())
        self._mostrar_pedidos(res)
        self.lbl_res.configure(text=f"Sector {self.var_sector.get()}: {len(res)} pedidos "
                                    f"(consulta O(1) en el índice hash). Pulse 'Ordenar' para ver todos.")
        self.mapa.resaltados = {p.lugar for p in res}
        self.mapa.redibujar()

    # ================================================================ 2. VORAZ
    def _tab_voraz(self):
        f = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(f, text="2. Voraz")
        ttk.Label(f, wraplength=500, text=(
            "Greedy: en cada paso se toma la mejor opción LOCAL sin mirar el panorama global.\n"
            "• Asignación: cada pedido (urgentes primero) va al repartidor más cercano con capacidad.\n"
            "• Ruta: el repartidor siempre visita el punto pendiente más próximo.")).pack(fill="x")
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=6)
        ttk.Button(bf, text="Asignar pedidos al más cercano", style="Accent.TButton",
                   command=self._voraz_asignar).pack(side="left")
        ttk.Button(bf, text="Rutas (vecino más cercano)", command=self._voraz_rutas).pack(side="left", padx=4)
        fr, self.tv_rep = self._tabla(f, ("Repartidor", "Vehículo", "Base", "Carga", "Pedidos"),
                                      (70, 70, 140, 60, 160), alto=4)
        fr.pack(fill="x")
        self.txt_voraz = self._texto(f, 22)
        self.txt_voraz.pack(fill="both", expand=True, pady=4)

    def _voraz_asignar(self):
        res = voraz.asignar_mas_cercano(self.pedidos, self.repartidores, self.grafo)
        self._asignacion = res["asignacion"]
        self._llenar(self.tv_rep, [(r.id, r.vehiculo, r.ubicacion, f"{r.carga}/{r.capacidad} kg",
                                    ", ".join(r.pedidos)) for r in self.repartidores])
        txt = "Decisiones voraces (orden de prioridad):\n" + "\n".join(res["registro"])
        if res["sin_asignar"]:
            txt += f"\n\nSin asignar por capacidad: {[p.id for p in res['sin_asignar']]}"
        self._escribir(self.txt_voraz, txt)
        self._limpiar_mapa()
        for k, r in enumerate(self.repartidores):
            tramos = [self.grafo.camino_minimo(r.ubicacion, p.lugar)[1] for p in self._asignacion[r.id]]
            self.mapa.agregar_ruta(tramos, PALETA_RUTAS[k], dash=(3, 3), ancho=2, numerar=False)
        self.mapa.titulo = "Voraz: asignación al repartidor más cercano"
        self.mapa.redibujar()

    def _voraz_rutas(self):
        if not hasattr(self, "_asignacion"):
            self._voraz_asignar()
        self._limpiar_mapa()
        lineas, total = [], 0.0
        for k, r in enumerate(self.repartidores):
            peds = self._asignacion.get(r.id, [])
            if not peds:
                continue
            lugares = [r.ubicacion] + [p.lugar for p in peds]
            t0 = time.perf_counter()
            D, caminos = self.grafo.matriz_distancias(lugares)
            orden, costo = voraz.ruta_vecino_mas_cercano(D, 0)
            ms = (time.perf_counter() - t0) * 1000
            total += costo
            self.mapa.agregar_ruta(self._tramos_de_orden(lugares, orden, caminos), PALETA_RUTAS[k])
            secuencia = " → ".join(peds[i - 1].id for i in orden[1:])
            lineas.append(f"{r.id} ({r.ubicacion}): {secuencia}\n   distancia {costo:,.0f} m   [{ms:.2f} ms]")
        self._escribir(self.txt_voraz, "Rutas del vecino más cercano  —  O(n²) por repartidor\n\n" +
                       "\n".join(lineas) + f"\n\nDistancia total: {total:,.0f} m")
        self.mapa.titulo = "Voraz: ruta del vecino más cercano"
        self.mapa.redibujar()

    # ================================================================ 3. DIVIDE Y VENCERÁS
    def _tab_dyv(self):
        f = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(f, text="3. Divide y V.")
        ttk.Label(f, wraplength=500, text=(
            "La ciudad se divide recursivamente por la mediana (alternando cortes verticales y "
            "horizontales) hasta tener una zona por repartidor. Cada repartidor resuelve la ruta "
            "óptima SOLO de su zona (Held-Karp), y luego se combinan los resultados.")).pack(fill="x")
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=6)
        ttk.Label(bf, text="Zonas (repartidores):").pack(side="left")
        self.var_zonas = tk.IntVar(value=3)
        ttk.Spinbox(bf, from_=1, to=6, textvariable=self.var_zonas, width=4).pack(side="left", padx=4)
        ttk.Button(bf, text="Dividir y resolver", style="Accent.TButton",
                   command=self._dyv).pack(side="left")
        self.txt_dyv = self._texto(f, 30)
        self.txt_dyv.pack(fill="both", expand=True)

    def _dyv(self):
        from modelos import Repartidor
        k = max(1, min(6, int(self.var_zonas.get())))
        bases = ["Plaza de Armas", "UNSAAC (Av. de la Cultura)", "Terminal Terrestre",
                 "Plaza de Santiago", "Plaza San Sebastián", "San Blas"]
        reps = self.repartidores[:k] + [Repartidor(f"R{i + 1}", f"Moto {i + 1}", "Moto", 20, bases[i])
                                        for i in range(len(self.repartidores), k)]
        t0 = time.perf_counter()
        res = dyv.resolver_zonas(self.pedidos, reps, self.grafo)
        ms = (time.perf_counter() - t0) * 1000
        self._limpiar_mapa()
        lineas = []
        for i, z in enumerate(res["zonas"]):
            col = PALETA_RUTAS[i % len(PALETA_RUTAS)]
            r = z.get("repartidor")
            self.mapa.zonas.append(dict(caja=z["caja"], color=PALETA_ZONAS[i % 6], borde=col,
                                        etiqueta=f"Zona {i + 1}" + (f" · {r.id}" if r else "")))
            if r is None:
                continue
            self.mapa.agregar_ruta(z["tramos"], col)
            sec = " → ".join(p.id for p in z["orden_pedidos"])
            lineas.append(f"Zona {i + 1} → {r.id} desde {r.ubicacion}\n   pedidos: {len(z['pedidos'])}"
                          f"   método: {z['metodo']}\n   ruta: {sec}\n   distancia: {z['costo']:,.0f} m")
        self._escribir(self.txt_dyv, "\n\n".join(lineas) +
                       f"\n\nCOMBINAR:\n  distancia total  = {res['total']:,.0f} m"
                       f"\n  zona más larga   = {res['maxima']:,.0f} m (tiempo de la operación)"
                       f"\n  tiempo de cálculo = {ms:.1f} ms")
        self.mapa.titulo = f"Divide y vencerás: {k} zonas"
        self.mapa.redibujar()

    # ================================================================ 4. PROGRAMACIÓN DINÁMICA
    def _tab_pd(self):
        f = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(f, text="4. P. Dinámica")
        ttk.Label(f, wraplength=500, text=(
            "Mochila 0/1: elegir qué pedidos cargar para MAXIMIZAR el valor sin superar la capacidad.\n"
            "Held-Karp: ruta ÓPTIMA para visitar los pedidos cargados, guardando estados (conjunto, último)."
        )).pack(fill="x")
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=6)
        ttk.Label(bf, text="Capacidad (kg):").pack(side="left")
        self.var_cap = tk.IntVar(value=20)
        ttk.Spinbox(bf, from_=1, to=500, textvariable=self.var_cap, width=6).pack(side="left", padx=4)
        ttk.Button(bf, text="1) Cargar vehículo", style="Accent.TButton",
                   command=self._pd_mochila).pack(side="left")
        ttk.Button(bf, text="2) Ruta óptima", command=self._pd_ruta).pack(side="left", padx=4)
        fr, self.tv_moch = self._tabla(f, ("Método", "Valor S/.", "Peso kg", "Pedidos", "ms"),
                                       (110, 60, 60, 210, 50), alto=2)
        fr.pack(fill="x")
        self.txt_pd = self._texto(f, 24)
        self.txt_pd.pack(fill="both", expand=True, pady=4)

    def _pd_mochila(self):
        cap = int(self.var_cap.get())
        t0 = time.perf_counter()
        sel, valor, peso, dp = pd.mochila_01(self.pedidos, cap)
        t_dp = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        gsel, gval, gpeso = voraz.mochila_voraz(self.pedidos, cap)
        t_g = (time.perf_counter() - t0) * 1000
        self._carga = sel
        self._llenar(self.tv_moch, [
            ("PD (óptimo)", valor, peso, ", ".join(p.id for p in sel), f"{t_dp:.2f}"),
            ("Voraz v/p", gval, gpeso, ", ".join(p.id for p in gsel), f"{t_g:.2f}")])
        n = len(self.pedidos)
        txt = (f"Tabla dp de tamaño ({n}+1) x ({cap}+1) = {(n + 1) * (cap + 1):,} estados  →  O(n·W)\n"
               f"dp[n][W] = {dp[n][cap]}  (valor máximo)\n\n")
        txt += "Última columna de la tabla (w = W):\n"
        for i in range(n + 1):
            etiqueta = "  (sin pedidos)" if i == 0 else f"  + {self.pedidos[i - 1].id} " \
                       f"(p={self.pedidos[i - 1].peso}, v={self.pedidos[i - 1].valor})"
            txt += f"dp[{i:>2}][{cap}] = {dp[i][cap]:>4}{etiqueta}\n"
        if gval < valor:
            txt += f"\nEl voraz pierde S/. {valor - gval}: elegir por valor/peso no garantiza el óptimo en 0/1."
        else:
            txt += "\nEn este caso el voraz coincide con el óptimo."
        self._escribir(self.txt_pd, txt)
        self._limpiar_mapa()
        self.mapa.resaltados = {p.lugar for p in sel}
        self.mapa.titulo = f"Mochila 0/1: {len(sel)} pedidos cargados, S/. {valor}"
        self.mapa.redibujar()

    def _pd_ruta(self):
        if not getattr(self, "_carga", None):
            self._pd_mochila()
        carga = self._carga
        if len(carga) + 1 > 15:
            messagebox.showwarning("Demasiados puntos", "Held-Karp es O(n²·2ⁿ); use ≤ 14 pedidos.")
            return
        lugares = [ALMACEN] + [p.lugar for p in carga]
        D, caminos = self.grafo.matriz_distancias(lugares)
        t0 = time.perf_counter()
        orden, costo = pd.held_karp(D, 0)
        t_hk = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        orden_g, costo_g = voraz.ruta_vecino_mas_cercano(D, 0)
        t_g = (time.perf_counter() - t0) * 1000
        self._limpiar_mapa()
        self.mapa.agregar_ruta(self._tramos_de_orden(lugares, orden_g, caminos), "#9E9E9E",
                               dash=(6, 4), ancho=3, numerar=False)
        self.mapa.agregar_ruta(self._tramos_de_orden(lugares, orden, caminos), PALETA_RUTAS[0])
        n = len(lugares)
        txt = (f"Held-Karp (PD): {' → '.join(carga[i - 1].id for i in orden[1:])}\n"
               f"   distancia {costo:,.0f} m   [{t_hk:.2f} ms]   estados: 2^{n - 1}·{n - 1} = "
               f"{(2 ** (n - 1)) * (n - 1):,}\n\n"
               f"Vecino más cercano (voraz, gris): {' → '.join(carga[i - 1].id for i in orden_g[1:])}\n"
               f"   distancia {costo_g:,.0f} m   [{t_g:.2f} ms]\n\n"
               f"El voraz recorre {100 * (costo_g / costo - 1) if costo else 0:.1f}% más.")
        self._escribir(self.txt_pd, txt)
        self.mapa.titulo = "PD: ruta óptima (azul) vs voraz (gris)"
        self.mapa.redibujar()

    # ================================================================ 5. BACKTRACKING
    def _tab_bt(self):
        f = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(f, text="5. Backtracking")
        ttk.Label(f, wraplength=500, text=(
            "Encuentra TODAS las rutas simples entre dos lugares evitando calles cerradas y elige la "
            "más corta. Clic en un lugar: 1º origen, 2º destino. Clic en una calle: cerrarla/abrirla."
        )).pack(fill="x")
        g = ttk.Frame(f)
        g.pack(fill="x", pady=4)
        self.var_origen = tk.StringVar(value="San Blas")
        self.var_destino = tk.StringVar(value="Plaza Túpac Amaru")
        self._bt_turno = 0
        ttk.Label(g, text="Origen").grid(row=0, column=0, sticky="w")
        ttk.Combobox(g, textvariable=self.var_origen, values=list(LUGARES), width=26,
                     state="readonly").grid(row=0, column=1)
        ttk.Label(g, text="Destino").grid(row=1, column=0, sticky="w")
        ttk.Combobox(g, textvariable=self.var_destino, values=list(LUGARES), width=26,
                     state="readonly").grid(row=1, column=1)
        ttk.Button(g, text="Cerrar calles de ejemplo", command=self._bt_ejemplo).grid(row=0, column=2, padx=4)
        ttk.Button(g, text="Abrir todas", command=self._bt_abrir).grid(row=1, column=2, padx=4)
        self.lbl_cerradas = ttk.Label(f, text="Calles cerradas: ninguna", wraplength=500,
                                      foreground="#B71C1C")
        self.lbl_cerradas.pack(fill="x")
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=4)
        ttk.Button(bf, text="Buscar todas las rutas", style="Accent.TButton",
                   command=self._bt_buscar).pack(side="left")
        ttk.Button(bf, text="Solo la mejor (con poda)", command=self._bt_poda).pack(side="left", padx=4)
        self.lbl_bt = ttk.Label(f, text="", wraplength=500)
        self.lbl_bt.pack(fill="x")
        fr, self.tv_bt = self._tabla(f, ("#", "Distancia (m)", "Lugares", "Recorrido"),
                                     (40, 80, 55, 330), alto=14)
        fr.pack(fill="both", expand=True)
        self.tv_bt.bind("<<TreeviewSelect>>", self._bt_ver_ruta)

    def _refrescar_cerradas(self):
        if not self.mapa.cerradas:
            self.lbl_cerradas.configure(text="Calles cerradas: ninguna")
            return
        nombres = [self.grafo.calle_entre(*tuple(a)) for a in self.mapa.cerradas]
        self.lbl_cerradas.configure(text="Calles cerradas por mantenimiento: " + "; ".join(nombres))

    def _bt_ejemplo(self):
        self.mapa.cerradas = {frozenset(("San Blas", "Av. Tullumayo")),
                              frozenset(("Limacpampa", "UNSAAC (Av. de la Cultura)")),
                              frozenset(("Av. El Sol (Correo)", "Estación Wanchaq"))}
        self._refrescar_cerradas()
        self.mapa.redibujar()

    def _bt_abrir(self):
        self.mapa.cerradas = set()
        self._refrescar_cerradas()
        self.mapa.redibujar()

    def _bt_buscar(self):
        o, d = self.var_origen.get(), self.var_destino.get()
        if o == d:
            messagebox.showinfo("Ruta", "Origen y destino son iguales.")
            return
        t0 = time.perf_counter()
        res = bt.todas_las_rutas(self.grafo, o, d, self.mapa.cerradas)
        ms = (time.perf_counter() - t0) * 1000
        self._bt_rutas = res["rutas"]
        self._llenar(self.tv_bt, [(i + 1, f"{dist:,.0f}", len(cam), " → ".join(cam))
                                  for i, (dist, cam) in enumerate(res["rutas"][:300])])
        if not res["rutas"]:
            self.lbl_bt.configure(text="No existe ninguna ruta con esas calles cerradas.")
            self._limpiar_mapa()
            return
        dist, cam = res["mejor"]
        self.lbl_bt.configure(text=(
            f"{len(res['rutas']):,} rutas encontradas ({res['nodos']:,} nodos del árbol de búsqueda, "
            f"{ms:.0f} ms){' [truncado]' if res['truncado'] else ''}.\n"
            f"Más corta: {dist:,.0f} m  |  más larga: {res['rutas'][-1][0]:,.0f} m"))
        self._dibujar_bt(cam, f"Backtracking: mejor de {len(res['rutas']):,} rutas")

    def _bt_poda(self):
        o, d = self.var_origen.get(), self.var_destino.get()
        t0 = time.perf_counter()
        res = bt.ruta_mas_corta_poda(self.grafo, o, d, self.mapa.cerradas)
        ms = (time.perf_counter() - t0) * 1000
        if not res["mejor"]:
            self.lbl_bt.configure(text="No existe ninguna ruta con esas calles cerradas.")
            return
        dist, cam = res["mejor"]
        self.lbl_bt.configure(text=(f"Con poda: {res['nodos']:,} nodos explorados ({ms:.1f} ms). "
                                    f"Mejor ruta: {dist:,.0f} m (la misma, explorando mucho menos)."))
        self._dibujar_bt(cam, "Backtracking con poda: ruta más corta")

    def _bt_ver_ruta(self, _e=None):
        sel = self.tv_bt.selection()
        if not sel:
            return
        i = int(self.tv_bt.item(sel[0])["values"][0]) - 1
        dist, cam = self._bt_rutas[i]
        self._dibujar_bt(cam, f"Ruta #{i + 1}: {dist:,.0f} m")

    def _dibujar_bt(self, camino, titulo):
        cerradas = self.mapa.cerradas
        self._limpiar_mapa()
        self.mapa.cerradas = cerradas
        self.mapa.agregar_ruta([camino], PALETA_RUTAS[2], ancho=5, numerar=False)
        self.mapa.resaltados = {camino[0], camino[-1]}
        self.mapa.titulo = titulo
        self.mapa.redibujar()

    # ================================================================ 6. COMPARACIÓN
    def _tab_comparacion(self):
        f = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(f, text="6. Comparación")
        ttk.Button(f, text="Ejecutar experimentos", style="Accent.TButton",
                   command=self._comparar).pack(anchor="w")
        ttk.Label(f, text="Ruta con n paradas (promedio de 5 instancias)").pack(anchor="w", pady=(6, 0))
        fr, self.tv_cmp = self._tabla(f, ("n", "Voraz (m)", "Óptimo (m)", "Exceso %",
                                          "t Voraz", "t PD", "t BT"),
                                      (30, 75, 75, 60, 65, 65, 65), alto=9)
        fr.pack(fill="x")
        ttk.Label(f, text="Mochila 0/1 (capacidad 30 kg)").pack(anchor="w", pady=(6, 0))
        fr, self.tv_cmp2 = self._tabla(f, ("n", "Valor voraz", "Valor PD", "Pérdida %",
                                           "t Voraz", "t PD"), (40, 80, 80, 70, 70, 70), alto=5)
        fr.pack(fill="x")
        self.txt_cmp = self._texto(f, 8)
        self.txt_cmp.pack(fill="both", expand=True, pady=4)
        self._escribir(self.txt_cmp, "Tiempos en milisegundos.\nPulse 'Ejecutar experimentos'.")

    def _comparar(self):
        self.config(cursor="watch")
        self.update()
        rutas = comparar_rutas(range(3, 12), limite_bt=10)
        moch = comparar_mochila()
        self.config(cursor="")
        self._llenar(self.tv_cmp, [(f["n"], f"{f['costo_voraz']:,.0f}", f"{f['costo_optimo']:,.0f}",
                                    f"{f['exceso']:.1f}", f"{f['t_voraz']:.3f}", f"{f['t_pd']:.2f}",
                                    "-" if f["t_bt"] is None else f"{f['t_bt']:.2f}") for f in rutas])
        self._llenar(self.tv_cmp2, [(f["n"], f"{f['valor_voraz']:.1f}", f"{f['valor_pd']:.1f}",
                                     f"{f['perdida']:.2f}", f"{f['t_voraz']:.3f}", f"{f['t_pd']:.3f}")
                                    for f in moch])
        self._escribir(self.txt_cmp, (
            "Conclusión:\n"
            "• Voraz: el más rápido (O(n²)), pero su ruta puede ser bastante más larga.\n"
            "• PD (Held-Karp): siempre óptimo; su tiempo crece como n²·2ⁿ (útil hasta ~15 paradas).\n"
            "• Backtracking: también óptimo, pero crece como n! y se vuelve el más lento.\n"
            "• Mochila: el voraz se acerca mucho al óptimo, pero solo la PD lo garantiza."))

    # ================================================================ 7. EN VIVO
    def _tab_vivo(self):
        f = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(f, text="7. En vivo")
        ttk.Label(f, wraplength=500, text=(
            "Simulación del reparto en TIEMPO REAL. Los repartidores avanzan por las calles del mapa. "
            "Haga clic en una calle para CERRARLA (o reabrirla) mientras circulan: quien la iba a usar "
            "recalcula su ruta al instante (Dijkstra) y reordena sus pedidos pendientes (Held-Karp)."
        )).pack(fill="x")
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(6, 2))
        ttk.Label(bf, text="Plan inicial:").pack(side="left")
        self.var_plan = tk.StringVar(value=list(PLANES)[0])
        ttk.Combobox(bf, textvariable=self.var_plan, values=list(PLANES), width=28,
                     state="readonly").pack(side="left", padx=4)
        bf2 = ttk.Frame(f)
        bf2.pack(fill="x", pady=2)
        ttk.Button(bf2, text="▶ Iniciar / seguir", style="Accent.TButton",
                   command=self._sim_play).pack(side="left")
        ttk.Button(bf2, text="⏸ Pausa", command=self._sim_pausar).pack(side="left", padx=4)
        ttk.Button(bf2, text="⟲ Reiniciar", command=self._sim_reiniciar).pack(side="left")
        ttk.Button(bf2, text="⚠ Incidente aleatorio", command=self._sim_incidente).pack(side="left", padx=4)
        bf3 = ttk.Frame(f)
        bf3.pack(fill="x", pady=2)
        ttk.Label(bf3, text="Velocidad:").pack(side="left")
        self.var_vel = tk.DoubleVar(value=30)
        ttk.Scale(bf3, from_=5, to=120, variable=self.var_vel, length=200).pack(side="left", padx=4)
        self.lbl_vel = ttk.Label(bf3, text="× 30")
        self.lbl_vel.pack(side="left")
        self.var_vel.trace_add("write", lambda *_: self.lbl_vel.configure(
            text=f"× {self.var_vel.get():.0f}"))
        self.lbl_reloj = ttk.Label(bf3, text="08:00", font=("Helvetica", 22, "bold"),
                                   foreground="#00404A")
        self.lbl_reloj.pack(side="right")
        fr, self.tv_sim = self._tabla(f, ("Rep.", "Estado", "Entregas", "Recorrido", "Falta"),
                                      (45, 205, 60, 75, 110), alto=4)
        fr.pack(fill="x", pady=4)
        ttk.Label(f, text="Eventos (lo más reciente arriba):").pack(anchor="w")
        self.txt_sim = self._texto(f, 16)
        self.txt_sim.pack(fill="both", expand=True)
        self._escribir(self.txt_sim, "Pulse ▶ para empezar. Puede cerrar calles antes o durante el reparto.")

    def _sim_crear(self):
        reps = repartidores_ejemplo()
        planes = PLANES[self.var_plan.get()](self.grafo, self.pedidos, reps)
        self.sim = Simulacion(self.grafo, planes, self.mapa.cerradas)
        self._sim_colores = {m.rep.id: PALETA_RUTAS[k % len(PALETA_RUTAS)]
                             for k, m in enumerate(self.sim.moviles)}
        self._sim_n_eventos = 0
        self._sim_tick_n = 0
        self._escribir(self.txt_sim, "")
        self.mapa.limpiar_capas()
        self.mapa.limpiar_dinamica()
        self._sim_actualizar(rutas=True)        # primero los vehículos…
        self.mapa.titulo = f"En vivo · {self.var_plan.get()}"
        self.mapa.redibujar()                   # …así no se dibujan dos veces

    def _sim_play(self):
        if self.sim is None or self.sim.terminada():
            self._sim_crear()
        elif not self.mapa.moviles:             # se volvió a la pestaña: redibujar vehículos
            self._sim_actualizar(rutas=True)
            self.mapa.redibujar()
        self._sim_activa = True
        self._sim_t_prev = time.perf_counter()
        if self._sim_job is None:
            self._sim_job = self.after(40, self._sim_tick)

    def _sim_pausar(self):
        self._sim_activa = False
        if self._sim_job is not None:
            self.after_cancel(self._sim_job)
            self._sim_job = None

    def _sim_reiniciar(self):
        self._sim_pausar()
        self.sim = None
        if hasattr(self, "tv_sim"):
            self.mapa.limpiar_dinamica()
            self._llenar(self.tv_sim, [])
            self.lbl_reloj.configure(text="08:00")
            self._escribir(self.txt_sim, "Pulse ▶ para empezar.")
            if self.tabs.index("current") == 6:
                self._limpiar_mapa()

    def _sim_tick(self):
        self._sim_job = None
        if not self._sim_activa or self.sim is None:
            return
        ahora = time.perf_counter()
        dt = min(0.25, ahora - self._sim_t_prev)
        self._sim_t_prev = ahora
        antes = [(m.i, id(m.camino), len(m.entregados)) for m in self.sim.moviles]
        self.sim.avanzar(dt * self.var_vel.get())
        despues = [(m.i, id(m.camino), len(m.entregados)) for m in self.sim.moviles]
        self._sim_tick_n += 1
        self._sim_actualizar(rutas=antes != despues or self._sim_tick_n % 4 == 0,
                             entregas=[a[2] for a in antes] != [d[2] for d in despues])
        if self.sim.terminada():
            self._sim_activa = False
            total = sum(m.recorrido for m in self.sim.moviles)
            self.estado.set(f"Reparto terminado a las {self.sim.reloj()}: {total / 1000:.2f} km en total.")
            return
        self._sim_job = self.after(40, self._sim_tick)

    def _sim_actualizar(self, rutas: bool = True, entregas: bool = False):
        sim, geo = self.sim, self.mapa.geo
        for m in sim.moviles:
            u, v, frac = sim.posicion(m)
            lat, lon = geo.punto(u, v, frac) if u != v else geo.pos[u]
            col = self._sim_colores[m.rep.id]
            self.mapa.mover_movil(m.rep.id, lat, lon, col)
            if rutas:
                coords = [] if m.terminado else geo.resto(u, v, frac) + geo.camino(m.camino[m.i + 1:])[1:]
                self.mapa.poner_ruta_viva(m.rep.id, coords, col)
        if entregas:
            self.mapa.entregados = {p.id for m in sim.moviles for p in m.entregados}
            self.mapa.redibujar()
        self.lbl_reloj.configure(text=sim.reloj())
        filas = []
        for m in sim.moviles:
            total = len(m.entregados) + len(m.pendientes) + len(m.sin_ruta)
            if m.terminado:
                est = "Terminó ✓"
            else:
                sig = m.pendientes[0] if m.pendientes else None
                est = f"→ {sig.id} {sig.lugar}" if sig else "regresando"
            falta = sim.restante(m)
            filas.append((m.rep.id, est, f"{len(m.entregados)}/{total}", f"{m.recorrido / 1000:.2f} km",
                          f"{falta / 1000:.2f} km · {falta / m.velocidad / 60:.0f} min"))
        self._llenar(self.tv_sim, filas)
        nuevos = sim.eventos[self._sim_n_eventos:]
        if nuevos:
            self._sim_n_eventos = len(sim.eventos)
            self.txt_sim.configure(state="normal")
            for e in nuevos:
                self.txt_sim.insert("1.0", e + "\n")
            self.txt_sim.configure(state="disabled")

    def _sim_clic_calle(self, arista):
        if self.sim is None:                       # todavía no empieza: solo marca el cierre
            self.mapa.cerradas ^= {arista}
            self.mapa.redibujar()
            a, b = tuple(arista)
            self.estado.set(f"{self.grafo.calle_entre(a, b)}: "
                            f"{'cerrada' if arista in self.mapa.cerradas else 'abierta'}.")
            return
        if arista in self.sim.cerradas:
            self.sim.abrir(arista)
        else:
            self.sim.cerrar(arista)
        self.mapa.cerradas = set(self.sim.cerradas)
        self._sim_actualizar(rutas=True)
        self.mapa.redibujar()

    def _sim_incidente(self):
        if self.sim is None:
            self._sim_play()
        activos = [m for m in self.sim.moviles if not m.terminado and self.sim.aristas_pendientes(m)]
        if not activos:
            self.estado.set("No hay repartidores en ruta para generar un incidente.")
            return
        m = random.choice(activos)
        arista = random.choice(self.sim.aristas_pendientes(m))
        self.sim._log(f"INCIDENTE: obra/accidente en la ruta de {m.rep.id}")
        self._sim_clic_calle(arista)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
