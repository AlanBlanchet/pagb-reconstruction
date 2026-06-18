# Researcher memory — PAGB Reconstruction

## 2026-06-18 — EBSD martensite datasets + EBSD-product UI inspiration

### Format constraint (load-bearing)
- App loader = `orix.io.load` → reads `.ang`, `.ctf` (Channel TEXT), `bruker_h5ebsd`, `emsoft_h5ebsd`, `orix_hdf5`. orix does NOT read Oxford binary `.cpr`/`.crc`.
- We ADDED an Oxford `.crc`/`.cpr` reader (`io/crc_io.py`, `CRCLoader`): record = phase byte + 3 Bunge Euler f4 + rest skipped; grid from `.cpr [Job] xCells/yCells/GridDist`. Validated on MTEX `martensite.crc` (486×707, bcc).

### Martensite datasets (for prior-austenite reconstruction)
- IN REPO NOW: `data/martensite_roomtemp.ctf` — Taylor et al. 2024 lath martensite (room-temp child), CC-BY-4.0, 501×667, 0.3µm, ~87% bcc / no retained austenite. From ORTools4MTEX repo `data/input/ebsd/Taylor_et_al_2024/` (extract of Zenodo 10.5281/zenodo.8348372). Its 500°C companion `Map Data 30 ... 500C.ctf` is the measured austenite GROUND TRUTH for validation.
- Canonical MTEX `mtexdata martensite` = `martensite.cpr/.crc` (Nyyssonen Q&P steel, Iron bcc SG229 / fcc SG225, 707×486, KS) — Oxford binary; now loadable via our CRCLoader. Raw: raw.githubusercontent.com/mtex-toolbox/mtex/develop/data/EBSD/martensite.{crc,cpr}
- Harder 2nd case: `TRWIPsteel.ctf` (TWIP-TRIP, two-step γ→ε→α', Pramanik). ORTools4MTEX repo.
- HuggingFace EBSD = no usable martensite (only IN718 superalloy, no license). DefDAP/AstroEBSD example data = no steel martensite.
- Gotcha: WebFetch rejects raw files >10MB — use `api.github.com/repos/.../contents/...` JSON for size + `download_url`.

### EBSD-product UI inspiration (prioritized, pluggable) — sources MTEX, AZtecCrystal, EDAX OIM, DREAM.3D, Bruker
- IPF colour-key TRIANGLE (we ADDED via orix `IPFColorKeyTSL`, shown beside map for IPF modes). TSL cubic convention: 001=red(BL), 101=green(BR), 111=blue(top); default ref axis IPF-Z. orix's wedge may lack 001/101/111 corner labels — overlay our own if the critic flags it.
- Categorical maps (variant/packet/block/grain id): discrete swatch legend + ordered palette (`matplotlib tab20`; many categories → `glasbey`/`colorcet.glasbey`). We added a categorical colormap (distinct colours); per-id SWATCH legend still TODO.
- Reconstruction-quality MAPS (high value, data already exists): per-pixel fit/OR-deviation map with FIXED 0–5° range (MTEX LaboTeX); clustering probability/votes map; boundary misfit with fit-scaled transparency. We have "Fit Angle" map but autoLevels (not fixed range) — add optional (vmin,vmax) to map_property meta.
- 24 KS variants → packets (4, by {111}γ) / Bain groups; offer per-variant AND per-packet colouring.
- Other: KAM (we have it), MDF axis-distribution (missing), area-weighted grain-size histogram, pole figure multi-{hkl} + theoretical-variant overlay + linked brushing.
- IA convention: map-dominant centre; left = data/phase/settings; right = stats/legends/texture; bottom = histograms. Legend + IPF key ON/beside the map.
- Refs: mtex-toolbox.github.io/MaParentGrainReconstruction.html (fit/votes maps), /MartensiteVariants.html (variant/packet maps), orix IPF tutorial, dream3d.io (WriteIPFStandardTriangle, KAM).
