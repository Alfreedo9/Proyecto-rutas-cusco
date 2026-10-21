"""
modelos.py
----------
Clases de datos del sistema: Lugar (nodo del mapa), Pedido y Repartidor.

Se usan dataclasses para que el código sea corto y legible.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Lugar:
    """Punto del mapa de Cusco (intersección, plaza o zona conocida)."""
    nombre: str
    lat: float
    lon: float
    sector: str


@dataclass
class Pedido:
    """Pedido de un cliente.

    id         : código único, por ejemplo "P007".
    cliente    : nombre del cliente.
    lugar      : nombre del Lugar (nodo del grafo) donde se entrega.
    sector     : sector de la ciudad (Centro Histórico, Wanchaq, ...).
    prioridad  : 1 (normal) ... 5 (urgente).
    peso       : peso del paquete en kg (entero, se usa en la mochila 0/1).
    valor      : valor del pedido en soles (S/.).
    distancia  : distancia en metros desde el almacén (se calcula con Dijkstra).
    """
    id: str
    cliente: str
    lugar: str
    sector: str
    prioridad: int
    peso: int
    valor: int
    distancia: float = 0.0


@dataclass
class Repartidor:
    """Repartidor con su vehículo."""
    id: str
    nombre: str
    vehiculo: str            # "Moto" o "Furgoneta"
    capacidad: int           # kg
    ubicacion: str           # nombre del Lugar donde está ahora
    carga: int = 0           # kg asignados
    pedidos: list = field(default_factory=list)   # ids de pedidos asignados

    def libre(self) -> int:
        """Capacidad disponible en kg."""
        return self.capacidad - self.carga
