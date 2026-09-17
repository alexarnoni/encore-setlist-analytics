from encore.ingestion.musicbrainz import select_representative_release


def _release(track_count: int, date: str | None = None, country: str | None = None) -> dict:
    return {
        "media": [{"track-count": track_count}],
        "date": date,
        "country": country,
    }


def test_returns_none_for_empty_list():
    assert select_representative_release([]) is None


def test_picks_the_modal_track_count_not_the_highest():
    # Three releases share 12 tracks, one outlier has 20 (deluxe edition).
    # The mode (12) must win even though 20 is larger.
    releases = [
        _release(12, date="2007-01-01", country="GB"),
        _release(12, date="2007-02-01", country="US"),
        _release(12, date="2007-03-01", country="XW"),
        _release(20, date="2007-01-01", country="GB"),
    ]

    result = select_representative_release(releases)

    assert result["media"][0]["track-count"] == 12
    assert result["date"] == "2007-01-01"  # earliest among the modal group


def test_tie_on_modal_count_broken_by_earliest_date():
    releases = [
        _release(12, date="2007-06-15", country="GB"),
        _release(12, date="2007-01-10", country="US"),
    ]

    result = select_representative_release(releases)

    assert result["date"] == "2007-01-10"


def test_partial_dates_are_treated_as_start_of_period():
    # "2007" should sort as 2007-01-01, i.e. earlier than "2007-02-01".
    releases = [
        _release(12, date="2007", country="GB"),
        _release(12, date="2007-02-01", country="US"),
    ]

    result = select_representative_release(releases)

    assert result["country"] == "GB"


def test_tie_on_count_and_date_broken_by_country_preference():
    releases = [
        _release(12, date="2007-01-01", country="XW"),
        _release(12, date="2007-01-01", country="US"),
        _release(12, date="2007-01-01", country="GB"),
    ]

    result = select_representative_release(releases)

    assert result["country"] == "GB"


def test_missing_country_ranks_below_known_countries():
    releases = [
        _release(12, date="2007-01-01", country=None),
        _release(12, date="2007-01-01", country="XW"),
    ]

    result = select_representative_release(releases)

    assert result["country"] == "XW"


def test_multiple_modal_counts_stay_in_contention():
    # Two releases with 10 tracks and two with 14 tracks: both counts are
    # equally frequent (mode is ambiguous), so all four remain candidates
    # and the tie-break rules decide among them.
    releases = [
        _release(10, date="2007-05-01", country="GB"),
        _release(10, date="2007-06-01", country="US"),
        _release(14, date="2007-01-01", country="US"),
        _release(14, date="2007-03-01", country="GB"),
    ]

    result = select_representative_release(releases)

    assert result["media"][0]["track-count"] == 14
    assert result["date"] == "2007-01-01"
