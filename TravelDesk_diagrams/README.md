# TravelDesk v3.0 diagrams (24 figures)

`png/` - every figure at 2x resolution (the Agile Spec v3.0 embeds the same figures).
`src/` - the D2 source of every figure (`*.d2`), the generator and the SVG-to-PNG renderer:

* Install D2 (https://d2lang.com), then `python gen_d2.py [name ...]` writes `src/*.d2`, `src/*.svg` and `png/*.png`.
* Layout: ELK, `--elk-nodeNodeBetweenLayers=34 --elk-edgeNodeBetweenLayers=18`.
* `svg2png.js` renders each SVG with headless Chrome (puppeteer) at 2x; point `executablePath` at your Chrome.
* The ER figures (d19-d22b) are generated from `tables.json`, exported from a fresh database with migrations 001-007;
  re-export it after any schema change.

Colour key used in every figure: teal = Employee, indigo = Manager, amber = rule in plain code, violet = AI,
green = approved / success, red = refused / rejected, orange = external service, slate = neutral component.
