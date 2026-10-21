"""
datos.py
--------
Mapa simplificado de Cusco (coordenadas reales aproximadas) y datos de prueba.

* LUGARES : nodos del grafo (plazas, mercados, avenidas, distritos).
* CALLES  : aristas no dirigidas (calle o avenida que une dos lugares).
            El peso de cada arista es la distancia en metros calculada con la
            fórmula de Haversine y multiplicada por 1.25 (factor de sinuosidad:
            las calles del Cusco no son líneas rectas).
* ALMACEN : punto de partida de los repartos.
* PEDIDOS_EJEMPLO y REPARTIDORES_EJEMPLO : datos iniciales de la aplicación.

Las coordenadas son aproximadas (tomadas de un mapa de referencia) y los
nombres de las calles son referenciales.
"""
from __future__ import annotations

import math
import random

from modelos import Lugar, Pedido, Repartidor

# ------------------------------------------------------------------ lugares
#            nombre                      lat        lon       sector
_LUGARES = [
    ("Plaza de Armas",              -13.5167, -71.9787, "Centro Histórico"),
    ("Plaza Regocijo",              -13.5176, -71.9802, "Centro Histórico"),
    ("Plaza San Francisco",         -13.5186, -71.9817, "Centro Histórico"),
    ("Mercado San Pedro",           -13.5214, -71.9840, "Centro Histórico"),
    ("Qoricancha",                  -13.5199, -71.9752, "Centro Histórico"),
    ("Limacpampa",                  -13.5196, -71.9728, "Centro Histórico"),
    ("Av. Tullumayo",               -13.5172, -71.9733, "Centro Histórico"),
    ("San Blas",                    -13.5146, -71.9752, "San Blas"),
    ("San Cristóbal",               -13.5136, -71.9810, "San Blas"),
    ("Cristo Blanco",               -13.5110, -71.9768, "San Blas"),
    ("Sacsayhuamán",                -13.5094, -71.9817, "San Blas"),
    ("Av. El Sol (Correo)",         -13.5222, -71.9741, "Wanchaq"),
    ("Av. Ejército",                -13.5232, -71.9832, "Santiago"),
    ("Puente Grau",                 -13.5243, -71.9782, "Santiago"),
    ("Belén",                       -13.5266, -71.9812, "Santiago"),
    ("Plaza de Santiago",           -13.5286, -71.9858, "Santiago"),
    ("Estación Wanchaq",            -13.5262, -71.9707, "Wanchaq"),
    ("Óvalo Pachacútec",            -13.5300, -71.9701, "Wanchaq"),
    ("Plaza Túpac Amaru",           -13.5270, -71.9652, "Wanchaq"),
    ("UNSAAC (Av. de la Cultura)",  -13.5222, -71.9582, "Wanchaq"),
    ("Magisterio",                  -13.5265, -71.9611, "Wanchaq"),
    ("Hospital Regional",           -13.5241, -71.9540, "Wanchaq"),
    ("Terminal Terrestre",          -13.5356, -71.9620, "Wanchaq"),
    ("Real Plaza",                  -13.5283, -71.9520, "Wanchaq"),
    ("Ttio",                        -13.5345, -71.9536, "Wanchaq"),
    ("Aeropuerto",                  -13.5380, -71.9450, "Wanchaq"),
    ("Marcavalle",                  -13.5330, -71.9468, "San Sebastián"),
    ("Plaza San Sebastián",         -13.5310, -71.9370, "San Sebastián"),
]

LUGARES: dict[str, Lugar] = {n: Lugar(n, la, lo, s) for n, la, lo, s in _LUGARES}

# ------------------------------------------------------------------ calles
#   (lugar A, lugar B, nombre de la calle)
CALLES_DEF = [
    ("Plaza de Armas", "Plaza Regocijo", "Calle Espaderos"),
    ("Plaza de Armas", "San Blas", "Cuesta de San Blas"),
    ("Plaza de Armas", "San Cristóbal", "Cuesta del Almirante"),
    ("Plaza de Armas", "Qoricancha", "Calle Loreto"),
    ("Plaza de Armas", "Av. Tullumayo", "Calle Hatun Rumiyoc"),
    ("Plaza de Armas", "Av. El Sol (Correo)", "Calle Mantas / Av. El Sol"),
    ("Plaza Regocijo", "Plaza San Francisco", "Calle Garcilaso"),
    ("Plaza Regocijo", "San Cristóbal", "Calle Saphy"),
    ("Plaza San Francisco", "Mercado San Pedro", "Calle Santa Clara"),
    ("Plaza San Francisco", "Puente Grau", "Calle Nueva"),
    ("Mercado San Pedro", "Av. Ejército", "Calle Hospital"),
    ("Qoricancha", "Limacpampa", "Calle Zetas"),
    ("Qoricancha", "Av. El Sol (Correo)", "Calle Santo Domingo"),
    ("Av. Tullumayo", "Limacpampa", "Av. Tullumayo"),
    ("Av. Tullumayo", "San Blas", "Calle Choquechaca"),
    ("San Blas", "Cristo Blanco", "Calle Tandapata"),
    ("San Cristóbal", "Sacsayhuamán", "Camino a Sacsayhuamán"),
    ("Sacsayhuamán", "Cristo Blanco", "Vía Sacsayhuamán"),
    ("Limacpampa", "Av. El Sol (Correo)", "Av. Garcilaso"),
    ("Limacpampa", "UNSAAC (Av. de la Cultura)", "Av. de la Cultura"),
    ("Av. El Sol (Correo)", "Puente Grau", "Av. Pumacahua"),
    ("Av. El Sol (Correo)", "Estación Wanchaq", "Av. El Sol"),
    ("Av. Ejército", "Puente Grau", "Av. Ejército"),
    ("Av. Ejército", "Belén", "Av. Ejército (sur)"),
    ("Puente Grau", "Belén", "Av. Grau"),
    ("Puente Grau", "Estación Wanchaq", "Av. Pachacútec"),
    ("Belén", "Plaza de Santiago", "Av. Antonio Lorena"),
    ("Plaza de Santiago", "Óvalo Pachacútec", "Av. Huayna Cápac"),
    ("Estación Wanchaq", "Óvalo Pachacútec", "Av. El Sol (sur)"),
    ("Estación Wanchaq", "Plaza Túpac Amaru", "Av. Tacna"),
    ("Óvalo Pachacútec", "Plaza Túpac Amaru", "Av. Pachacútec (este)"),
    ("Óvalo Pachacútec", "Terminal Terrestre", "Av. Vallejo Santoni"),
    ("Plaza Túpac Amaru", "Magisterio", "Av. Huayruropata"),
    ("Plaza Túpac Amaru", "UNSAAC (Av. de la Cultura)", "Av. Garcilaso (este)"),
    ("UNSAAC (Av. de la Cultura)", "Magisterio", "Av. Universitaria"),
    ("UNSAAC (Av. de la Cultura)", "Hospital Regional", "Av. de la Cultura (este)"),
    ("Magisterio", "Hospital Regional", "Calle Los Pinos"),
    ("Magisterio", "Terminal Terrestre", "Av. Los Incas"),
    ("Hospital Regional", "Real Plaza", "Av. de la Cultura (Real Plaza)"),
    ("Real Plaza", "Ttio", "Av. Collasuyo"),
    ("Real Plaza", "Marcavalle", "Av. de la Cultura (Marcavalle)"),
    ("Terminal Terrestre", "Ttio", "Av. Velasco Astete"),
    ("Ttio", "Aeropuerto", "Av. Velasco Astete (sur)"),
    ("Ttio", "Marcavalle", "Calle Ttio"),
    ("Aeropuerto", "Marcavalle", "Av. 28 de Julio"),
    ("Marcavalle", "Plaza San Sebastián", "Av. de la Cultura (S. Sebastián)"),
]

FACTOR_SINUOSIDAD = 1.25
ALMACEN = "Plaza de Armas"   # punto de partida de los repartos


def haversine(a: Lugar, b: Lugar) -> float:
    """Distancia en metros entre dos puntos (lat, lon) sobre la Tierra."""
    r = 6_371_000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def longitud_calle(a: str, b: str) -> float:
    """Longitud aproximada (m) de la calle entre los lugares a y b."""
    return round(haversine(LUGARES[a], LUGARES[b]) * FACTOR_SINUOSIDAD, 1)


# ------------------------------------------------------------------ pedidos
_CLIENTES = ["Ana Quispe", "Luis Mamani", "Rosa Huamán", "Jorge Ccori", "María Condori",
             "Pedro Apaza", "Lucía Torres", "Carlos Huillca", "Elena Paucar", "Diego Ramos",
             "Sofía Ttito", "Miguel Cusi", "Julia Vargas", "Raúl Chávez", "Carmen Yupanqui",
             "Hugo Sullca", "Noemí Choque", "Iván Puma", "Gladys Ayma", "Óscar Laura"]

# Datos fijos (reproducibles) usados por la GUI y por las pruebas:
#            id     cliente idx  lugar                          prio peso valor
_PEDIDOS = [
    ("P001", 0, "San Blas",                    5, 3, 45),
    ("P002", 1, "Mercado San Pedro",           2, 8, 60),
    ("P003", 2, "UNSAAC (Av. de la Cultura)",  3, 2, 30),
    ("P004", 3, "Hospital Regional",           5, 1, 80),
    ("P005", 4, "Terminal Terrestre",          1, 10, 55),
    ("P006", 5, "Plaza de Santiago",           3, 6, 40),
    ("P007", 6, "Aeropuerto",                  4, 4, 70),
    ("P008", 7, "Magisterio",                  2, 5, 35),
    ("P009", 8, "Sacsayhuamán",                1, 2, 20),
    ("P010", 9, "Plaza San Sebastián",         4, 7, 65),
    ("P011", 10, "Qoricancha",                 3, 3, 25),
    ("P012", 11, "Real Plaza",                 2, 9, 90),
    ("P013", 12, "Belén",                      5, 2, 50),
    ("P014", 13, "Plaza Túpac Amaru",          1, 4, 30),
    ("P015", 14, "Cristo Blanco",              2, 1, 15),
    ("P016", 15, "Ttio",                       3, 6, 45),
]


def pedidos_ejemplo() -> list[Pedido]:
    """Lista de pedidos de ejemplo (siempre los mismos)."""
    return [Pedido(i, _CLIENTES[c], l, LUGARES[l].sector, p, w, v)
            for i, c, l, p, w, v in _PEDIDOS]


def repartidores_ejemplo() -> list[Repartidor]:
    """Tres repartidores en distintos puntos de la ciudad."""
    return [
        Repartidor("R1", "Moto 1", "Moto", 20, "Plaza de Armas"),
        Repartidor("R2", "Moto 2", "Moto", 20, "UNSAAC (Av. de la Cultura)"),
        Repartidor("R3", "Furgoneta", "Furgoneta", 60, "Terminal Terrestre"),
    ]


def pedidos_aleatorios(n: int, semilla: int = 0, inicio: int = 1) -> list[Pedido]:
    """Genera n pedidos simulados en lugares aleatorios del mapa (para pruebas)."""
    rnd = random.Random(semilla)
    nombres = list(LUGARES)
    pedidos = []
    for k in range(n):
        lugar = rnd.choice(nombres)
        pedidos.append(Pedido(
            id=f"P{inicio + k:03d}",
            cliente=rnd.choice(_CLIENTES),
            lugar=lugar,
            sector=LUGARES[lugar].sector,
            prioridad=rnd.randint(1, 5),
            peso=rnd.randint(1, 10),
            valor=rnd.randint(10, 100),
        ))
    return pedidos
