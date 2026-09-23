from copy import deepcopy

import pytest

from src.data import BASE
from src.geography import district_from_event, inside_geometry, label_position, load_boundaries, map_data
from src.model import BASELINE, EXAMPLE, simulate_decisions
from scripts.fetch_districts import join_rings


def test_geography_is_attributed_and_contains_five_real_districts():
    data = load_boundaries()
    assert data["license"] == "ODbL-1.0"
    assert data["osm_timestamp"]
    assert len(data["features"]) == 5
    assert {f["properties"]["name"] for f in data["features"]} == set(BASE)
    for feature in data["features"]:
        assert feature["properties"]["source_url"].startswith("https://www.openstreetmap.org/relation/")
        assert inside_geometry(label_position(feature["geometry"]), feature["geometry"])
        for polygon in feature["geometry"]["coordinates"]:
            for ring in polygon:
                assert ring[0] == ring[-1]
                assert len(ring) >= 4
                assert all(70.5 < lon < 72.5 and 50.5 < lat < 51.8 for lon, lat in ring)


def test_map_matches_exact_score_and_does_not_mutate_geography():
    original = deepcopy(load_boundaries())
    scenario = simulate_decisions(EXAMPLE)
    data, labels = map_data(scenario, layer="gain", focused="Нура")
    assert load_boundaries() == original
    assert len(labels) == 5
    for feature in data["features"]:
        props = feature["properties"]
        name = props["name"]
        assert props["score"] == round(scenario.score.district_scores[name], 2)
        assert props["gain"] == round(scenario.score.district_scores[name] - BASELINE.district_scores[name], 2)
        assert props["line_width"] == (3 if name == "Нура" else 1.2)


def test_before_and_invalid_plan_show_only_baseline():
    scenario = simulate_decisions(EXAMPLE)
    for candidate, before in ((scenario, True), (None, False)):
        data, _ = map_data(candidate, layer="critical", focused="Нура", before=before)
        nura = next(f["properties"] for f in data["features"] if f["properties"]["name"] == "Нура")
        assert nura["critical"] == 2
        assert nura["score"] == 49.18
        assert nura["gain"] == 0


@pytest.mark.parametrize("layer", ["score", "gain", "critical"])
def test_map_layers_are_complete(layer):
    data, _ = map_data(simulate_decisions(EXAMPLE), layer=layer, focused="Алматы")
    assert all(len(f["properties"]["color"]) == 4 for f in data["features"])


def test_map_event_accepts_polygon_and_label_picks_only():
    for item in ({"properties": {"name": "Нура"}}, {"name": "Нура"}):
        event = {"selection": {"objects": {"district-polygons": [item]}}}
        assert district_from_event(event) == "Нура"
    assert district_from_event({}) is None
    assert district_from_event({"selection": {"objects": {"untrusted": [{"name": "Нура"}]}}}) is None
    assert district_from_event({"selection": {"objects": {"district-labels": [{"name": "Unknown"}]}}}) is None


def test_ring_assembly_handles_reversed_segments_and_rejects_gaps():
    rings = join_rings([[(0, 0), (1, 0)], [(1, 1), (1, 0)], [(1, 1), (0, 0)]])
    assert rings == [[(0, 0), (1, 0), (1, 1), (0, 0)]]
    with pytest.raises(ValueError, match="closed ring"):
        join_rings([[(0, 0), (1, 0)]])
