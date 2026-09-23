"""Allow `python -m encore.site`; the documented entry point is `encore.site.build`."""

from encore.site.build import main

if __name__ == "__main__":
    raise SystemExit(main())
