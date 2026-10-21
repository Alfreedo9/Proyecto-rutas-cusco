# Sistema de Gestión de Rutas Óptimas en Cusco

Proyecto final de **Programación III** — Ingeniería Informática y de Sistemas, UNSAAC.

Integrantes: Alfredo Quispe Huamanttupa · Elmer Leonel Baca Pauccar · Erik Huillca Casa · Roberto Carlos Quispe Hermoza

Gestión de pedidos de reparto sobre el mapa real de Cusco (OpenStreetMap) con cinco enfoques
algorítmicos: estructuras/ordenación/búsqueda, voraz, divide y vencerás, programación dinámica
y backtracking, más una simulación del reparto en tiempo real con cierres de calles.

## Estructura del repositorio

| Carpeta | Contenido |
|---|---|
| `/` (raíz) | Versión **web** desplegada en Vercel |
| `py/` | Módulos Python del proyecto (copia idéntica) + `web.py`, el puente con la interfaz web |
| `escritorio/rutas_cusco/` | Aplicación de escritorio original (Tkinter), pruebas y experimentos |

## Versión web

El código Python se ejecuta **en el navegador** con [Pyodide](https://pyodide.org) (Python 3
compilado a WebAssembly), sin servidor. `py/web.py` cumple el papel de `gui/app.py`: llama a los
mismos módulos (`algoritmos/`, `grafo.py`, `simulacion.py`, `comparacion.py`) y devuelve los
resultados en JSON; `app.js` los dibuja con Leaflet.

Probar en local:

```bash
python -m http.server 8000   # abrir http://localhost:8000
```

Despliegue: sitio estático en Vercel (Framework Preset **Other**, sin build, raíz del repo).

## Versión de escritorio

```bash
cd escritorio/rutas_cusco
pip install -r requirements.txt
python main.py
python -m unittest discover -s pruebas -v   # 23 pruebas
```

Datos del mapa: © colaboradores de OpenStreetMap (ODbL).
