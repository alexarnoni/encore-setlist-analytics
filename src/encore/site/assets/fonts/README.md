# Fonts

IBM Plex Mono, Regular (400) and Medium (500), latin subset, self-hosted (no request to a font CDN).

- Source: https://github.com/IBM/plex, `packages/plex-mono/fonts/complete/woff2/`
- Licence: SIL Open Font License 1.1, in `OFL.txt` (copyright IBM Corp.; reserved font name "Plex").
  The subset is a modified version of the font under that licence and keeps the name for
  identification only; it is served with the licence text next to it.
- Subset: Basic Latin, Latin-1 Supplement, Latin Extended-A, and the punctuation the site uses
  (en and em dash, curly quotes, ellipsis, bullet, minus sign, multiplication sign). About 18 KB per weight.

To regenerate (needs `fonttools` and `brotli`, listed in `requirements.txt`):

```bash
python -m fontTools.subset IBMPlexMono-Regular.woff2 \
  --unicodes="U+0020-007E,U+00A0-00FF,U+0100-017F,U+2013,U+2014,U+2018,U+2019,U+201C,U+201D,U+2026,U+2022,U+2212,U+00D7" \
  --flavor=woff2 --layout-features='*' --output-file=IBMPlexMono-Regular.woff2
```

`assets/fonts.css` declares the two faces; the build links them only when these files exist.
