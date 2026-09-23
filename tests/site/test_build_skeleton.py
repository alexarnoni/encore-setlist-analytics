"""T1: the build entry point exists and is runnable."""

from pathlib import Path

from encore.site import build


def test_main_returns_zero() -> None:
    assert build.main() == 0


def test_output_dir_default_and_override(monkeypatch) -> None:
    monkeypatch.delenv("SITE_OUTPUT_DIR", raising=False)
    assert build.output_dir() == Path("site")
    monkeypatch.setenv("SITE_OUTPUT_DIR", "out")
    assert build.output_dir() == Path("out")
