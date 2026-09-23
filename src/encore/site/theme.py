"""Design tokens: the single source for page CSS and for chart colours.

Charts are drawn with the *light* values below as sentinels and then rewritten to
`var(--token)` (see `charts.finalize_svg`), so the page theme recolours them
without a re-render. Band colours are one shade per band, identical in both themes.
"""

from __future__ import annotations

from encore.site import bands as bands_mod

# One fixed colour per band in config order (colour follows the band, never its rank).
# From the notebooks, adjusted once so every colour reaches 3:1 (WCAG graphics) on both card surfaces,
# and used unchanged in both themes: Linkin Park #1baf7a -> #19a170, Twenty One Pilots #eda100 ->
# #c28400, Muse #e87ba4 -> #d57197, Avenged Sevenfold #4a3aa7 -> #6851ea.
BAND_PALETTE: tuple[str, ...] = (
    "#2a78d6", "#eb6834", "#19a170", "#c28400", "#d57197", "#008300", "#6851ea",
)

LIGHT: dict[str, str] = {
    "bg": "#f5f2ea", "card": "#fcfcfb", "ink": "#14130f", "muted": "#52514e",
    "line": "#e0dccf", "signal": "#b3261e", "neutral": "#a3a29c",
}
DARK: dict[str, str] = {
    "bg": "#161512", "card": "#1e1d19", "ink": "#ece9df", "muted": "#a8a59b",
    "line": "#302e28", "signal": "#e2574c", "neutral": "#8a877d",
}

FONT_MONO = '"IBM Plex Mono", ui-monospace, "Cascadia Mono", Consolas, monospace'
FONT_SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'

SURFACES = {"light": LIGHT["card"], "dark": DARK["card"]}


def band_colors(names: tuple[str, ...] | None = None) -> dict[str, str]:
    """Band name -> hex colour, by position in the band config."""
    names = names or bands_mod.band_names()
    return {name: BAND_PALETTE[i % len(BAND_PALETTE)] for i, name in enumerate(names)}


def band_token(name: str) -> str:
    """CSS custom property name of a band's colour."""
    return f"--band-{bands_mod.slug(name)}"


def sentinel_map() -> dict[str, str]:
    """Light hex value -> CSS custom property, for rewriting chart colours."""
    mapping = {LIGHT[name]: f"--{name}" for name in ("ink", "muted", "line", "neutral", "card")}
    for name, colour in band_colors().items():
        mapping.setdefault(colour, band_token(name))
    return mapping


def tokens_css() -> str:
    """The `:root` and dark-theme custom property blocks, generated from the values above."""
    bands = "".join(f"  {band_token(n)}: {c};\n" for n, c in band_colors().items())
    light = "".join(f"  --{k}: {v};\n" for k, v in LIGHT.items())
    dark = "".join(f"  --{k}: {v};\n" for k, v in DARK.items())
    return (
        f":root {{\n  --font-mono: {FONT_MONO};\n  --font-sans: {FONT_SANS};\n{light}{bands}}}\n"
        f':root[data-theme="dark"] {{\n{dark}}}\n'
    )


def contrast(foreground: str, background: str) -> float:
    """WCAG contrast ratio between two `#rrggbb` colours."""
    def luminance(hex_colour: str) -> float:
        h = hex_colour.lstrip("#")
        channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    hi, lo = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)
