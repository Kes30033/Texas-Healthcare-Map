"""Build the hand-drawn map layers (Texas counties, neighboring states, interstates and U.S. highways)
from U.S. Census Bureau boundary files. Used by the "Simple" map style, which needs no map images.

Downloads the source shapefiles into data/basemap/source/ (not saved to git) on first run and
writes data/basemap/basemap.json.

usage: python scripts/make_basemap.py
"""
import io
import json
import urllib.request
import zipfile
from pathlib import Path

import shapefile
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "basemap"
SRC = OUT / "source"
FILES = {
    "counties": "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip",
    "states": "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip",
    "roads": "https://www2.census.gov/geo/tiger/TIGER2023/PRISECROADS/tl_2023_48_prisecroads.zip",
}
BBOX = box(-108.5, 24.8, -92.0, 37.6)


def fetch(name):
    path = SRC / FILES[name].rsplit("/", 1)[1]
    if not path.exists():
        SRC.mkdir(parents=True, exist_ok=True)
        print("downloading", path.name)
        urllib.request.urlretrieve(FILES[name], path)
    return path


def read(name):
    z = zipfile.ZipFile(fetch(name))
    base = [n[:-4] for n in z.namelist() if n.endswith(".shp")][0]
    r = shapefile.Reader(shp=io.BytesIO(z.read(base + ".shp")), dbf=io.BytesIO(z.read(base + ".dbf")),
                         shx=io.BytesIO(z.read(base + ".shx")))
    fields = [f[0] for f in r.fields[1:]]
    for sr in r.iterShapeRecords():
        yield dict(zip(fields, sr.record)), shape(sr.shape.__geo_interface__)


def rnd(g, p=4):
    def fix(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], p), round(c[1], p)]
        return [fix(x) for x in c]
    m = mapping(g)
    return {"type": m["type"], "coordinates": fix(m["coordinates"])}


def label_point(g):
    part = max(g.geoms, key=lambda x: x.area) if g.geom_type == "MultiPolygon" else g
    p = part.representative_point()
    return [round(p.y, 3), round(p.x, 3)]


def main():
    counties = []
    for rec, g in read("counties"):
        if rec["STATEFP"] == "48":
            counties.append({"type": "Feature",
                             "properties": {"name": rec["NAME"], "lp": label_point(g)},
                             "geometry": rnd(g.simplify(0.003, preserve_topology=True), 3)})
    neighbors = []
    for rec, g in read("states"):
        if rec["STUSPS"] in ("NM", "OK", "AR", "LA", "CO", "KS"):
            s = g.intersection(BBOX).simplify(0.01, preserve_topology=True)
            if not s.is_empty:
                neighbors.append({"type": "Feature", "properties": {"name": rec["NAME"]}, "geometry": rnd(s, 3)})
    roads = {}
    for rec, g in read("roads"):
        kind = "primary" if rec["MTFCC"] == "S1100" else "us" if rec["RTTYP"] == "U" else None
        if kind:
            roads.setdefault((rec["FULLNAME"] or "", kind), []).append(g)
    road_feats = [{"type": "Feature", "properties": {"name": name, "kind": kind},
                   "geometry": rnd(unary_union(gs).simplify(0.004 if kind == "us" else 0.003), 3)}
                  for (name, kind), gs in roads.items()]
    out = {"counties": counties, "neighbors": neighbors, "roads": road_feats}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "basemap.json").write_text(json.dumps(out, separators=(",", ":")))
    print(len(counties), "counties,", len(road_feats), "roads ->", OUT / "basemap.json",
          f"({(OUT / 'basemap.json').stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
