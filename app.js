/* Rutas Óptimas Cusco — interfaz web.
 * Toda la lógica está en Python (py/web.py + módulos originales), ejecutada con Pyodide.
 * Este archivo solo dibuja el mapa (Leaflet) y las pestañas. */
"use strict";

const ARCHIVOS_PY = [
  "web.py", "modelos.py", "datos.py", "grafo.py", "geometria.py", "simulacion.py", "comparacion.py", "osm.py",
  "algoritmos/__init__.py", "algoritmos/ordenacion.py", "algoritmos/busqueda.py", "algoritmos/voraz.py",
  "algoritmos/divide_venceras.py", "algoritmos/prog_dinamica.py", "algoritmos/backtracking.py",
  "data/cusco_osm.json",
];
const COLOR_PRIORIDAD = { 5: "#D7263D", 4: "#F46036", 3: "#E2A100", 2: "#2E86AB", 1: "#6C757D" };
const COLOR_CALLE = "#2F7E9A", COLOR_CERRADA = "#D7263D", COLOR_ENTREGADO = "#9E9E9E";
const FONDOS = {
  osm: ["https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", 19, "© colaboradores de OpenStreetMap"],
  claro: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", 16, "© Esri · © OpenStreetMap"],
  sat: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", 19, "© Esri · © OpenStreetMap"],
};

const $ = (s) => document.querySelector(s);
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (n, d = 0) => Number(n).toLocaleString("es-PE", { minimumFractionDigits: d, maximumFractionDigits: d });

let llamarPy = null;
function py(metodo, ...args) {
  const r = JSON.parse(llamarPy(metodo, JSON.stringify(args)));
  if (r && r.traza) console.error(r.traza);
  return r;
}

// ---------------------------------------------------------------- estado de la interfaz
const S = {
  datos: null, pedidos: [], repartidores: [], lugares: {}, calles: [],
  tab: 0, cerradas: new Set(), capa: null, resaltados: new Set(), bases: null,
  seleccion: new Set(), btTurno: 0, entregados: new Set(),
  sim: { activa: false, existe: false, job: null, prev: 0, tick: 0 },
};
const clave = (a, b) => `${a}|${b}`;
function claveCalle(a, b) {
  return S.calles.some((c) => c.a === a && c.b === b) ? clave(a, b) : clave(b, a);
}
const cerradasLista = () => [...S.cerradas].map((k) => k.split("|"));

function estado(t) { $("#estado").textContent = t; }

// ---------------------------------------------------------------- carga de Pyodide
async function iniciar() {
  const barra = $("#carga-barra"), paso = $("#carga-paso");
  const avance = (p, t) => { barra.style.width = p + "%"; paso.textContent = t; };
  try {
    avance(8, "Descargando Pyodide (Python 3 en WebAssembly)…");
    const pyodide = await loadPyodide({ indexURL: "vendor/pyodide/" });
    avance(60, "Cargando los módulos del proyecto…");
    const base = "/home/pyodide/rutas";
    pyodide.FS.mkdirTree(base + "/algoritmos");
    pyodide.FS.mkdirTree(base + "/data");
    const textos = await Promise.all(ARCHIVOS_PY.map((f) => fetch("py/" + f).then((r) => {
      if (!r.ok) throw new Error("No se pudo cargar py/" + f);
      return r.text();
    })));
    ARCHIVOS_PY.forEach((f, i) => pyodide.FS.writeFile(`${base}/${f}`, textos[i]));
    avance(80, "Construyendo el grafo y ejecutando Dijkstra…");
    await new Promise((r) => setTimeout(r, 30));
    pyodide.runPython(`import os, sys\nos.chdir("${base}")\nsys.path.insert(0, "${base}")\nfrom web import llamar`);
    llamarPy = pyodide.globals.get("llamar");
    avance(95, "Dibujando el mapa…");
    S.datos = py("inicio");
    montar();
    avance(100, "Listo");
    setTimeout(() => $("#carga").classList.add("fuera"), 250);
  } catch (e) {
    console.error(e);
    $("#carga").classList.add("error");
    avance(100, "Error al iniciar: " + e.message + "\nRecargue la página (se necesita conexión a internet la primera vez).");
  }
}

// ---------------------------------------------------------------- mapa
let mapa, fondo, L_zonas, L_calles, L_rutas, L_hit, L_lugares, L_marcas, L_vivo;
const moviles = {}, rutasVivas = {};

function crearMapa() {
  mapa = L.map("mapa", { zoomControl: true, preferCanvas: false }).setView([-13.523, -71.965], 14);
  for (const [n, z] of [["zonas", 350], ["calles", 400], ["rutas", 420], ["vivo", 430], ["hit", 450]]) {
    mapa.createPane(n).style.zIndex = z;
  }
  cambiarFondo("osm");
  L_zonas = L.layerGroup().addTo(mapa);
  L_calles = L.layerGroup().addTo(mapa);
  L_rutas = L.layerGroup().addTo(mapa);
  L_vivo = L.layerGroup().addTo(mapa);
  L_hit = L.layerGroup().addTo(mapa);
  L_lugares = L.layerGroup().addTo(mapa);
  L_marcas = L.layerGroup().addTo(mapa);
  mapa.on("click", (e) => {
    const n = lugarCercano(e.latlng.lat, e.latlng.lng, 250);
    if (n) clicLugar(n);
  });
}

function cambiarFondo(k) {
  if (fondo) mapa.removeLayer(fondo);
  const [url, maxZ, attr] = FONDOS[k];
  fondo = L.tileLayer(url, { maxZoom: 19, maxNativeZoom: maxZ, attribution: attr }).addTo(mapa);
}

function centrar() {
  const pts = Object.values(S.lugares).map((l) => l.pos);
  mapa.fitBounds(L.latLngBounds(pts).pad(0.06));
}

function metrosAprox(p, q) {
  const lat = ((p[0] + q[0]) / 2) * Math.PI / 180;
  const dy = (q[0] - p[0]) * 111320, dx = (q[1] - p[1]) * 111320 * Math.cos(lat);
  return Math.hypot(dx, dy);
}
function lugarCercano(lat, lon, max) {
  let mejor = null, md = Infinity;
  for (const l of Object.values(S.lugares)) {
    const d = metrosAprox([lat, lon], l.pos);
    if (d < md) { md = d; mejor = l.nombre; }
  }
  return md <= max ? mejor : null;
}
function puntoMedio(coords) {
  let total = 0; const acc = [0];
  for (let i = 1; i < coords.length; i++) { total += metrosAprox(coords[i - 1], coords[i]); acc.push(total); }
  const obj = total / 2;
  for (let i = 1; i < acc.length; i++) {
    if (acc[i] >= obj) {
      const t = acc[i] === acc[i - 1] ? 0 : (obj - acc[i - 1]) / (acc[i] - acc[i - 1]);
      const p = coords[i - 1], q = coords[i];
      return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
    }
  }
  return coords[0];
}
const icono = (html, w, h, ax = w / 2, ay = h / 2) => L.divIcon({ className: "ic", html, iconSize: [w, h], iconAnchor: [ax, ay] });

function redibujar() {
  L_zonas.clearLayers(); L_calles.clearLayers(); L_rutas.clearLayers();
  L_hit.clearLayers(); L_lugares.clearLayers(); L_marcas.clearLayers();
  const capa = Object.assign({ rutas: [], zonas: [], resaltados: [], titulo: "" }, S.capa || {});

  // zonas (divide y vencerás)
  for (const z of capa.zonas) {
    const [lat0, lat1, lon0, lon1] = z.caja;
    L.rectangle([[lat0, lon0], [lat1, lon1]], { pane: "zonas", color: z.borde, weight: 3, fillColor: z.color, fillOpacity: 0.38, interactive: false }).addTo(L_zonas);
    L.marker([lat1, lon0], { icon: icono(`<span class="ic-zona" style="background:${z.borde}">${esc(z.etiqueta)}</span>`, 1, 1, -6, -6), interactive: false }).addTo(L_zonas);
  }

  // las 46 calles del grafo (trazo real de OSM)
  for (const c of S.calles) {
    const k = clave(c.a, c.b), cerrada = S.cerradas.has(k);
    L.polyline(c.coords, { pane: "calles", color: cerrada ? COLOR_CERRADA : COLOR_CALLE, weight: cerrada ? 5 : 4,
      opacity: cerrada ? 0.95 : 0.55, dashArray: cerrada ? "6 5" : null, interactive: false, lineCap: "round" }).addTo(L_calles);
    const hit = L.polyline(c.coords, { pane: "hit", color: "#000", weight: 16, opacity: 0, lineCap: "round" }).addTo(L_hit);
    hit.on("click", (e) => { L.DomEvent.stopPropagation(e); clicCalle(c); });
    hit.on("mouseover", () => hit.setStyle({ opacity: 0.12 }));
    hit.on("mouseout", () => hit.setStyle({ opacity: 0 }));
    hit.bindTooltip(`${esc(c.nombre)} · ${fmt(c.metros)} m`, { sticky: true, direction: "top", opacity: 0.9 });
    if (cerrada) L.marker(puntoMedio(c.coords), { icon: icono('<div class="ic-x">✕</div>', 18, 18), interactive: false }).addTo(L_calles);
  }

  // rutas calculadas
  for (const r of capa.rutas) {
    for (const seg of r.segmentos) {
      if (seg.length < 2) continue;
      L.polyline(seg, { pane: "rutas", color: "#fff", weight: r.ancho + 5, opacity: 0.75, interactive: false, lineCap: "round", lineJoin: "round" }).addTo(L_rutas);
      L.polyline(seg, { pane: "rutas", color: r.color, weight: r.ancho + 2, opacity: 0.95, dashArray: r.dash, interactive: false, lineCap: "round", lineJoin: "round" }).addTo(L_rutas);
    }
    for (const p of r.paradas) {
      L.marker(p.pos, { icon: icono(`<div class="ic-parada" style="background:${r.color}">${p.n}</div>`, 20, 20, 10, 30), interactive: false, zIndexOffset: 400 }).addTo(L_marcas);
    }
  }

  // lugares
  const nombres = $("#f-nombres").checked;
  for (const l of Object.values(S.lugares)) {
    const res = S.resaltados.has(l.nombre) || capa.resaltados.includes(l.nombre);
    const m = L.circleMarker(l.pos, { radius: res ? 8 : 5, color: res ? "#222" : "#fff", weight: 2,
      fillColor: res ? "#F2A65A" : "#0E3B43", fillOpacity: 1 }).addTo(L_lugares);
    m.on("click", (e) => { L.DomEvent.stopPropagation(e); clicLugar(l.nombre); });
    m.bindTooltip(esc(l.nombre), nombres ? { permanent: true, direction: "right", offset: [6, -8], className: "nombre" }
      : { direction: "top", offset: [0, -6] });
  }

  // almacén
  L.marker(S.lugares[S.datos.almacen].pos, { icon: icono('<div class="ic-almacen">A</div>', 22, 22), zIndexOffset: 500, title: "Almacén" }).addTo(L_marcas);

  // repartidores (bases)
  if (S.tab !== 6 || !S.sim.existe) {
    const bases = S.tab === 2 && S.bases ? S.bases : S.repartidores;
    const porLugar = {};
    for (const r of bases) {
      const k = r.pos.join(",");
      porLugar[k] = (porLugar[k] || 0) + 1;
      L.marker(r.pos, { icon: icono(`<div class="ic-rep">${esc(r.id)}</div>`, 24, 24, 12 - (porLugar[k] - 1) * 26, -10), zIndexOffset: 300, interactive: false }).addTo(L_marcas);
    }
  }

  // pedidos agrupados por lugar (píldoras según prioridad)
  const grupos = {};
  for (const p of S.pedidos) (grupos[p.lugar] ||= []).push(p);
  for (const [lugar, ps] of Object.entries(grupos)) {
    const vis = ps.slice(0, 4).map((p) => {
      const col = S.entregados.has(p.id) ? COLOR_ENTREGADO : COLOR_PRIORIDAD[p.prioridad];
      return `<b style="background:${col}">${esc(p.id)}</b>`;
    }).join("") + (ps.length > 4 ? `<b style="background:#555">+${ps.length - 4}</b>` : "");
    const m = L.marker(S.lugares[lugar].pos, { icon: icono(`<div class="ic-pedidos">${vis}</div>`, 1, 1, -10, -4), zIndexOffset: 200 }).addTo(L_marcas);
    m.bindTooltip(ps.map((p) => `${p.id} · ${esc(p.cliente)} · prio ${p.prioridad} · ${p.peso} kg · S/. ${p.valor}`).join("<br>"), { direction: "top" });
  }

  const t = $("#mapa-titulo");
  t.hidden = !capa.titulo;
  t.textContent = capa.titulo || "";
}

function leyenda() {
  const items = [["#222", "Almacén", 3], ["#1B998B", "Repartidor", 99]]
    .concat([5, 4, 3, 2, 1].map((k) => [COLOR_PRIORIDAD[k], `Prio ${k}`, 3]))
    .concat([[COLOR_ENTREGADO, "Entregado", 3], [COLOR_CERRADA, "Calle cerrada", 3]]);
  $("#leyenda").innerHTML = items.map(([c, t, r]) => `<span><i style="background:${c};border-radius:${r}px"></i>${t}</span>`).join("");
}

function ponerCapa(capa) {
  S.capa = capa || null;
  S.resaltados = new Set();
  redibujar();
}
function limpiarMapa() { S.capa = null; S.resaltados = new Set(); S.bases = null; redibujar(); }

// ---------------------------------------------------------------- clics en el mapa
function clicLugar(n) {
  $("#f-lugar").value = n;
  if (S.tab === 4) {
    $(S.btTurno === 0 ? "#f-origen" : "#f-destino").value = n;
    S.btTurno ^= 1;
  }
  S.resaltados = new Set([n]);
  redibujar();
  estado(`Lugar seleccionado: ${n} (${S.lugares[n].sector})`);
}

function clicCalle(c) {
  const k = clave(c.a, c.b);
  if (S.tab === 6) return simClicCalle(c);
  if (S.tab !== 4) {
    estado(`Calle: ${c.nombre} (${c.a} – ${c.b}), ${fmt(c.metros)} m` + (c.nombre_osm ? `  ·  en OSM: ${c.nombre_osm}` : "") +
      "  —  para cerrarla use la pestaña 5 o 7.");
    return;
  }
  S.cerradas.has(k) ? S.cerradas.delete(k) : S.cerradas.add(k);
  refrescarCerradas();
  redibujar();
}

function refrescarCerradas() {
  const nombres = S.calles.filter((c) => S.cerradas.has(clave(c.a, c.b))).map((c) => c.nombre);
  $("#l-cerradas").textContent = nombres.length ? "Calles cerradas por mantenimiento: " + nombres.join("; ") : "Calles cerradas: ninguna";
}

// ---------------------------------------------------------------- tablas
function tabla(sel, cols, filas, opts = {}) {
  const t = $(sel);
  if (!filas.length && !opts.vacia) { t.innerHTML = ""; return; }
  t.innerHTML = `<thead><tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>` +
    filas.map((f, i) => `<tr data-i="${i}"${opts.attr ? opts.attr(f, i) : ""}>${f.map((v) => `<td>${v}</td>`).join("")}</tr>`).join("") + "</tbody>";
}

function mostrarPedidos(lista) {
  tabla("#tb-pedidos", ["ID", "Cliente", "Lugar", "Sector", "Prio", "Peso", "S/.", "Dist (m)"],
    lista.map((p) => [p.id, esc(p.cliente), esc(p.lugar), esc(p.sector),
      `<span class="chip" style="background:${COLOR_PRIORIDAD[p.prioridad]}">${p.prioridad}</span>`, p.peso, p.valor, fmt(p.distancia)]),
    { attr: (f, i) => ` data-id="${lista[i].id}"` + (S.seleccion.has(lista[i].id) ? ' class="sel"' : ""), vacia: true });
}

function aplicarPedidos(r, mensaje = true) {
  if (r.error) { alert(r.error); return false; }
  S.pedidos = r.pedidos; S.repartidores = r.repartidores;
  S.seleccion = new Set([...S.seleccion].filter((id) => S.pedidos.some((p) => p.id === id)));
  mostrarPedidos(S.pedidos);
  if (mensaje && r.mensaje) $("#r-pedidos").textContent = r.mensaje;
  redibujar();
  return true;
}

// ---------------------------------------------------------------- montaje
function opciones(sel, valores, valor) {
  $(sel).innerHTML = valores.map((v) => `<option>${esc(v)}</option>`).join("");
  if (valor !== undefined) $(sel).value = valor;
}

function montar() {
  const d = S.datos;
  for (const l of d.lugares) S.lugares[l.nombre] = l;
  S.calles = d.calles;
  S.pedidos = d.pedidos; S.repartidores = d.repartidores;
  const nombres = d.lugares.map((l) => l.nombre);
  opciones("#f-lugar", nombres, "San Blas");
  opciones("#f-origen", nombres, "San Blas");
  opciones("#f-destino", nombres, "Plaza Túpac Amaru");
  opciones("#f-criterio", d.criterios);
  opciones("#f-alg", d.algoritmos);
  opciones("#f-sector", d.sectores);
  opciones("#f-plan", d.planes);
  $("#l-osm").textContent = d.osm.calles ? `Calles reales OSM: ${d.osm.calles}/46 · red de ${fmt(d.osm.nodos)} nodos` : "Calles: trazo recto";
  crearMapa();
  leyenda();
  mostrarPedidos(S.pedidos);
  redibujar();
  centrar();
  eventos();
}

function cambiarTab(i) {
  simPausar();
  S.tab = i;
  document.querySelectorAll(".pestanas button").forEach((b) => b.classList.toggle("activa", +b.dataset.tab === i));
  document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("activa", +p.dataset.pane === i));
  if (i === 6) {
    mapa.addLayer(L_vivo);
    limpiarMapa();
    if (S.sim.existe) {
      simPintar(py("sim_estado", true));
      $("#mapa-titulo").hidden = false;
      $("#mapa-titulo").textContent = "En vivo · " + $("#f-plan").value;
    }
  } else {
    mapa.removeLayer(L_vivo);
    S.entregados = new Set();
    limpiarMapa();
  }
}

function ocupado(btn, fn) {
  btn.disabled = true;
  document.body.style.cursor = "wait";
  setTimeout(() => {
    try { fn(); } finally { btn.disabled = false; document.body.style.cursor = ""; }
  }, 20);
}

function eventos() {
  document.querySelectorAll(".pestanas button").forEach((b) => b.addEventListener("click", () => cambiarTab(+b.dataset.tab)));
  $("#f-fondo").addEventListener("change", (e) => cambiarFondo(e.target.value));
  $("#f-nombres").addEventListener("change", redibujar);
  $("#b-centrar").addEventListener("click", centrar);
  $("#f-reales").addEventListener("change", (e) => {
    simReiniciar();
    const r = py("distancias_reales", e.target.checked);
    for (const c of S.calles) c.metros = r.metros[clave(c.a, c.b)];
    aplicarPedidos(r, false);
    limpiarMapa();
    estado(r.mensaje);
  });
  $("#btn-equipo").addEventListener("click", () => $("#dlg-equipo").showModal());

  // 1. pedidos
  $("#tb-pedidos").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-id]");
    if (!tr) return;
    const id = tr.dataset.id;
    S.seleccion.has(id) ? S.seleccion.delete(id) : S.seleccion.add(id);
    tr.classList.toggle("sel");
    const p = S.pedidos.find((x) => x.id === id);
    if (p) { S.resaltados = new Set(S.pedidos.filter((x) => S.seleccion.has(x.id)).map((x) => x.lugar)); redibujar(); }
  });
  $("#b-agregar").addEventListener("click", () => {
    const r = py("agregar", $("#f-cliente").value, $("#f-lugar").value, +$("#f-prio").value, +$("#f-peso").value, +$("#f-valor").value);
    if (aplicarPedidos(r)) estado(r.mensaje);
  });
  $("#b-eliminar").addEventListener("click", () => {
    if (!S.seleccion.size) { estado("Seleccione uno o más pedidos en la tabla (clic en la fila)."); return; }
    aplicarPedidos(py("eliminar", [...S.seleccion]));
  });
  $("#b-restaurar").addEventListener("click", () => { aplicarPedidos(py("restaurar")); limpiarMapa(); });
  $("#b-aleatorios").addEventListener("click", () => aplicarPedidos(py("aleatorios")));
  $("#b-ordenar").addEventListener("click", () => aplicarPedidos(py("ordenar", $("#f-criterio").value, $("#f-alg").value)));
  $("#b-binaria").addEventListener("click", () => {
    const r = py("buscar_id", $("#f-id").value);
    $("#r-pedidos").textContent = r.mensaje;
    mostrarPedidos(S.pedidos);
    if (r.encontrado) {
      S.seleccion = new Set([r.encontrado]);
      mostrarPedidos(S.pedidos);
      const tr = document.querySelector(`#tb-pedidos tr[data-id="${r.encontrado}"]`);
      tr && tr.scrollIntoView({ block: "nearest" });
      ponerCapa(r.capa);
    }
  });
  $("#b-sector").addEventListener("click", () => {
    const r = py("buscar_sector", $("#f-sector").value);
    mostrarPedidos(r.filtrados);
    $("#r-pedidos").textContent = r.mensaje + " Pulse «Ordenar» para ver todos.";
    ponerCapa(r.capa);
  });

  // 2. voraz
  const pintarReps = (filas) => tabla("#tb-reps", ["Repartidor", "Vehículo", "Base", "Carga", "Pedidos"],
    filas.map((f) => [`<span class="punto" style="background:${f.color}"></span>${f.id}`, f.vehiculo, esc(f.base), f.carga, `<span class="mono">${f.pedidos}</span>`]));
  $("#b-v-asignar").addEventListener("click", () => {
    const r = py("voraz_asignar");
    pintarReps(r.tabla); $("#t-voraz").textContent = r.texto; ponerCapa(r.capa);
  });
  $("#b-v-rutas").addEventListener("click", () => {
    const r = py("voraz_rutas");
    if (r.tabla) pintarReps(r.tabla);
    $("#t-voraz").textContent = r.texto; ponerCapa(r.capa);
  });

  // 3. divide y vencerás
  $("#b-dyv").addEventListener("click", (e) => ocupado(e.target, () => {
    const r = py("dividir", +$("#f-zonas").value);
    if (r.error) return alert(r.error);
    $("#t-dyv").textContent = r.texto; S.bases = r.bases; S.capa = r.capa; S.resaltados = new Set(); redibujar();
  }));

  // 4. programación dinámica
  const pintarMoch = (filas) => tabla("#tb-moch", ["Método", "Valor S/.", "Peso kg", "Pedidos", "ms"],
    filas.map((f) => [f.metodo, f.valor, f.peso, `<span class="mono">${f.pedidos}</span>`, f.ms]));
  $("#f-cap").addEventListener("change", () => py("reset_carga"));
  $("#b-mochila").addEventListener("click", () => {
    const r = py("mochila", +$("#f-cap").value);
    pintarMoch(r.tabla); $("#t-pd").textContent = r.texto; ponerCapa(r.capa);
  });
  $("#b-hk").addEventListener("click", (e) => ocupado(e.target, () => {
    const r = py("ruta_optima", +$("#f-cap").value);
    if (r.error) return alert(r.error);
    if (r.tabla) pintarMoch(r.tabla);
    $("#t-pd").textContent = r.texto; ponerCapa(r.capa);
  }));

  // 5. backtracking
  $("#b-bt-ej").addEventListener("click", () => {
    S.cerradas = new Set(S.datos.cerradas_ejemplo.map(([a, b]) => claveCalle(a, b)));
    refrescarCerradas(); redibujar();
  });
  $("#b-bt-abrir").addEventListener("click", () => { S.cerradas = new Set(); refrescarCerradas(); redibujar(); });
  $("#b-bt").addEventListener("click", (e) => ocupado(e.target, () => {
    const r = py("bt_todas", $("#f-origen").value, $("#f-destino").value, cerradasLista());
    if (r.error) return alert(r.error);
    $("#r-bt").textContent = r.mensaje;
    tabla("#tb-bt", ["#", "Distancia (m)", "Lugares", "Recorrido"],
      (r.filas || []).map((f) => [f.n, fmt(f.dist), f.lugares, `<span class="envolver">${esc(f.recorrido)}</span>`]));
    ponerCapa(r.capa);
  }));
  $("#b-bt-poda").addEventListener("click", () => {
    const r = py("bt_poda", $("#f-origen").value, $("#f-destino").value, cerradasLista());
    if (r.error) return alert(r.error);
    $("#r-bt").textContent = r.mensaje; ponerCapa(r.capa);
  });
  $("#tb-bt").addEventListener("click", (e) => {
    const tr = e.target.closest("tbody tr");
    if (!tr) return;
    document.querySelectorAll("#tb-bt tr.sel").forEach((x) => x.classList.remove("sel"));
    tr.classList.add("sel");
    ponerCapa(py("bt_ver", +tr.dataset.i).capa);
  });

  // 6. comparación
  $("#b-comparar").addEventListener("click", (e) => {
    $("#r-cmp").textContent = "Ejecutando experimentos…";
    ocupado(e.target, () => {
      const r = py("comparar");
      tabla("#tb-cmp", ["n", "Voraz (m)", "Óptimo (m)", "Exceso %", "t Voraz", "t PD", "t BT"],
        r.rutas.map((f) => [f.n, fmt(f.costo_voraz), fmt(f.costo_optimo), fmt(f.exceso, 1), fmt(f.t_voraz, 3), fmt(f.t_pd, 2), f.t_bt == null ? "–" : fmt(f.t_bt, 2)]));
      tabla("#tb-cmp2", ["n", "Valor voraz", "Valor PD", "Pérdida %", "t Voraz", "t PD"],
        r.mochila.map((f) => [f.n, fmt(f.valor_voraz, 1), fmt(f.valor_pd, 1), fmt(f.perdida, 2), fmt(f.t_voraz, 3), fmt(f.t_pd, 3)]));
      grafico(r.rutas);
      $("#t-cmp").hidden = false;
      $("#r-cmp").textContent = `Tiempos en milisegundos · experimentos completos en ${fmt(r.ms / 1000, 1)} s.`;
    });
  });

  // 7. en vivo
  $("#f-vel").addEventListener("input", (e) => ($("#l-vel").textContent = "× " + e.target.value));
  $("#b-play").addEventListener("click", simPlay);
  $("#b-pausa").addEventListener("click", simPausar);
  $("#b-reini").addEventListener("click", () => { simReiniciar(); limpiarMapa(); });
  $("#b-incid").addEventListener("click", simIncidente);
  $("#f-plan").addEventListener("change", () => { simReiniciar(); limpiarMapa(); });
}

// ---------------------------------------------------------------- gráfico de tiempos (escala log)
function grafico(filas) {
  const W = 520, H = 210, m = { l: 46, r: 12, t: 10, b: 30 };
  const series = [["t_voraz", "Voraz (vecino más cercano)", "#1BAF7A"], ["t_pd", "PD (Held-Karp)", "#2A78D6"], ["t_bt", "Backtracking", "#C8553D"]];
  const vals = filas.flatMap((f) => series.map(([k]) => f[k]).filter((v) => v != null && v > 0));
  const lo = Math.floor(Math.log10(Math.min(...vals))), hi = Math.ceil(Math.log10(Math.max(...vals)));
  const ns = filas.map((f) => f.n);
  const x = (n) => m.l + (n - ns[0]) / (ns[ns.length - 1] - ns[0]) * (W - m.l - m.r);
  const y = (v) => H - m.b - (Math.log10(v) - lo) / (hi - lo) * (H - m.t - m.b);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Tiempo de cálculo por número de paradas">`;
  for (let e = lo; e <= hi; e++) {
    svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(10 ** e)}" y2="${y(10 ** e)}" stroke="#EEE8DC"/>` +
      `<text x="${m.l - 6}" y="${y(10 ** e) + 4}" text-anchor="end" font-size="10.5" fill="#6B777A">${e >= 0 ? fmt(10 ** e) : (10 ** e).toString()}</text>`;
  }
  for (const n of ns) svg += `<text x="${x(n)}" y="${H - m.b + 16}" text-anchor="middle" font-size="10.5" fill="#6B777A">${n}</text>`;
  svg += `<text x="${(W + m.l) / 2}" y="${H - 2}" text-anchor="middle" font-size="10.5" fill="#6B777A">paradas (n)</text>`;
  svg += `<text x="10" y="${m.t + 6}" font-size="10.5" fill="#6B777A" transform="rotate(-90 10 ${m.t + 6})" text-anchor="end">ms (log)</text>`;
  for (const [k, , c] of series) {
    const pts = filas.filter((f) => f[k] != null && f[k] > 0).map((f) => [x(f.n), y(f[k])]);
    svg += `<polyline fill="none" stroke="${c}" stroke-width="2.2" points="${pts.map((p) => p.join(",")).join(" ")}"/>`;
    svg += pts.map(([a, b]) => `<circle cx="${a}" cy="${b}" r="3" fill="${c}"/>`).join("");
  }
  svg += "</svg>";
  $("#graf-cmp").innerHTML = `<div class="ley">${series.map(([, t, c]) => `<span><span class="punto" style="background:${c}"></span>${t}</span>`).join("")}</div>${svg}`;
}

// ---------------------------------------------------------------- simulación en vivo
function simCrear() {
  L_vivo.clearLayers();
  for (const k in moviles) delete moviles[k];
  for (const k in rutasVivas) delete rutasVivas[k];
  $("#t-sim").textContent = "";
  S.sim.existe = true;
  S.entregados = new Set();
  const r = py("sim_crear", $("#f-plan").value, cerradasLista());
  S.capa = null; S.resaltados = new Set();
  simPintar(r);
  $("#mapa-titulo").hidden = false;
  $("#mapa-titulo").textContent = "En vivo · " + $("#f-plan").value;
}

function simPlay() {
  if (!S.sim.existe || S.sim.terminada) { S.sim.terminada = false; simCrear(); }
  S.sim.activa = true;
  S.sim.prev = performance.now();
  if (!S.sim.job) S.sim.job = setTimeout(simTick, 40);
}
function simPausar() {
  S.sim.activa = false;
  if (S.sim.job) { clearTimeout(S.sim.job); S.sim.job = null; }
}
function simReiniciar() {
  simPausar();
  S.sim.existe = false; S.sim.terminada = false;
  py("sim_reiniciar");
  if (L_vivo) L_vivo.clearLayers();
  for (const k in moviles) delete moviles[k];
  for (const k in rutasVivas) delete rutasVivas[k];
  S.entregados = new Set();
  $("#tb-sim").innerHTML = "";
  $("#l-reloj").textContent = "08:00";
  $("#t-sim").textContent = "Pulse ▶ para empezar.";
}

function simTick() {
  S.sim.job = null;
  if (!S.sim.activa) return;
  const ahora = performance.now();
  const dt = Math.min(0.25, (ahora - S.sim.prev) / 1000);
  S.sim.prev = ahora;
  S.sim.tick++;
  const r = py("sim_avanzar", dt * +$("#f-vel").value, S.sim.tick % 4 === 0);
  simPintar(r);
  if (r.terminada) {
    S.sim.activa = false; S.sim.terminada = true;
    estado(r.resumen);
    return;
  }
  S.sim.job = setTimeout(simTick, 40);
}

function simPintar(r) {
  if (!r || !r.activa) return;
  for (const m of r.moviles) {
    if (!moviles[m.id]) {
      moviles[m.id] = L.marker(m.pos, { icon: icono(`<div class="ic-movil" style="background:${m.color}">${m.id}</div>`, 30, 30), zIndexOffset: 1000, interactive: false }).addTo(L_vivo);
    } else moviles[m.id].setLatLng(m.pos);
    if (m.ruta) {
      if (rutasVivas[m.id]) rutasVivas[m.id].setLatLngs(m.ruta.length > 1 ? m.ruta : []);
      else rutasVivas[m.id] = L.polyline(m.ruta.length > 1 ? m.ruta : [], { pane: "vivo", color: m.color, weight: 6, opacity: 0.85, interactive: false, lineCap: "round", lineJoin: "round" }).addTo(L_vivo);
    }
  }
  $("#l-reloj").textContent = r.reloj;
  tabla("#tb-sim", ["Rep.", "Estado", "Entregas", "Recorrido", "Falta"],
    r.moviles.map((m) => [`<span class="punto" style="background:${m.color}"></span>${m.id}`, esc(m.fila.estado), m.fila.entregas, m.fila.recorrido, m.fila.falta]));
  if (r.eventos.length) {
    const pre = $("#t-sim");
    pre.textContent = r.eventos.slice().reverse().join("\n") + (pre.textContent ? "\n" + pre.textContent : "");
  }
  const nuevasC = new Set(r.cerradas.map(([a, b]) => claveCalle(a, b)));
  const cambioC = nuevasC.size !== S.cerradas.size || [...nuevasC].some((k) => !S.cerradas.has(k));
  const cambioE = r.entregados.length !== S.entregados.size;
  if (cambioC) { S.cerradas = nuevasC; refrescarCerradas(); }
  if (cambioE) S.entregados = new Set(r.entregados);
  if (cambioC || cambioE) redibujar();
}

function simClicCalle(c) {
  if (!S.sim.existe) {
    const k = clave(c.a, c.b);
    S.cerradas.has(k) ? S.cerradas.delete(k) : S.cerradas.add(k);
    refrescarCerradas(); redibujar();
    estado(`${c.nombre}: ${S.cerradas.has(k) ? "cerrada" : "abierta"}.`);
    return;
  }
  simPintar(py("sim_toggle", c.a, c.b));
}

function simIncidente() {
  if (!S.sim.existe) simPlay();
  const r = py("sim_incidente");
  if (r.error) { estado(r.error); return; }
  simPintar(r);
}

iniciar();
