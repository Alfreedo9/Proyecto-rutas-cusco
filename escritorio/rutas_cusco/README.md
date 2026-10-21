# Sistema de Gestión de Rutas Óptimas en Cusco

Proyecto del curso **Programación III** (UNSAAC).

Integrantes:

- Alfredo Quispe Huamanttupa
- Elmer Leonel Baca Pauccar
- Erik Huillca Casa
- Roberto Carlos Quispe Hermoza

Aplicación en Python con interfaz gráfica (Tkinter) para gestionar pedidos de reparto
en Cusco sobre el **mapa real de la ciudad** (OpenStreetMap). Aplica cinco enfoques
algorítmicos, compara su eficiencia y simula el reparto **en tiempo real**, con
cierres de calles mientras los repartidores circulan:

1. Estructuras, ordenación y búsqueda
2. Voraz
3. Divide y vencerás
4. Programación dinámica
5. Backtracking

## Cómo ejecutar

Requisitos: **Python 3.10 o superior** y, para el mapa real, la librería
[`tkintermapview`](https://github.com/TomSchimansky/TkinterMapView):

```bash
pip install -r requirements.txt             # instala tkintermapview (mapa real)
python main.py                              # abre la aplicación
python -m unittest discover -s pruebas -v   # 23 pruebas
python comparacion.py                       # experimentos de tiempo y calidad
```

* La primera vez que se abre con internet, la aplicación descarga sola las calles
  reales de OpenStreetMap y las guarda en `data/cusco_osm.json` (botón
  **Actualizar calles OSM** para volver a descargarlas).
* Sin `tkintermapview` la aplicación funciona igual con el mapa simplificado.
* Para presentar **sin internet**: con conexión, ejecutar una vez
  `python herramientas/preparar_sin_internet.py` (guarda calles y teselas en `data/`).

> En macOS, si `tkinter` no está disponible, instale Python desde python.org.
> Con Homebrew también se puede: `brew install python-tk`.

## Mapa real y tiempo real

| Función | Cómo se usa |
|---|---|
| Mapa de OpenStreetMap | Arrastrar para moverse, rueda o `+`/`-` para zoom; fondo *Calles* (OSM), *Claro* o *Satélite* (Esri) |
| Calles reales | Cada una de las 46 calles del grafo sigue el trazo real de las vías (Dijkstra sobre la red de OSM, `osm.py`) |
| Cerrar vías | Clic en una calle del mapa (pestañas 5 y 7): se pinta de rojo con ✕ |
| Distancias reales | Casilla *Distancias reales (OSM)*: usa la longitud medida en OSM en lugar de Haversine × 1.25 |
| Pestaña 7 · En vivo | Los repartidores avanzan por las calles; al cerrar una calle replanifican al instante (Dijkstra + Held-Karp); botón *Incidente aleatorio* |

Los algoritmos siguen trabajando sobre el grafo de 28 lugares y 46 calles (así los
resultados del informe se mantienen); el mapa real se usa para ubicar los lugares,
dibujar los recorridos por las calles verdaderas y, si se activa, medir las distancias.

## Estructura

```
rutas_cusco/
├── main.py                    # punto de entrada
├── modelos.py                 # Lugar, Pedido, Repartidor (dataclasses)
├── datos.py                   # mapa de Cusco (28 lugares, 46 calles) y pedidos de ejemplo
├── grafo.py                   # grafo de calles + Dijkstra
├── osm.py                     # calles reales de OpenStreetMap (Overpass + Dijkstra)
├── geometria.py               # trazos de las calles y posición de los vehículos
├── simulacion.py              # reparto en tiempo real con cierres de calles
├── comparacion.py             # experimentos Voraz vs PD vs Backtracking
├── requirements.txt           # tkintermapview
├── data/                      # (se crea solo) cusco_osm.json, cusco_teselas.db
├── algoritmos/
│   ├── ordenacion.py          # Merge Sort, Quick Sort
│   ├── busqueda.py            # búsqueda binaria, índice hash por sector
│   ├── voraz.py               # asignación al más cercano, vecino más cercano, mochila voraz
│   ├── divide_venceras.py     # segmentación de la ciudad (árbol k-d) + ruta por zona
│   ├── prog_dinamica.py       # mochila 0/1, Held-Karp (TSP)
│   └── backtracking.py        # todas las rutas evitando calles cerradas, TSP exacto
├── gui/
│   ├── app.py                 # ventana principal con 7 pestañas
│   ├── mapa_real.py           # mapa real (tkintermapview + OpenStreetMap)
│   └── mapa.py                # mapa simplificado (respaldo sin la librería)
├── herramientas/
│   └── preparar_sin_internet.py
└── pruebas/
    ├── test_algoritmos.py     # 16 pruebas de los algoritmos
    └── test_mapa_vivo.py      # 7 pruebas de OSM, geometría y simulación
```

## Requerimiento → implementación

| Requerimiento | Función | Complejidad |
|---|---|---|
| Ingreso de pedidos con coordenadas | `gui/app.py::_agregar_pedido`, clic en el mapa | O(1) |
| Ordenación por prioridad o distancia | `ordenacion.merge_sort`, `quick_sort` | O(n log n) |
| Búsqueda por ID | `busqueda.busqueda_binaria` | O(log n) |
| Búsqueda por sector | `busqueda.IndiceSector` | O(1) + k |
| Voraz: repartidor más cercano | `voraz.asignar_mas_cercano` | O(m(V+E)log V + n·m) |
| Voraz: punto más próximo | `voraz.ruta_vecino_mas_cercano` | O(n²) |
| Divide y vencerás: zonas | `divide_venceras.dividir` + `resolver_zonas` | O(n log² n) + rutas por zona |
| PD: mochila | `prog_dinamica.mochila_01` | O(n·W) |
| PD: ruta óptima | `prog_dinamica.held_karp` | O(n²·2ⁿ) |
| Backtracking: rutas con calles cerradas | `backtracking.todas_las_rutas` | O(V!) peor caso |
| Distancias por calles | `grafo.Grafo.dijkstra` | O((V+E) log V) |
| Trazar calles sobre OSM | `osm.trazar` (Dijkstra en la red real) | O(k (N+M) log N) |
| Replanificar en vivo al cerrar una calle | `simulacion.Simulacion.cerrar` | Dijkstra + Held-Karp (≤ 10 paradas) |
