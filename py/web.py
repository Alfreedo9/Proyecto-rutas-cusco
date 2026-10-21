"""
web.py
------
Puente entre la interfaz web (JavaScript + Leaflet) y el código del proyecto.

Reemplaza a gui/app.py (Tkinter): llama a los MISMOS módulos (algoritmos/,
grafo.py, simulacion.py, comparacion.py ...) y devuelve los resultados en
JSON para que el navegador los dibuje. Se ejecuta en el navegador con
Pyodide (Python compilado a WebAssembly), así que no hay servidor.
"""
from __future__ import annotations

import json
import random
import time

import osm
from algoritmos import backtracking as bt
from algoritmos import busqueda, divide_venceras as dyv, ordenacion, voraz
from algoritmos import prog_dinamica as pd
from comparacion import comparar_mochila, comparar_rutas
from datos import ALMACEN, CALLES_DEF, LUGARES, pedidos_aleatorios, pedidos_ejemplo, repartidores_ejemplo
from geometria import Geometria
from grafo import Grafo
from modelos import Pedido, Repartidor
from simulacion import Simulacion, planes_dyv, planes_voraz

PALETA_RUTAS = ["#2A78D6", "#D7263D", "#1BAF7A", "#8E44AD", "#E67E22", "#16A085"]
PALETA_ZONAS = ["#DCEBFB", "#FBE0E3", "#DDF5EA", "#EEE2F5", "#FDEBD9", "#D9F2EE"]
SECTORES = sorted({l.sector for l in LUGARES.values()})
PLANES = {"Divide y vencerás + Held-Karp": planes_dyv, "Voraz (más cercano)": planes_voraz}
CERRADAS_EJEMPLO = [("San Blas", "Av. Tullumayo"), ("Limacpampa", "UNSAAC (Av. de la Cultura)"),
                    ("Av. El Sol (Correo)", "Estación Wanchaq")]


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


def _arista(par) -> frozenset:
    return frozenset((par[0], par[1]))


def _par(arista: frozenset) -> list[str]:
    """Arista → [a, b] en el mismo orden que CALLES_DEF (clave estable para JS)."""
    for a, b, _ in CALLES_DEF:
        if frozenset((a, b)) == arista:
            return [a, b]
    return list(arista)


class Estado:
    def __init__(self) -> None:
        self.datos_osm = osm.cargar()
        self.geo = Geometria(self.datos_osm)
        self.reales = False
        self.grafo = Grafo()
        self.dist_almacen, _ = self.grafo.dijkstra(ALMACEN)
        self.repartidores = repartidores_ejemplo()
        self.pedidos: list[Pedido] = []
        self._cargar(pedidos_ejemplo())
        self.asignacion = None
        self.carga = None
        self.bt_rutas: list = []
        self.sim: Simulacion | None = None
        self.sim_n_eventos = 0
        self.colores: dict = {}

    # ------------------------------------------------------------ utilidades
    def _cargar(self, nuevos):
        for p in nuevos:
            p.distancia = self.dist_almacen[p.lugar]
        self.pedidos[:] = nuevos

    def _ped(self, p: Pedido) -> dict:
        return dict(id=p.id, cliente=p.cliente, lugar=p.lugar, sector=p.sector, prioridad=p.prioridad,
                    peso=p.peso, valor=p.valor, distancia=round(p.distancia, 1))

    def _ruta(self, tramos, color, dash=None, ancho=4, numerar=True) -> dict:
        """Misma idea que MapaReal.agregar_ruta: cada tramo es una lista de lugares."""
        segs, paradas = [], []
        for k, tramo in enumerate(tramos, start=1):
            if not tramo:
                continue
            segs.append([list(p) for p in self.geo.camino(tramo)])
            if numerar:
                paradas.append(dict(pos=list(self.geo.pos[tramo[-1]]), n=k))
        return dict(segmentos=segs, color=color, dash=dash, ancho=ancho, paradas=paradas)

    @staticmethod
    def _tramos(orden, caminos):
        return [caminos[(orden[i], orden[i + 1])] for i in range(len(orden) - 1)]

    def _capa(self, titulo="", rutas=None, zonas=None, resaltados=None) -> dict:
        return dict(titulo=titulo, rutas=rutas or [], zonas=zonas or [], resaltados=list(resaltados or []))

    # ------------------------------------------------------------ inicio
    def inicio(self) -> dict:
        calles = []
        for a, b, nombre in CALLES_DEF:
            ar = frozenset((a, b))
            calles.append(dict(a=a, b=b, nombre=nombre, metros=self.grafo.peso[ar],
                               nombre_osm=self.geo.nombre_real.get(ar, ""),
                               coords=[list(p) for p in self.geo.tramo(a, b)]))
        osm_ok = sum(1 for c in (self.datos_osm or {}).get("calles", []) if c.get("geometria"))
        return dict(
            lugares=[dict(nombre=n, sector=l.sector, pos=list(self.geo.pos[n])) for n, l in LUGARES.items()],
            calles=calles, almacen=ALMACEN, sectores=SECTORES,
            criterios=list(ordenacion.CRITERIOS), algoritmos=list(ordenacion.ALGORITMOS),
            planes=list(PLANES), cerradas_ejemplo=[list(p) for p in CERRADAS_EJEMPLO],
            osm=dict(calles=osm_ok, fecha=(self.datos_osm or {}).get("fecha", ""),
                     nodos=(self.datos_osm or {}).get("nodos_red", 0)),
            **self.estado_pedidos(),
        )

    def estado_pedidos(self) -> dict:
        self.asignacion = self.carga = None      # los resultados previos ya no valen
        return dict(pedidos=[self._ped(p) for p in self.pedidos],
                    repartidores=[dict(id=r.id, nombre=r.nombre, vehiculo=r.vehiculo, capacidad=r.capacidad,
                                       ubicacion=r.ubicacion, pos=list(self.geo.pos[r.ubicacion]))
                                  for r in self.repartidores])

    def distancias_reales(self, activar: bool) -> dict:
        self.reales = bool(activar and self.datos_osm)
        self.grafo = Grafo(osm.longitudes(self.datos_osm) if self.reales else None)
        self.dist_almacen, _ = self.grafo.dijkstra(ALMACEN)
        for p in self.pedidos:
            p.distancia = self.dist_almacen[p.lugar]
        self.sim = None
        self.asignacion = self.carga = None
        msg = ("Distancias: longitudes REALES medidas sobre OpenStreetMap." if self.reales
               else "Distancias: estimación Haversine × 1.25 (la del informe).")
        return dict(mensaje=msg, metros={f"{a}|{b}": self.grafo.peso[frozenset((a, b))]
                                         for a, b, _ in CALLES_DEF}, **self.estado_pedidos())

    # ------------------------------------------------------------ 1. pedidos
    def _siguiente_id(self) -> str:
        n = max((int(p.id[1:]) for p in self.pedidos), default=0) + 1
        return f"P{n:03d}"

    def agregar(self, cliente, lugar, prioridad, peso, valor) -> dict:
        prioridad, peso, valor = int(prioridad), int(peso), int(valor)
        if lugar not in LUGARES or not 1 <= prioridad <= 5 or peso <= 0 or valor <= 0:
            return dict(error="Revise prioridad (1-5), peso y valor (> 0).")
        p = Pedido(self._siguiente_id(), (cliente or "").strip() or "Cliente", lugar, LUGARES[lugar].sector,
                   prioridad, peso, valor, self.dist_almacen[lugar])
        self.pedidos.append(p)
        return dict(mensaje=f"Pedido {p.id} agregado en {p.lugar}.", **self.estado_pedidos())

    def eliminar(self, ids) -> dict:
        ids = set(ids)
        self.pedidos[:] = [p for p in self.pedidos if p.id not in ids]
        return dict(mensaje=f"{len(ids)} pedido(s) eliminado(s).", **self.estado_pedidos())

    def restaurar(self) -> dict:
        self._cargar(pedidos_ejemplo())
        return dict(mensaje="Datos de ejemplo restaurados (16 pedidos).", **self.estado_pedidos())

    def aleatorios(self) -> dict:
        n0 = int(self._siguiente_id()[1:])
        nuevos = pedidos_aleatorios(10, semilla=int(time.time() * 1000) % 100000, inicio=n0)
        for p in nuevos:
            p.distancia = self.dist_almacen[p.lugar]
        self.pedidos.extend(nuevos)
        return dict(mensaje="Se agregaron 10 pedidos aleatorios.", **self.estado_pedidos())

    def ordenar(self, criterio, algoritmo) -> dict:
        clave = ordenacion.CRITERIOS[criterio]
        alg = ordenacion.ALGORITMOS[algoritmo]
        t0 = time.perf_counter()
        res = alg(self.pedidos, clave)
        ms = _ms(t0)
        self.pedidos[:] = res
        return dict(mensaje=f"{algoritmo} ordenó {len(res)} pedidos por '{criterio}' en {ms:.3f} ms — O(n log n)",
                    **self.estado_pedidos())

    def buscar_id(self, ident) -> dict:
        ident = (ident or "").strip().upper()
        ordenados = busqueda.preparar_busqueda(self.pedidos)
        p, comp = busqueda.busqueda_binaria(ordenados, ident)
        _, comp_sec = busqueda.busqueda_secuencial(self.pedidos, ident)
        if p is None:
            return dict(mensaje=f"No existe el pedido {ident} ({comp} comparaciones binaria / "
                                f"{comp_sec} secuencial).", encontrado=None)
        return dict(mensaje=f"Encontrado {p.id}: {p.cliente} en {p.lugar}, prioridad {p.prioridad}. "
                            f"Binaria: {comp} comparaciones; secuencial: {comp_sec}.",
                    encontrado=p.id, capa=self._capa(f"Búsqueda binaria: {p.id}", resaltados=[p.lugar]))

    def buscar_sector(self, sector) -> dict:
        res = busqueda.IndiceSector(self.pedidos).buscar(sector)
        return dict(mensaje=f"Sector {sector}: {len(res)} pedidos (consulta O(1) en el índice hash).",
                    filtrados=[self._ped(p) for p in res],
                    capa=self._capa(f"Índice hash: {sector}", resaltados={p.lugar for p in res}))

    # ------------------------------------------------------------ 2. voraz
    def voraz_asignar(self) -> dict:
        res = voraz.asignar_mas_cercano(self.pedidos, self.repartidores, self.grafo)
        self.asignacion = res["asignacion"]
        rutas = []
        for k, r in enumerate(self.repartidores):
            tramos = [self.grafo.camino_minimo(r.ubicacion, p.lugar)[1] for p in self.asignacion[r.id]]
            rutas.append(self._ruta(tramos, PALETA_RUTAS[k], dash="4 6", ancho=3, numerar=False))
        txt = "Decisiones voraces (orden de prioridad):\n" + "\n".join(res["registro"])
        if res["sin_asignar"]:
            txt += f"\n\nSin asignar por capacidad: {[p.id for p in res['sin_asignar']]}"
        tabla = [dict(id=r.id, vehiculo=r.vehiculo, base=r.ubicacion, carga=f"{r.carga}/{r.capacidad} kg",
                      pedidos=", ".join(r.pedidos), color=PALETA_RUTAS[k])
                 for k, r in enumerate(self.repartidores)]
        return dict(texto=txt, tabla=tabla,
                    capa=self._capa("Voraz: asignación al repartidor más cercano", rutas))

    def voraz_rutas(self) -> dict:
        base = self.voraz_asignar() if self.asignacion is None else None
        rutas, lineas, total = [], [], 0.0
        for k, r in enumerate(self.repartidores):
            peds = self.asignacion.get(r.id, [])
            if not peds:
                continue
            lugares = [r.ubicacion] + [p.lugar for p in peds]
            t0 = time.perf_counter()
            D, caminos = self.grafo.matriz_distancias(lugares)
            orden, costo = voraz.ruta_vecino_mas_cercano(D, 0)
            ms = _ms(t0)
            total += costo
            rutas.append(self._ruta(self._tramos(orden, caminos), PALETA_RUTAS[k]))
            sec = " → ".join(peds[i - 1].id for i in orden[1:])
            lineas.append(f"{r.id} ({r.ubicacion}): {sec}\n   distancia {costo:,.0f} m   [{ms:.2f} ms]")
        out = dict(texto="Rutas del vecino más cercano  —  O(n²) por repartidor\n\n" + "\n".join(lineas) +
                         f"\n\nDistancia total: {total:,.0f} m",
                   capa=self._capa("Voraz: ruta del vecino más cercano", rutas))
        if base:
            out["tabla"] = base["tabla"]
        return out

    # ------------------------------------------------------------ 3. divide y vencerás
    def dividir(self, k) -> dict:
        k = max(1, min(6, int(k)))
        bases = ["Plaza de Armas", "UNSAAC (Av. de la Cultura)", "Terminal Terrestre",
                 "Plaza de Santiago", "Plaza San Sebastián", "San Blas"]
        reps = self.repartidores[:k] + [Repartidor(f"R{i + 1}", f"Moto {i + 1}", "Moto", 20, bases[i])
                                        for i in range(len(self.repartidores), k)]
        if not self.pedidos:
            return dict(texto="No hay pedidos.", capa=self._capa())
        t0 = time.perf_counter()
        res = dyv.resolver_zonas(self.pedidos, reps, self.grafo)
        ms = _ms(t0)
        rutas, zonas, lineas = [], [], []
        for i, z in enumerate(res["zonas"]):
            col = PALETA_RUTAS[i % len(PALETA_RUTAS)]
            r = z.get("repartidor")
            zonas.append(dict(caja=list(z["caja"]), color=PALETA_ZONAS[i % 6], borde=col,
                              etiqueta=f"Zona {i + 1}" + (f" · {r.id}" if r else "")))
            if r is None:
                continue
            rutas.append(self._ruta(z["tramos"], col))
            sec = " → ".join(p.id for p in z["orden_pedidos"])
            lineas.append(f"Zona {i + 1} → {r.id} desde {r.ubicacion}\n   pedidos: {len(z['pedidos'])}"
                          f"   método: {z['metodo']}\n   ruta: {sec}\n   distancia: {z['costo']:,.0f} m")
        txt = ("\n\n".join(lineas) + f"\n\nCOMBINAR:\n  distancia total   = {res['total']:,.0f} m"
               f"\n  zona más larga    = {res['maxima']:,.0f} m (tiempo de la operación)"
               f"\n  tiempo de cálculo = {ms:.1f} ms")
        return dict(texto=txt, capa=self._capa(f"Divide y vencerás: {k} zonas", rutas, zonas),
                    bases=[dict(id=r.id, pos=list(self.geo.pos[r.ubicacion])) for r in reps])

    # ------------------------------------------------------------ 4. programación dinámica
    def mochila(self, cap) -> dict:
        cap = max(1, min(500, int(cap)))
        t0 = time.perf_counter()
        sel, valor, peso, dp = pd.mochila_01(self.pedidos, cap)
        t_dp = _ms(t0)
        t0 = time.perf_counter()
        gsel, gval, gpeso = voraz.mochila_voraz(self.pedidos, cap)
        t_g = _ms(t0)
        self.carga = sel
        n = len(self.pedidos)
        txt = (f"Tabla dp de tamaño ({n}+1) x ({cap}+1) = {(n + 1) * (cap + 1):,} estados  →  O(n·W)\n"
               f"dp[n][W] = {dp[n][cap]}  (valor máximo)\n\nÚltima columna de la tabla (w = W):\n")
        for i in range(n + 1):
            et = "  (sin pedidos)" if i == 0 else \
                f"  + {self.pedidos[i - 1].id} (p={self.pedidos[i - 1].peso}, v={self.pedidos[i - 1].valor})"
            txt += f"dp[{i:>2}][{cap}] = {dp[i][cap]:>4}{et}\n"
        txt += (f"\nEl voraz pierde S/. {valor - gval}: elegir por valor/peso no garantiza el óptimo en 0/1."
                if gval < valor else "\nEn este caso el voraz coincide con el óptimo.")
        tabla = [dict(metodo="PD (óptimo)", valor=valor, peso=peso, pedidos=", ".join(p.id for p in sel),
                      ms=f"{t_dp:.2f}"),
                 dict(metodo="Voraz v/p", valor=gval, peso=gpeso, pedidos=", ".join(p.id for p in gsel),
                      ms=f"{t_g:.2f}")]
        return dict(texto=txt, tabla=tabla,
                    capa=self._capa(f"Mochila 0/1: {len(sel)} pedidos cargados, S/. {valor}",
                                    resaltados={p.lugar for p in sel}))

    def ruta_optima(self, cap) -> dict:
        extra = self.mochila(cap) if not self.carga else None
        carga = self.carga
        if len(carga) + 1 > 15:
            return dict(error="Held-Karp es O(n²·2ⁿ); use ≤ 14 pedidos (baje la capacidad).")
        lugares = [ALMACEN] + [p.lugar for p in carga]
        D, caminos = self.grafo.matriz_distancias(lugares)
        t0 = time.perf_counter()
        orden, costo = pd.held_karp(D, 0)
        t_hk = _ms(t0)
        t0 = time.perf_counter()
        orden_g, costo_g = voraz.ruta_vecino_mas_cercano(D, 0)
        t_g = _ms(t0)
        rutas = [self._ruta(self._tramos(orden_g, caminos), "#9E9E9E", dash="8 6", ancho=3, numerar=False),
                 self._ruta(self._tramos(orden, caminos), PALETA_RUTAS[0])]
        n = len(lugares)
        txt = (f"Held-Karp (PD): {' → '.join(carga[i - 1].id for i in orden[1:])}\n"
               f"   distancia {costo:,.0f} m   [{t_hk:.2f} ms]   estados: 2^{n - 1}·{n - 1} = "
               f"{(2 ** (n - 1)) * (n - 1):,}\n\n"
               f"Vecino más cercano (voraz, gris): {' → '.join(carga[i - 1].id for i in orden_g[1:])}\n"
               f"   distancia {costo_g:,.0f} m   [{t_g:.2f} ms]\n\n"
               f"El voraz recorre {100 * (costo_g / costo - 1) if costo else 0:.1f}% más.")
        out = dict(texto=txt, capa=self._capa("PD: ruta óptima (azul) vs voraz (gris)", rutas))
        if extra:
            out["tabla"] = extra["tabla"]
        return out

    def reset_carga(self) -> None:
        self.carga = None

    # ------------------------------------------------------------ 5. backtracking
    def bt_todas(self, origen, destino, cerradas) -> dict:
        if origen == destino:
            return dict(error="Origen y destino son iguales.")
        c = {_arista(p) for p in cerradas}
        t0 = time.perf_counter()
        res = bt.todas_las_rutas(self.grafo, origen, destino, c)
        ms = _ms(t0)
        self.bt_rutas = res["rutas"]
        if not res["rutas"]:
            return dict(mensaje="No existe ninguna ruta con esas calles cerradas.", filas=[], capa=self._capa())
        dist, cam = res["mejor"]
        filas = [dict(n=i + 1, dist=round(d), lugares=len(cm), recorrido=" → ".join(cm))
                 for i, (d, cm) in enumerate(res["rutas"][:300])]
        msg = (f"{len(res['rutas']):,} rutas encontradas ({res['nodos']:,} nodos del árbol de búsqueda, "
               f"{ms:.0f} ms){' [truncado]' if res['truncado'] else ''}.\n"
               f"Más corta: {dist:,.0f} m  |  más larga: {res['rutas'][-1][0]:,.0f} m")
        return dict(mensaje=msg, filas=filas, capa=self._capa_bt(cam, f"Backtracking: mejor de {len(res['rutas']):,} rutas"))

    def bt_poda(self, origen, destino, cerradas) -> dict:
        if origen == destino:
            return dict(error="Origen y destino son iguales.")
        c = {_arista(p) for p in cerradas}
        t0 = time.perf_counter()
        res = bt.ruta_mas_corta_poda(self.grafo, origen, destino, c)
        ms = _ms(t0)
        if not res["mejor"]:
            return dict(mensaje="No existe ninguna ruta con esas calles cerradas.", capa=self._capa())
        dist, cam = res["mejor"]
        return dict(mensaje=f"Con poda: {res['nodos']:,} nodos explorados ({ms:.1f} ms). "
                            f"Mejor ruta: {dist:,.0f} m (la misma, explorando mucho menos).",
                    capa=self._capa_bt(cam, "Backtracking con poda: ruta más corta"))

    def bt_ver(self, i) -> dict:
        dist, cam = self.bt_rutas[int(i)]
        return dict(capa=self._capa_bt(cam, f"Ruta #{int(i) + 1}: {dist:,.0f} m"))

    def _capa_bt(self, camino, titulo) -> dict:
        return self._capa(titulo, [self._ruta([camino], PALETA_RUTAS[2], ancho=6, numerar=False)],
                          resaltados=[camino[0], camino[-1]])

    # ------------------------------------------------------------ 6. comparación
    def comparar(self) -> dict:
        t0 = time.perf_counter()
        rutas = comparar_rutas(range(3, 12), limite_bt=10)
        moch = comparar_mochila()
        return dict(rutas=rutas, mochila=moch, ms=_ms(t0))

    # ------------------------------------------------------------ 7. en vivo
    def sim_crear(self, plan, cerradas) -> dict:
        reps = repartidores_ejemplo()
        planes = PLANES[plan](self.grafo, self.pedidos, reps)
        self.sim = Simulacion(self.grafo, planes, {_arista(p) for p in cerradas})
        self.colores = {m.rep.id: PALETA_RUTAS[k % len(PALETA_RUTAS)] for k, m in enumerate(self.sim.moviles)}
        self.sim_n_eventos = 0
        return self.sim_estado(True)

    def sim_avanzar(self, dt, forzar=False) -> dict:
        if self.sim is None:
            return dict(activa=False)
        antes = [(m.i, id(m.camino), len(m.entregados)) for m in self.sim.moviles]
        self.sim.avanzar(float(dt))
        despues = [(m.i, id(m.camino), len(m.entregados)) for m in self.sim.moviles]
        return self.sim_estado(bool(forzar) or antes != despues)

    def sim_estado(self, rutas: bool = True) -> dict:
        sim, geo = self.sim, self.geo
        moviles = []
        for m in sim.moviles:
            u, v, frac = sim.posicion(m)
            lat, lon = geo.punto(u, v, frac) if u != v else geo.pos[u]
            d = dict(id=m.rep.id, pos=[lat, lon], color=self.colores[m.rep.id], terminado=m.terminado)
            if rutas:
                d["ruta"] = [] if m.terminado or u == v else \
                    [list(p) for p in geo.resto(u, v, frac) + geo.camino(m.camino[m.i + 1:])[1:]]
            total = len(m.entregados) + len(m.pendientes) + len(m.sin_ruta)
            if m.terminado:
                est = "Terminó ✓"
            else:
                sig = m.pendientes[0] if m.pendientes else None
                est = f"→ {sig.id} {sig.lugar}" if sig else "regresando"
            falta = sim.restante(m)
            d["fila"] = dict(estado=est, entregas=f"{len(m.entregados)}/{total}",
                             recorrido=f"{m.recorrido / 1000:.2f} km",
                             falta=f"{falta / 1000:.2f} km · {falta / m.velocidad / 60:.0f} min")
            moviles.append(d)
        nuevos = sim.eventos[self.sim_n_eventos:]
        self.sim_n_eventos = len(sim.eventos)
        out = dict(activa=True, reloj=sim.reloj(), moviles=moviles, eventos=nuevos,
                   entregados=[p.id for m in sim.moviles for p in m.entregados],
                   cerradas=[_par(a) for a in sim.cerradas], terminada=sim.terminada(), rutas=rutas)
        if out["terminada"]:
            total = sum(m.recorrido for m in sim.moviles)
            out["resumen"] = f"Reparto terminado a las {sim.reloj()}: {total / 1000:.2f} km en total."
        return out

    def sim_toggle(self, a, b) -> dict:
        ar = frozenset((a, b))
        if ar in self.sim.cerradas:
            self.sim.abrir(ar)
        else:
            self.sim.cerrar(ar)
        return self.sim_estado(True)

    def sim_incidente(self) -> dict:
        activos = [m for m in self.sim.moviles if not m.terminado and self.sim.aristas_pendientes(m)]
        if not activos:
            return dict(error="No hay repartidores en ruta para generar un incidente.")
        m = random.choice(activos)
        arista = random.choice(self.sim.aristas_pendientes(m))
        self.sim._log(f"INCIDENTE: obra/accidente en la ruta de {m.rep.id}")
        a, b = _par(arista)
        return self.sim_toggle(a, b)

    def sim_reiniciar(self) -> None:
        self.sim = None


ESTADO = Estado()


def llamar(metodo: str, args_json: str = "[]") -> str:
    """Punto de entrada único desde JavaScript: llamar('voraz_rutas', '[]') → JSON."""
    try:
        res = getattr(ESTADO, metodo)(*json.loads(args_json))
        return json.dumps(res if res is not None else {}, ensure_ascii=False, default=str)
    except Exception as ex:                                      # noqa: BLE001
        import traceback
        return json.dumps(dict(error=f"{type(ex).__name__}: {ex}", traza=traceback.format_exc()))
