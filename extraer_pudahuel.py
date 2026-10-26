"""
Extrae la comuna de Pudahuel desde data/comunas.json (todo Chile)
y guarda un archivo liviano: data/pudahuel.geojson

Si las coordenadas vienen en metros, las convierte a latitud/longitud:
  1) usando el sistema de coordenadas (.prj) que viene dentro de comunas_final.zip
  2) si no se puede, probando sistemas comunes de Chile y quedándose con el
     que deja a Pudahuel en su lugar real.

Uso (en la carpeta del proyecto, con comunas_final.zip y data/comunas.json):
    python -m pip install pyproj shapely
    python extraer_pudahuel.py
"""
import json
import sys
import zipfile
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

RAIZ = Path(__file__).parent
CARPETA = RAIZ / "data"
ENTRADA = CARPETA / "comunas.json"
SALIDA = CARPETA / "pudahuel.geojson"
ZIP_ORIGINAL = RAIZ / "comunas_final.zip"
NOMBRE = "pudahuel"

# Donde debe quedar Pudahuel (lon_min, lat_min, lon_max, lat_max)
CAJA_ESPERADA = (-71.1, -33.7, -70.5, -33.2)

# Sistemas comunes en Chile para probar si no hay .prj
CANDIDATOS = [
    "EPSG:32719",  # WGS84 / UTM 19S
    "EPSG:32718",  # WGS84 / UTM 18S
    "EPSG:31979",  # SIRGAS 2000 / UTM 19S
    "EPSG:31978",  # SIRGAS 2000 / UTM 18S
    "EPSG:24879",  # PSAD56 / UTM 19S
    "EPSG:24878",  # PSAD56 / UTM 18S
    "EPSG:5361",   # SIRGAS-Chile / UTM 19S
    "EPSG:5362",   # SIRGAS-Chile / UTM 18S
    "EPSG:3857",   # Web Mercator
]

if not ENTRADA.exists():
    sys.exit(f"No encuentro {ENTRADA}")

print("Leyendo archivo (puede tardar un poco)...")
with open(ENTRADA, encoding="utf-8") as f:
    data = json.load(f)

feats = data["features"] if data.get("type") == "FeatureCollection" else [data]
print(f"Comunas en el archivo: {len(feats)}")


def textos(ft):
    return [str(v).strip().lower() for v in (ft.get("properties") or {}).values()]


elegidas = [ft for ft in feats if NOMBRE in textos(ft)]
if not elegidas:
    elegidas = [ft for ft in feats if any(NOMBRE in t for t in textos(ft))]
if not elegidas:
    sys.exit("No encontré la comuna Pudahuel en el archivo.")
print("Encontrada:", (elegidas[0].get("properties") or {}).get("Comuna", "Pudahuel"))

geom = unary_union([shape(ft["geometry"]) for ft in elegidas])


def en_pudahuel(g) -> bool:
    c = g.centroid
    x0, y0, x1, y1 = CAJA_ESPERADA
    return x0 <= c.x <= x1 and y0 <= c.y <= y1


minx, miny, maxx, maxy = geom.bounds
proyectado = max(abs(minx), abs(maxx)) > 180 or max(abs(miny), abs(maxy)) > 90

if proyectado:
    try:
        from pyproj import CRS, Transformer
    except ImportError:
        sys.exit(
            "Falta pyproj. Ejecuta:  python -m pip install pyproj\n"
            "y vuelve a correr este script."
        )

    def convertir(crs_origen):
        tr = Transformer.from_crs(crs_origen, "EPSG:4326", always_xy=True)
        return transform(tr.transform, geom)

    resultado_geom = None

    # 1) Sistema real desde el .prj del zip original
    if ZIP_ORIGINAL.exists():
        try:
            with zipfile.ZipFile(ZIP_ORIGINAL) as z:
                prjs = [n for n in z.namelist() if n.lower().endswith(".prj")]
                if prjs:
                    wkt = z.read(prjs[0]).decode("utf-8", errors="ignore")
                    crs = CRS.from_wkt(wkt)
                    print(f"Sistema de coordenadas del zip: {crs.name}")
                    g = convertir(crs)
                    if en_pudahuel(g):
                        resultado_geom = g
                    else:
                        print("  -> con ese sistema Pudahuel no cae en su lugar; pruebo otros.")
        except Exception as e:  # noqa: BLE001
            print(f"No pude leer el .prj del zip ({e}); pruebo otros sistemas.")

    # 2) Probar sistemas comunes
    if resultado_geom is None:
        for codigo in CANDIDATOS:
            try:
                g = convertir(codigo)
            except Exception:  # noqa: BLE001
                continue
            if en_pudahuel(g):
                print(f"Sistema detectado: {codigo}")
                resultado_geom = g
                break

    if resultado_geom is None:
        print("Primeras coordenadas del archivo:", list(geom.exterior.coords)[:3]
              if geom.geom_type == "Polygon" else geom.bounds)
        sys.exit(
            "No pude ubicar Pudahuel con ningún sistema conocido.\n"
            "Copia y envía este mensaje completo."
        )
    geom = resultado_geom
elif not en_pudahuel(geom):
    sys.exit(
        f"Las coordenadas ya son lat/lon pero Pudahuel quedó en {geom.centroid.coords[0]}, "
        "fuera de su lugar. Envía este mensaje completo."
    )

# Simplificar (~10 m) para que el archivo sea liviano
geom = geom.simplify(0.0001, preserve_topology=True)

salida = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"comuna": "Pudahuel", "fuente": "BCN"},
            "geometry": mapping(geom),
        }
    ],
}
with open(SALIDA, "w", encoding="utf-8") as f:
    json.dump(salida, f)

b = geom.bounds
c = geom.centroid
print(f"Listo: {SALIDA} ({SALIDA.stat().st_size / 1024:.0f} KB)")
print(f"Centro (lon, lat): {c.x:.4f}, {c.y:.4f}   <- debería ser cerca de -70.80, -33.42")
print(f"Límites (lon/lat): {b[0]:.3f}, {b[1]:.3f} a {b[2]:.3f}, {b[3]:.3f}")