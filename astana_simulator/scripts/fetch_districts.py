"""Refresh the five OSM district outlines. Not used during app startup.

Only public OSM data is downloaded; output is a local, attributed GeoJSON file.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.parse
import urllib.request

DISTRICTS = {
    3479876: "Есиль", 3482819: "Алматы", 3486954: "Сарыарка",
    8593081: "Байконур", 20593940: "Нура",
}
ENDPOINT = "https://overpass-api.de/api/interpreter"


def join_rings(segments):
    segments = [list(segment) for segment in segments]
    rings = []
    while segments:
        ring = segments.pop(0)
        while ring[0] != ring[-1]:
            for index, segment in enumerate(segments):
                if ring[-1] == segment[0]:
                    ring.extend(segment[1:])
                elif ring[-1] == segment[-1]:
                    ring.extend(list(reversed(segment))[1:])
                else:
                    continue
                segments.pop(index)
                break
            else:
                raise ValueError("OSM boundary is not a closed ring; refusing to invent a segment")
        if len(ring) < 4:
            raise ValueError("Invalid ring")
        rings.append(ring)
    return rings


def contains(point, ring):
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def convert_relation(relation):
    segments = {"outer": [], "inner": []}
    for member in relation["members"]:
        if member["type"] != "way":
            continue
        role = member.get("role") or "outer"
        if role in segments:
            segments[role].append([(p["lon"], p["lat"]) for p in member["geometry"]])
    polygons = [[ring] for ring in join_rings(segments["outer"])]
    for hole in join_rings(segments["inner"]):
        for polygon in polygons:
            if contains(hole[0], polygon[0]):
                polygon.append(hole)
                break
        else:
            raise ValueError("Unassigned inner ring")
    if not polygons:
        raise ValueError("Missing geometry")
    return {
        "type": "Feature", "id": str(relation["id"]),
        "properties": {
            "name": DISTRICTS[relation["id"]], "osm_relation": relation["id"],
            "osm_name": relation["tags"].get("name:ru", relation["tags"]["name"]),
            "source_url": f"https://www.openstreetmap.org/relation/{relation['id']}",
        },
        "geometry": {"type": "MultiPolygon", "coordinates": polygons},
    }


def main():
    query = f"[out:json][timeout:40];relation(id:{','.join(map(str, DISTRICTS))});out geom;"
    request = urllib.request.Request(ENDPOINT,
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "AstanaHackathonMap/1.0"})
    with urllib.request.urlopen(request, timeout=55) as response:
        data = json.load(response)
    relations = {element["id"]: element for element in data["elements"]}
    if set(relations) != set(DISTRICTS):
        raise ValueError("Not all five districts were returned")
    result = {
        "type": "FeatureCollection", "name": "Astana case districts",
        "attribution": "© OpenStreetMap contributors",
        "license": "ODbL-1.0", "license_url": "https://www.openstreetmap.org/copyright",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "osm_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
        "query": query, "endpoint": ENDPOINT,
        "features": [convert_relation(relations[i]) for i in DISTRICTS],
    }
    output = Path(__file__).resolve().parents[1] / "data" / "astana_districts.geojson"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {len(result['features'])} district boundaries to {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
