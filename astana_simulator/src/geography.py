"""Local OSM geometry, deterministic choropleth data and selection parsing."""

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from src.data import BASE, POPULATION
from src.model import BASELINE, Scenario

MAP_PATH = Path(__file__).resolve().parents[1] / "data" / "astana_districts.geojson"
LAYERS = {"score": "Районный балл", "gain": "Прирост к базе", "critical": "Критические показатели"}


@lru_cache(maxsize=1)
def load_boundaries() -> dict:
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    if {f["properties"]["name"] for f in data["features"]} != set(BASE):
        raise ValueError("Map districts do not match the case dataset")
    return data


def inside_ring(point, ring) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def inside_geometry(point, geometry) -> bool:
    return any(inside_ring(point, polygon[0]) and not any(inside_ring(point, hole) for hole in polygon[1:])
               for polygon in geometry["coordinates"])


def label_position(geometry) -> list[float]:
    # Search inside the largest polygon, never use an out-of-bound bounding-box center.
    def area(polygon):
        return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon[0], polygon[0][1:])))
    polygon = max(geometry["coordinates"], key=area)
    ring = polygon[0]
    x0, x1 = min(p[0] for p in ring), max(p[0] for p in ring)
    y0, y1 = min(p[1] for p in ring), max(p[1] for p in ring)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    candidates = [(cx, cy)] + [(x0 + (x1 - x0) * i / 25, y0 + (y1 - y0) * j / 25)
                              for i in range(1, 25) for j in range(1, 25)]
    candidates.sort(key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    for point in candidates:
        if inside_geometry(point, geometry):
            return list(point)
    raise ValueError("No interior label position found")


def color_for(value: float, layer: str) -> list[int]:
    if layer == "critical":
        return [206, 104, 74, 155] if value else [46, 129, 115, 135]
    low, high = (45, 80) if layer == "score" else (0, 15)
    t = max(0, min(1, (value - low) / (high - low)))
    start, end = (231, 191, 128), (23, 112, 103)
    return [round(a + (b - a) * t) for a, b in zip(start, end)] + [155]


def map_data(scenario: Scenario | None, *, layer: str, focused: str, before: bool = False) -> tuple[dict, list[dict]]:
    if layer not in LAYERS or focused not in BASE:
        raise ValueError("Unknown map layer or district")
    data = deepcopy(load_boundaries())
    score = BASELINE if scenario is None or before else scenario.score
    indicators = BASE if scenario is None or before else scenario.indicators
    labels = []
    for feature in data["features"]:
        name = feature["properties"]["name"]
        value = score.district_scores[name]
        gain = value - BASELINE.district_scores[name]
        critical = sum(v < 40 for v in indicators[name].values())
        measure = {"score": value, "gain": gain, "critical": critical}[layer]
        feature["properties"].update(
            score=round(value, 2), gain=round(gain, 2), critical=critical,
            population=f"{POPULATION[name]:.0%}",
            color=color_for(measure, layer),
            outline=[24, 70, 65, 255] if name == focused else [255, 255, 255, 230],
            line_width=3 if name == focused else 1.2,
            tooltip=f"{name}\nРайонный балл: {value:.2f} / 100\nПрирост: {gain:+.2f}\nКритических: {critical}\nНажмите, чтобы выбрать район",
        )
        labels.append({"name": name, "position": label_position(feature["geometry"]),
                       "text": f"{name}\n{value:.1f}", "tooltip": feature["properties"]["tooltip"]})
    return data, labels


def district_from_event(event: dict) -> str | None:
    """Only accept known district names from pickable layers, never arbitrary events."""
    objects = event.get("selection", {}).get("objects", {})
    for layer in ("district-polygons", "district-labels"):
        for item in objects.get(layer, []):
            name = item.get("properties", {}).get("name") or item.get("name")
            if name in BASE:
                return name
    return None
