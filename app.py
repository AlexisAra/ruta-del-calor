"""
Ruta del Calor - MVP Sprint 1 (prototipo Streamlit + Folium)
Visor centrado en la comuna de Pudahuel con capas activables.

- Límite comunal: archivo OFICIAL en  data/pudahuel.geojson  (ver instrucciones).
- Temperatura y población > 65 años: datos SIMULADOS (demo), generados
  siempre DENTRO del límite de la comuna.

Ejecutar:  python -m streamlit run app.py
"""
import json
import random
from pathlib import Path

import folium
import streamlit as st
from folium.plugins import HeatMap
from shapely.geometry import Point, box, shape
from shapely.ops import unary_union
from streamlit_folium import st_folium

st.set_page_config(page_title="Ruta del Calor", page_icon="🔥", layout="wide")

RUTA_LIMITE = Path(__file__).parent / "data" / "pudahuel.geojson"
NOMBRE_COMUNA = "pudahuel"
# Solo se usa si falta el archivo oficial (caja aproximada, NO es el límite real)
CAJA_FALLBACK = (-70.88, -33.50, -70.68, -33.36)  # minx, miny, maxx, maxy


# ---------------------------------------------------------------- Límite comunal
@st.cache_data
def cargar_limite(ruta: str):
    """Lee el GeoJSON y se queda con Pudahuel (acepta archivo de todo Chile)."""
    with open(ruta, encoding="utf-8") as f:
        data = json.load(f)
    feats = data["features"] if data.get("type") == "FeatureCollection" else [data]
    elegidas = []
    for ft in feats:
        props = ft.get("properties") or {}
        texto = " ".join(str(v) for v in props.values()).lower()
        if NOMBRE_COMUNA in texto:
            elegidas.append(ft)
    if not elegidas and len(feats) == 1:
        elegidas = feats  # archivo ya filtrado y sin atributos
    if not elegidas:
        return None
    return {"type": "FeatureCollection", "features": elegidas}


def obtener_geometria():
    """Devuelve (geometria, geojson_dict | None, es_oficial)."""
    if RUTA_LIMITE.exists():
        fc = cargar_limite(str(RUTA_LIMITE))
        if fc is None:
            st.error(
                "El archivo data/pudahuel.geojson no contiene la comuna de Pudahuel."
            )
            st.stop()
        geom = unary_union([shape(f["geometry"]) for f in fc["features"]])
        minx, miny, maxx, maxy = geom.bounds
        if max(abs(minx), abs(maxx)) > 180 or max(abs(miny), abs(maxy)) > 90:
            st.error(
                "El GeoJSON está en coordenadas proyectadas (UTM). "
                "Expórtalo de nuevo en WGS84 (lat/lon). Ver instrucciones."
            )
            st.stop()
        return geom, fc, True
    return box(*CAJA_FALLBACK), None, False


# ---------------------------------------------------------------- Datos simulados
def punto_dentro(rng, geom):
    minx, miny, maxx, maxy = geom.bounds
    while True:
        p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        if geom.contains(p):
            return p


@st.cache_data
def generar_focos(_geom, n_focos: int = 5, seed: int = 3):
    rng = random.Random(seed)
    focos = []
    for _ in range(n_focos):
        p = punto_dentro(rng, _geom)
        focos.append((p.y, p.x))
    return focos


@st.cache_data
def generar_puntos_calor(_geom, focos, n_por_foco: int = 40, seed: int = 42):
    """Temperatura simulada (°C) a las 16:00 hrs, solo dentro de la comuna."""
    rng = random.Random(seed)
    minx, miny, maxx, maxy = _geom.bounds
    sigma = 0.05 * max(maxx - minx, maxy - miny)
    puntos = []
    for lat0, lon0 in focos:
        creados, intentos = 0, 0
        while creados < n_por_foco and intentos < n_por_foco * 30:
            intentos += 1
            lat, lon = rng.gauss(lat0, sigma), rng.gauss(lon0, sigma)
            if not _geom.contains(Point(lon, lat)):
                continue
            dist = ((lat - lat0) ** 2 + (lon - lon0) ** 2) ** 0.5
            temp = round(41 - (dist / (2 * sigma)) * 6 + rng.uniform(-1, 1), 1)
            puntos.append({"lat": lat, "lon": lon, "temp": temp})
            creados += 1
    return puntos


@st.cache_data
def generar_puntos_mayores(_geom, focos, n: int = 60, seed: int = 7):
    """Población > 65 años simulada, solo dentro de la comuna."""
    rng = random.Random(seed)
    minx, miny, maxx, maxy = _geom.bounds
    sigma = 0.07 * max(maxx - minx, maxy - miny)
    puntos = []
    while len(puntos) < n:
        lat0, lon0 = rng.choice(focos)
        lat, lon = rng.gauss(lat0, sigma), rng.gauss(lon0, sigma)
        if _geom.contains(Point(lon, lat)):
            puntos.append({"lat": lat, "lon": lon, "pct": rng.randint(8, 35)})
    return puntos


def color_por_temperatura(t: float) -> str:
    if t >= 40:
        return "#d7191c"
    if t >= 38:
        return "#f46d43"
    return "#fdae61"


# ---------------------------------------------------------------- Datos base
geom, geojson_limite, es_oficial = obtener_geometria()
focos = generar_focos(geom)

# ---------------------------------------------------------------- Panel lateral
st.sidebar.title("🔥 Ruta del Calor")
st.sidebar.caption("MVP Sprint 1 · Comuna de Pudahuel")
st.sidebar.markdown("### Capas")

ver_limite = st.sidebar.checkbox("Límite comunal", value=True)
ver_puntos = st.sidebar.checkbox("Temperatura 16:00 hrs (puntos)", value=True)
ver_heat = st.sidebar.checkbox("Mapa de calor (densidad)", value=False)
ver_mayores = st.sidebar.checkbox("Población > 65 años (Censo)", value=False)

estilo_base = st.sidebar.selectbox(
    "Mapa base", ["OpenStreetMap", "CartoDB positron", "CartoDB dark_matter"]
)

st.sidebar.markdown("### Filtro")
temp_min = st.sidebar.slider("Temperatura mínima (°C)", 34.0, 42.0, 34.0, 0.5)

st.sidebar.markdown("---")
st.sidebar.info(
    "⚠️ Temperatura y población son datos simulados para la demo. "
    "Fuentes reales a integrar: CR2, Censo 2024 (INE), Casen."
)

# ---------------------------------------------------------------- Mapa
puntos = [p for p in generar_puntos_calor(geom, focos) if p["temp"] >= temp_min]

centro = geom.centroid
mapa = folium.Map(
    location=[centro.y, centro.x],
    zoom_start=12,
    tiles=estilo_base,
    control_scale=True,
)
minx, miny, maxx, maxy = geom.bounds
mapa.fit_bounds([[miny, minx], [maxy, maxx]])

if ver_limite:
    if geojson_limite is not None:
        folium.GeoJson(
            geojson_limite,
            name="Límite comunal",
            style_function=lambda _: {
                "color": "#222222",
                "weight": 3,
                "fillOpacity": 0.03,
            },
            tooltip="Comuna de Pudahuel",
        ).add_to(mapa)
    else:
        folium.Rectangle(
            bounds=[[miny, minx], [maxy, maxx]],
            color="#888888",
            weight=2,
            dash_array="6",
            tooltip="Caja aproximada (falta el límite oficial)",
        ).add_to(mapa)

if ver_puntos:
    capa = folium.FeatureGroup(name="Temperatura 16:00")
    for p in puntos:
        folium.CircleMarker(
            location=[p["lat"], p["lon"]],
            radius=6,
            color=color_por_temperatura(p["temp"]),
            fill=True,
            fill_opacity=0.75,
            weight=1,
            tooltip=f"{p['temp']} °C (16:00 hrs, simulado)",
        ).add_to(capa)
    capa.add_to(mapa)

if ver_heat and puntos:
    HeatMap(
        [[p["lat"], p["lon"], p["temp"] - 33] for p in puntos],
        name="Densidad de calor",
        radius=22,
        blur=18,
    ).add_to(mapa)

if ver_mayores:
    capa = folium.FeatureGroup(name="Mayores de 65")
    for p in generar_puntos_mayores(geom, focos):
        folium.CircleMarker(
            location=[p["lat"], p["lon"]],
            radius=4 + p["pct"] / 8,
            color="#4575b4",
            fill=True,
            fill_opacity=0.5,
            weight=1,
            tooltip=f"{p['pct']}% población > 65 años (simulado)",
        ).add_to(capa)
    capa.add_to(mapa)

leyenda = """
<div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
 background: white; padding: 10px 12px; border: 1px solid #999;
 border-radius: 6px; font-size: 13px; color: #222;">
<b>Temperatura 16:00</b><br>
<span style="color:#d7191c">●</span> ≥ 40 °C<br>
<span style="color:#f46d43">●</span> 38 – 40 °C<br>
<span style="color:#fdae61">●</span> &lt; 38 °C<br>
<span style="color:#4575b4">●</span> Población &gt; 65 años
</div>
"""
mapa.get_root().html.add_child(folium.Element(leyenda))

# ---------------------------------------------------------------- Página principal
st.title("Ruta del Calor – Visor territorial")
st.caption("Islas de calor urbano y vulnerabilidad social · Pudahuel (MVP)")

if not es_oficial:
    st.warning(
        "Falta el límite oficial: guarda el archivo como data/pudahuel.geojson. "
        "Mientras tanto se muestra una caja aproximada que NO es el límite real."
    )

c1, c2, c3 = st.columns(3)
c1.metric("Puntos visibles", len(puntos))
c2.metric("Temp. máxima", f"{max((p['temp'] for p in puntos), default=0)} °C")
c3.metric(
    "Temp. promedio",
    f"{(sum(p['temp'] for p in puntos) / len(puntos)):.1f} °C" if puntos else "-",
)

st_folium(mapa, width=None, height=600, returned_objects=[])

with st.expander("Fuente y fecha de los datos"):
    st.write(
        "**Límite comunal:** "
        + (
            "archivo oficial (División Político Administrativa)."
            if es_oficial
            else "pendiente (caja aproximada)."
        )
    )
    st.write(
        "**Temperatura y población > 65 años:** datos **simulados** para la demo "
        "del Sprint 1. En el Sprint 2 se reemplazarán por datos reales "
        "(CR2, Censo 2024 del INE, Casen)."
    )
