"""
simulacion.py
-------------
Simulación del reparto EN TIEMPO REAL (lógica pura, sin interfaz).

Cada repartidor recorre su plan (orden de pedidos calculado por divide y
vencerás + Held-Karp, o por el enfoque voraz) avanzando metro a metro por
las calles. Si durante el reparto se CIERRA una calle, los repartidores que
la iban a usar REPLANIFICAN al instante:

  * Dijkstra (con las calles cerradas) para el nuevo camino, y
  * Held-Karp para reordenar los pedidos pendientes (≤ 10 paradas).

Así se ve a los algoritmos reaccionando a cambios del mapa mientras el
reparto está en curso.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from algoritmos.prog_dinamica import held_karp
from modelos import Pedido, Repartidor

VELOCIDAD_KMH = {"Moto": 25.0, "Furgoneta": 20.0}
INICIO_JORNADA = 8 * 3600          # 08:00


@dataclass
class Movil:
    rep: Repartidor
    pendientes: list[Pedido]               # pedidos por entregar, en orden
    camino: list[str] = field(default_factory=list)  # nodos desde el tramo actual
    i: int = 0                             # tramo actual: camino[i] → camino[i+1]
    avance: float = 0.0                    # metros recorridos dentro del tramo
    recorrido: float = 0.0
    entregados: list[Pedido] = field(default_factory=list)
    sin_ruta: list[Pedido] = field(default_factory=list)
    terminado: bool = False

    @property
    def velocidad(self) -> float:          # m/s
        return VELOCIDAD_KMH.get(self.rep.vehiculo, 25.0) / 3.6


class Simulacion:
    def __init__(self, grafo, planes: list[tuple[Repartidor, list[Pedido]]],
                 cerradas: set | None = None) -> None:
        self.grafo = grafo
        self.cerradas: set = set(cerradas or ())
        self.t = 0.0                       # segundos simulados desde el inicio
        self.eventos: list[str] = []
        self.moviles = [Movil(rep, list(peds)) for rep, peds in planes]
        self._log("Inicio del reparto: " + ", ".join(
            f"{m.rep.id} con {len(m.pendientes)} pedidos" for m in self.moviles))
        for m in self.moviles:
            m.camino = [m.rep.ubicacion]
            self._replanificar(m, reoptimizar=False)
            self._entregar_en(m, m.rep.ubicacion)

    # ------------------------------------------------------------ utilidades
    def reloj(self) -> str:
        s = int(INICIO_JORNADA + self.t)
        return f"{s // 3600 % 24:02d}:{s // 60 % 60:02d}"

    def _log(self, texto: str) -> None:
        self.eventos.append(f"[{self.reloj()}] {texto}")

    def _peso(self, u: str, v: str) -> float:
        return self.grafo.peso[frozenset((u, v))]

    def nombre(self, arista: frozenset) -> str:
        a, b = tuple(arista)
        return self.grafo.calle_entre(a, b)

    def restante(self, m: Movil) -> float:
        """Metros que le faltan a un móvil según su plan actual."""
        if m.terminado or m.i >= len(m.camino) - 1:
            return 0.0
        total = self._peso(m.camino[m.i], m.camino[m.i + 1]) - m.avance
        for u, v in zip(m.camino[m.i + 1:], m.camino[m.i + 2:]):
            total += self._peso(u, v)
        return total

    def aristas_pendientes(self, m: Movil, incluir_actual: bool = False) -> list[frozenset]:
        ini = m.i if incluir_actual else m.i + 1
        return [frozenset(p) for p in zip(m.camino[ini:], m.camino[ini + 1:])]

    def posicion(self, m: Movil) -> tuple[str, str, float]:
        """(u, v, fracción) del tramo por donde va el móvil."""
        if m.terminado or len(m.camino) < 2 or m.i >= len(m.camino) - 1:
            n = m.camino[-1] if m.camino else m.rep.ubicacion
            return n, n, 0.0
        u, v = m.camino[m.i], m.camino[m.i + 1]
        return u, v, m.avance / self._peso(u, v)

    # ------------------------------------------------------------ planificación
    def _plan(self, origen: str, pedidos: list[Pedido], reoptimizar: bool):
        """Camino desde `origen` que visita los pedidos (en orden o reordenados)."""
        if not pedidos:
            return [origen], [], []
        lugares = [origen] + [p.lugar for p in pedidos]
        D, caminos = self.grafo.matriz_distancias(lugares, self.cerradas)
        alcanzables = [k for k in range(1, len(lugares)) if D[0][k] < math.inf]
        sin_ruta = [pedidos[k - 1] for k in range(1, len(lugares)) if D[0][k] == math.inf]
        if reoptimizar and 2 <= len(alcanzables) <= 10:
            sub = [0] + alcanzables
            Ds = [[D[i][j] for j in sub] for i in sub]
            orden_sub, _ = held_karp(Ds, 0)
            orden = [sub[k] for k in orden_sub]
        else:
            orden = [0] + alcanzables
        camino = [origen]
        for x, y in zip(orden, orden[1:]):
            camino.extend(caminos[(x, y)][1:])
        return camino, [pedidos[k - 1] for k in orden[1:]], sin_ruta

    def _replanificar(self, m: Movil, reoptimizar: bool = True) -> None:
        if m.terminado:
            return
        en_tramo = m.avance > 0 and m.i < len(m.camino) - 1
        if en_tramo:            # termina la cuadra en la que está y replanifica desde ahí
            u, v = m.camino[m.i], m.camino[m.i + 1]
            camino, orden, sin_ruta = self._plan(v, m.pendientes, reoptimizar)
            m.camino, m.i = [u] + camino, 0
        else:
            origen = m.camino[m.i] if m.camino else m.rep.ubicacion
            camino, orden, sin_ruta = self._plan(origen, m.pendientes, reoptimizar)
            m.camino, m.i, m.avance = camino, 0, 0.0
        m.pendientes = orden
        for p in sin_ruta:
            if p not in m.sin_ruta:
                m.sin_ruta.append(p)
                self._log(f"{m.rep.id}: {p.id} ({p.lugar}) queda sin ruta por las calles cerradas")
        if len(m.camino) < 2 and not m.pendientes:
            self._terminar(m)

    def _terminar(self, m: Movil) -> None:
        if not m.terminado:
            m.terminado = True
            self._log(f"{m.rep.id} terminó: {len(m.entregados)} entregas, "
                      f"{m.recorrido / 1000:.2f} km recorridos")

    def _entregar_en(self, m: Movil, nodo: str) -> None:
        while m.pendientes and m.pendientes[0].lugar == nodo:
            p = m.pendientes.pop(0)
            m.entregados.append(p)
            self._log(f"{m.rep.id} entregó {p.id} en {p.lugar}")

    # ------------------------------------------------------------ tiempo
    def avanzar(self, dt: float) -> None:
        """Avanza la simulación `dt` segundos."""
        self.t += dt
        for m in self.moviles:
            if m.terminado:
                continue
            restante_dt = m.velocidad * dt
            while restante_dt > 0 and not m.terminado:
                if m.i >= len(m.camino) - 1:
                    self._terminar(m)
                    break
                u, v = m.camino[m.i], m.camino[m.i + 1]
                falta = self._peso(u, v) - m.avance
                if restante_dt < falta:
                    m.avance += restante_dt
                    m.recorrido += restante_dt
                    restante_dt = 0
                else:
                    restante_dt -= falta
                    m.recorrido += falta
                    m.i += 1
                    m.avance = 0.0
                    self._entregar_en(m, v)
                    if m.i >= len(m.camino) - 1:
                        self._terminar(m)

    def terminada(self) -> bool:
        return all(m.terminado for m in self.moviles)

    # ------------------------------------------------------------ incidentes
    def cerrar(self, arista: frozenset) -> list[str]:
        """Cierra una calle y replanifica a quienes la iban a usar."""
        if arista in self.cerradas:
            return []
        self.cerradas.add(arista)
        self._log(f"CIERRE de {self.nombre(arista)}")
        afectados = []
        for m in self.moviles:
            if m.terminado:
                continue
            if m.i < len(m.camino) - 1 and frozenset(m.camino[m.i:m.i + 2]) == arista and m.avance > 0:
                self._log(f"{m.rep.id} ya estaba en esa calle: termina la cuadra")
            if arista in self.aristas_pendientes(m, incluir_actual=m.avance == 0):
                antes = self.restante(m)
                self._replanificar(m)
                despues = self.restante(m)
                afectados.append(m.rep.id)
                self._log(f"{m.rep.id} recalcula su ruta (Dijkstra + Held-Karp): "
                          f"{despues - antes:+,.0f} m")
        if not afectados:
            self._log("Ningún repartidor usaba esa calle")
        return afectados

    def abrir(self, arista: frozenset) -> None:
        """Reabre una calle; todos replanifican por si ahora hay un camino mejor."""
        if arista not in self.cerradas:
            return
        self.cerradas.discard(arista)
        self._log(f"Calle reabierta: {self.nombre(arista)}")
        for m in self.moviles:
            if m.terminado:
                continue
            antes = self.restante(m)
            self._replanificar(m)
            ahorro = antes - self.restante(m)
            if ahorro > 1:
                self._log(f"{m.rep.id} aprovecha la reapertura: {ahorro:,.0f} m menos")


def planes_dyv(grafo, pedidos, repartidores):
    """Plan inicial con divide y vencerás (zonas + Held-Karp por zona)."""
    from algoritmos.divide_venceras import resolver_zonas
    res = resolver_zonas(pedidos, repartidores, grafo)
    return [(z["repartidor"], z["orden_pedidos"]) for z in res["zonas"] if z.get("repartidor")]


def planes_voraz(grafo, pedidos, repartidores):
    """Plan inicial voraz (repartidor más cercano + vecino más cercano)."""
    from algoritmos.voraz import asignar_mas_cercano, ruta_vecino_mas_cercano
    asig = asignar_mas_cercano(pedidos, repartidores, grafo)["asignacion"]
    planes = []
    for r in repartidores:
        peds = asig.get(r.id, [])
        if not peds:
            continue
        D, _ = grafo.matriz_distancias([r.ubicacion] + [p.lugar for p in peds])
        orden, _ = ruta_vecino_mas_cercano(D, 0)
        planes.append((r, [peds[k - 1] for k in orden[1:]]))
    return planes
