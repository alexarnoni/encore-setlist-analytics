import re

from encore.config import load_bands

# Top MusicBrainz match (score 100) for each band name, captured from the
# Phase 0 search cache (data/raw/musicbrainz/search_artist_*.json, not
# committed). Guards config/bands.yaml against accidental edits.
EXPECTED_MBIDS = {
    "Arctic Monkeys": "ada7a83c-e3e1-40f1-93f9-3e73dbc9298a",
    "Oasis": "39ab1aed-75e0-4140-bd47-540276886b60",
    "Linkin Park": "f59c5520-5f46-4d2c-b2c4-822eabf53419",
    "Twenty One Pilots": "a6c6897a-7415-4f8d-b5a5-3a5e05f3be67",
    "Muse": "9c9f1380-2516-4fc9-a3e6-f9f61941d090",
    "Metallica": "65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab",
    "Avenged Sevenfold": "24e1b53c-3085-4581-8472-0b0088d2508c",
}

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def test_loads_exactly_the_seven_bands_in_scope():
    bands = load_bands()
    assert {band.name for band in bands} == set(EXPECTED_MBIDS)
    assert len(bands) == 7


def test_every_mbid_is_a_well_formed_uuid():
    for band in load_bands():
        assert _UUID_RE.match(band.mbid), f"{band.name}: {band.mbid!r} is not a UUID"


def test_mbids_match_phase_0_validated_values():
    bands_by_name = {band.name: band.mbid for band in load_bands()}
    assert bands_by_name == EXPECTED_MBIDS


def test_encore_bands_file_env_var_overrides_the_default_path(tmp_path, monkeypatch):
    custom_file = tmp_path / "custom-bands.yaml"
    custom_file.write_text("bands:\n  - name: Test Band\n    mbid: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\n")
    monkeypatch.setenv("ENCORE_BANDS_FILE", str(custom_file))

    bands = load_bands()

    assert [b.name for b in bands] == ["Test Band"]
