"""
Pruebas unitarias con resultados esperados.

Ejecutar desde la carpeta del proyecto:
    python -m unittest -v pruebas.test_algoritmos
"""
import itertools
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algoritmos.backtracking import ruta_mas_corta_poda, todas_las_rutas, tsp_backtracking
from algoritmos.busqueda import IndiceSector, busqueda_binaria, preparar_busqueda
from algoritmos.divide_venceras import dividir, resolver_zonas
from algoritmos.ordenacion import merge_sort, quick_sort
from algoritmos.prog_dinamica import held_karp, mochila_01
from algoritmos.voraz import asignar_mas_cercano, mochila_voraz, ruta_vecino_mas_cercano
from datos import pedidos_aleatorios, pedidos_ejemplo, repartidores_ejemplo
from grafo import Grafo
from modelos import Pedido


def P(id_, peso, valor, prio=3, lugar="Plaza de Armas"):
    return Pedido(id_, "x", lugar, "Centro Histórico", prio, peso, valor)


class TestOrdenacionBusqueda(unittest.TestCase):
    def test_ordenacion_igual_que_sorted(self):
        rnd = random.Random(1)
        for _ in range(50):
            datos = [rnd.randint(-100, 100) for _ in range(rnd.randint(0, 60))]
            self.assertEqual(merge_sort(datos), sorted(datos))
            self.assertEqual(quick_sort(datos), sorted(datos))

    def test_prioridad(self):
        # Esperado: primero prioridad 5; entre iguales, el más cercano
        a, b, c = P("A", 1, 1, prio=5), P("B", 1, 1, prio=5), P("C", 1, 1, prio=1)
        a.distancia, b.distancia, c.distancia = 900, 100, 50
        res = merge_sort([c, a, b], clave=lambda p: (-p.prioridad, p.distancia))
        self.assertEqual([p.id for p in res], ["B", "A", "C"])

    def test_merge_sort_estable(self):
        ped = [P(f"X{i}", 1, 1, prio=i % 2) for i in range(10)]
        res = merge_sort(ped, clave=lambda p: p.prioridad)
        self.assertEqual([p.id for p in res if p.prioridad == 0], ["X0", "X2", "X4", "X6", "X8"])

    def test_busqueda_binaria(self):
        ordenados = preparar_busqueda(pedidos_ejemplo())
        p, comp = busqueda_binaria(ordenados, "P007")
        self.assertEqual(p.lugar, "Aeropuerto")
        self.assertLessEqual(comp, 5)                 # ceil(log2(16)) + 1
        self.assertIsNone(busqueda_binaria(ordenados, "P999")[0])

    def test_indice_sector(self):
        idx = IndiceSector(pedidos_ejemplo())
        self.assertEqual(sorted(p.id for p in idx.buscar("San Blas")),
                         ["P001", "P009", "P015"])
        self.assertEqual(idx.buscar("Inexistente"), [])


class TestGrafo(unittest.TestCase):
    def test_dijkstra_vs_fuerza_bruta(self):
        g = Grafo()
        d, cam = g.camino_minimo("San Blas", "Plaza Túpac Amaru")
        mejor = todas_las_rutas(g, "San Blas", "Plaza Túpac Amaru")["mejor"]
        self.assertAlmostEqual(d, mejor[0])
        self.assertEqual(cam[0], "San Blas")
        self.assertEqual(cam[-1], "Plaza Túpac Amaru")


class TestVoraz(unittest.TestCase):
    def test_vecino_mas_cercano_caso_conocido(self):
        # Puntos en una recta: 0, 1, 3, 10 -> el voraz visita en orden y recorre 10
        x = [0, 1, 3, 10]
        D = [[abs(a - b) for b in x] for a in x]
        orden, costo = ruta_vecino_mas_cercano(D, 0)
        self.assertEqual(orden, [0, 1, 2, 3])
        self.assertEqual(costo, 10)

    def test_voraz_no_optimo(self):
        # Desde 0: el voraz va a 1 (dist 1) y luego debe ir lejos; el óptimo va primero a la izquierda
        x = [0, 1, -2, 6]
        D = [[abs(a - b) for b in x] for a in x]
        _, c_voraz = ruta_vecino_mas_cercano(D, 0)
        _, c_opt = held_karp(D, 0)
        self.assertEqual(c_voraz, 1 + 3 + 8)          # 0→1→-2→6 = 12
        self.assertEqual(c_opt, 2 + 3 + 5)            # 0→-2→1→6 = 10

    def test_asignacion_respeta_capacidad(self):
        res = asignar_mas_cercano(pedidos_ejemplo(), repartidores_ejemplo(), Grafo())
        for r_id, peds in res["asignacion"].items():
            cap = {"R1": 20, "R2": 20, "R3": 60}[r_id]
            self.assertLessEqual(sum(p.peso for p in peds), cap)
        # P001 (San Blas, urgente) debe ir con R1 (base Plaza de Armas, la más cercana)
        self.assertIn("P001", [p.id for p in res["asignacion"]["R1"]])


class TestProgramacionDinamica(unittest.TestCase):
    def test_mochila_caso_clasico(self):
        # Capacidad 50: el óptimo es B + C = 220 (el voraz por valor/peso toma A + B = 160)
        ped = [P("A", 10, 60), P("B", 20, 100), P("C", 30, 120)]
        sel, valor, peso, _ = mochila_01(ped, 50)
        self.assertEqual(valor, 220)
        self.assertEqual(sorted(p.id for p in sel), ["B", "C"])
        self.assertEqual(mochila_voraz(ped, 50)[1], 160)

    def test_mochila_vs_fuerza_bruta(self):
        for s in range(20):
            ped = pedidos_aleatorios(10, semilla=s)
            cap = 25
            mejor = max(sum(p.valor for p in comb)
                        for r in range(len(ped) + 1)
                        for comb in itertools.combinations(ped, r)
                        if sum(p.peso for p in comb) <= cap)
            self.assertEqual(mochila_01(ped, cap)[1], mejor)

    def test_held_karp_vs_permutaciones(self):
        rnd = random.Random(4)
        for _ in range(10):
            n = 7
            pts = [(rnd.random(), rnd.random()) for _ in range(n)]
            D = [[((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** .5 for b in pts] for a in pts]
            fuerza = min(sum(D[r[i]][r[i + 1]] for i in range(n - 1))
                         for perm in itertools.permutations(range(1, n)) for r in [(0,) + perm])
            orden, costo = held_karp(D, 0)
            self.assertAlmostEqual(costo, fuerza)
            self.assertEqual(sorted(orden), list(range(n)))
            self.assertAlmostEqual(tsp_backtracking(D, 0)[1], fuerza)


class TestDivideVenceras(unittest.TestCase):
    def test_zonas_balanceadas_y_completas(self):
        ped = pedidos_ejemplo()
        zonas = dividir(ped, 4)
        tam = [len(z["pedidos"]) for z in zonas]
        self.assertEqual(sum(tam), len(ped))          # no se pierde ningún pedido
        self.assertLessEqual(max(tam) - min(tam), 1)  # zonas balanceadas
        ids = sorted(p.id for z in zonas for p in z["pedidos"])
        self.assertEqual(ids, sorted(p.id for p in ped))

    def test_resolver_zonas(self):
        res = resolver_zonas(pedidos_ejemplo(), repartidores_ejemplo(), Grafo())
        self.assertEqual(len(res["zonas"]), 3)
        self.assertGreater(res["total"], 0)


class TestBacktracking(unittest.TestCase):
    def test_calle_cerrada_cambia_ruta(self):
        g = Grafo()
        libre = todas_las_rutas(g, "San Blas", "Plaza Túpac Amaru")
        cerradas = {frozenset(("San Blas", "Av. Tullumayo")),
                    frozenset(("Limacpampa", "UNSAAC (Av. de la Cultura)")),
                    frozenset(("Av. El Sol (Correo)", "Estación Wanchaq"))}
        con = todas_las_rutas(g, "San Blas", "Plaza Túpac Amaru", cerradas)
        self.assertLess(len(con["rutas"]), len(libre["rutas"]))
        self.assertGreaterEqual(con["mejor"][0], libre["mejor"][0])
        # Ninguna ruta usa una calle cerrada
        for _, cam in con["rutas"]:
            for a, b in zip(cam, cam[1:]):
                self.assertNotIn(frozenset((a, b)), cerradas)
        # La versión con poda encuentra la misma distancia explorando menos nodos
        poda = ruta_mas_corta_poda(g, "San Blas", "Plaza Túpac Amaru", cerradas)
        self.assertAlmostEqual(poda["mejor"][0], con["mejor"][0])
        self.assertLess(poda["nodos"], con["nodos"])

    def test_sin_ruta(self):
        g = Grafo()
        cerradas = {frozenset(("Sacsayhuamán", "San Cristóbal")),
                    frozenset(("Sacsayhuamán", "Cristo Blanco"))}
        self.assertIsNone(todas_las_rutas(g, "Sacsayhuamán", "Plaza de Armas", cerradas)["mejor"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
