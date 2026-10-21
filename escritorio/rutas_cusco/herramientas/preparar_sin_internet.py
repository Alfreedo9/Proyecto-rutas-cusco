"""
herramientas/preparar_sin_internet.py
-------------------------------------
Deja la aplicación lista para presentar SIN internet:

  1. Descarga las calles reales de OpenStreetMap  → data/cusco_osm.json
  2. Guarda las teselas del mapa de Cusco          → data/cusco_teselas.db
     (zoom 12 a 17, unas 600 imágenes, ~15 MB)

Uso (con internet, una sola vez):
    python herramientas/preparar_sin_internet.py

Después, aunque no haya conexión, el mapa se ve desde la base de datos local.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import osm  # noqa: E402
from datos import LUGARES  # noqa: E402


def main():
    print("1) Calles reales de OpenStreetMap")
    osm.generar_cache()

    print("\n2) Teselas del mapa (puede tardar unos minutos)")
    from tkintermapview import OfflineLoader
    from gui.mapa_real import RUTA_TESELAS, SERVIDORES_MAPA
    lats = [l.lat for l in LUGARES.values()]
    lons = [l.lon for l in LUGARES.values()]
    m = 0.01
    url, maximo, _ = SERVIDORES_MAPA["Calles (OpenStreetMap)"]
    cargador = OfflineLoader(path=RUTA_TESELAS, tile_server=url, max_zoom=maximo)
    cargador.save_offline_tiles((max(lats) + m, min(lons) - m), (min(lats) - m, max(lons) + m), 12, 17)
    print(f"\nListo: {RUTA_TESELAS}")


if __name__ == "__main__":
    main()
