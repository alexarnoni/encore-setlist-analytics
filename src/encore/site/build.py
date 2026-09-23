"""Entry point: `python -m encore.site.build` builds the static site into `site/`.

The generator reads only the `analytics` schema and never contacts setlist.fm
(docs/specs/spec-04-site.md, working rules). This is the T1 skeleton: it only
resolves the output directory and logs; pages are added in later tasks.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "site"


def output_dir() -> Path:
    """Return the build output directory (SITE_OUTPUT_DIR, default `site/`)."""
    return Path(os.environ.get("SITE_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))


def main() -> int:
    """Run the build and return the process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Site build started; output directory: %s", output_dir())
    logger.info("No pages generated yet (skeleton).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
