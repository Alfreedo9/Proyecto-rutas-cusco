"""
Pruebas del mapa real (osm.py, geometria.py) y de la simulación en tiempo real.

No necesitan internet: usan una red vial SINTÉTICA con el mismo formato que
devuelve la API Overpass de OpenStreetMap (cada calle del grafo es una vía con
tres nodos intermedios ligeramente curvados).
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import osm
from algoritmos.divide_venceras import resolver_zonas
from datos import CALLES_DEF, LUGARES, pedidos_ejemplo, repartidores_ejemplo
from geometria import Geometria
from grafo import Grafo
from simulacion import Simulacion, planes_dyv, planes_voraz


def red_sintetica() -> dict:
    """Respuesta tipo Overpass: lugares = nodos 1..28; cada calle = una vía curva."""
    ids = {n: k + 1 for k, n in enumerate(LUGARES)}
    elementos, nid = [], 1000
    for a, b, nombre in CALLES_DEF:
        la, lb = LUGARES[a], LUGARES[b]
        nodos = [ids[a]]
        geom = [{"lat": la.lat, "lon": la.lon}]
        for t in (0.25, 0.5, 0.75):                      # curva suave
            off = 0.0004 * math.sin(math.pi * t)
            nodos.append(nid)
            nid += 1
            geom.append({"lat": la.lat + (lb.lat - la.lat) * t + off,
                         "lon": la.lon + (lb.lon - la.lon) * t - off})
        nodos.append(ids[b])
        geom.append({"lat": lb.lat, "lon": lb.lon})
        elementos.append({"type": "way", "id": len(elementos) + 1, "nodes": nodos,
                          "geometry": geom, "tags": {"highway": "residential", "name": "OSM " + nombre}})
    # un tramo suelto, desconectado del resto (no debe usarse)
    elementos.append({"type": "way", "id": 999, "nodes": [9001, 9002],
                      "geometry": [{"lat": -13.5168, "lon": -71.9788}, {"lat": -13.5169, "lon": -71.9789}],
                      "tags": {"highway": "service"}})
    return {"elements": elementos}


class TestOSM(unittest.TestCase):
    def setUp(self):
        self.datos = osm.trazar(red_sintetica(), avisar=lambda *_: None)

    def test_traza_las_46_calles(self):
        self.assertEqual(len(self.datos["calles"]), len(CALLES_DEF))
        for c in self.datos["calles"]:
            self.assertGreaterEqual(len(c["geometria"]), 2)
            recta = osm.metros(LUGARES[c["a"]].lat, LUGARES[c["a"]].lon,
                               LUGARES[c["b"]].lat, LUGARES[c["b"]].lon)
            self.assertGreaterEqual(c["metros"] + 1e-6, recta)       # nunca más corta que la recta
            self.assertTrue(c["nombre_osm"].startswith("OSM "))

    def test_lugares_en_la_componente_principal(self):
        # el tramo suelto queda cerca de la Plaza de Armas pero no debe elegirse
        la, lo = self.datos["lugares"]["Plaza de Armas"]
        self.assertAlmostEqual(la, LUGARES["Plaza de Armas"].lat, places=5)
        self.assertAlmostEqual(lo, LUGARES["Plaza de Armas"].lon, places=5)

    def test_grafo_con_longitudes_reales(self):
        g = Grafo(osm.longitudes(self.datos))
        c = self.datos["calles"][0]
        self.assertAlmostEqual(g.peso[frozenset((c["a"], c["b"]))], c["metros"])
        self.assertTrue(g.reales)

    def test_geometria(self):
        geo = Geometria(self.datos)
        a, b = "Plaza de Armas", "San Blas"
        self.assertEqual(geo.punto(a, b, 0.0), geo.tramo(a, b)[0])
        self.assertEqual(geo.punto(a, b, 1.0), geo.tramo(a, b)[-1])
        self.assertEqual(geo.tramo(b, a), geo.tramo(a, b)[::-1])
        resto = geo.resto(a, b, 0.4)
        self.assertEqual(resto[0], geo.punto(a, b, 0.4))
        self.assertEqual(resto[-1], geo.pos[b])


class TestSimulacion(unittest.TestCase):
    def setUp(self):
        self.g = Grafo()

    def _correr(self, sim, limite=20000):
        k = 0
        while not sim.terminada() and k < limite:
            sim.avanzar(5)
            k += 1
        return k

    def test_recorre_lo_planificado(self):
        planes = planes_dyv(self.g, pedidos_ejemplo(), repartidores_ejemplo())
        esperado = resolver_zonas(pedidos_ejemplo(), repartidores_ejemplo(), self.g)["total"]
        sim = Simulacion(self.g, planes)
        self._correr(sim)
        self.assertTrue(sim.terminada())
        self.assertAlmostEqual(sum(m.recorrido for m in sim.moviles), esperado, delta=1.0)
        self.assertEqual(sum(len(m.entregados) for m in sim.moviles), 16)

    def test_cierre_en_vivo_replanifica(self):
        sim = Simulacion(self.g, planes_voraz(self.g, pedidos_ejemplo(), repartidores_ejemplo()))
        for _ in range(10):
            sim.avanzar(5)
        m = next(x for x in sim.moviles if len(sim.aristas_pendientes(x)) >= 2)
        arista = sim.aristas_pendientes(m)[1]
        sim.cerrar(arista)
        self.assertNotIn(arista, sim.aristas_pendientes(m))
        self._correr(sim)
        entregados = sum(len(x.entregados) for x in sim.moviles)
        sin_ruta = sum(len(x.sin_ruta) for x in sim.moviles)
        self.assertEqual(entregados + sin_ruta, 16)

    def test_pedido_inalcanzable(self):
        cerradas = {frozenset(("Ttio", "Aeropuerto")), frozenset(("Aeropuerto", "Marcavalle"))}
        sim = Simulacion(self.g, planes_dyv(self.g, pedidos_ejemplo(), repartidores_ejemplo()), cerradas)
        self._correr(sim)
        self.assertTrue(sim.terminada())
        self.assertIn("P007", {p.id for m in sim.moviles for p in m.sin_ruta})


if __name__ == "__main__":
    unittest.main()
