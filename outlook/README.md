# FLARE FireOutlook examples

## Seven-day FireOutlook2.0

The [seven-day guide](seven_day/README.md) and
[notebook](notebooks/04_seven_day_outlook.ipynb) hold **July 15, 2026** fixed and
follow seven evening issuances, **July 8-14 at 8 p.m. PDT**, from Day 7 to Day 1.
All forecasts cover July 15 at 5 a.m. through July 16 at 5 a.m. PDT. The bundled
Wheeler County sample supports seven maps, animation, county statistics and
five reported fire-location comparisons using original native-grid values.

This complements the full-domain v11 Day-1 dataset below. The seven-day sample
uses a different product version; it does not change the v11 values. This July
archive uses NBM for Days 2-7 and HRRR for Day 1. Longer leads remain experimental.

## Original v11 daily forecasts

Nineteen full western-domain daily forecast files for July 3–21, 2026, by **Manju Smriti**. Each NetCDF includes the Outlook index, category, latitude and longitude. Index and coordinate values retain their source precision on the native grid. Published v11 categories follow the October 15, 2026 definition in `category-definition.json`.

Part of [ManjuSmriti/flare-oregon-sample](https://github.com/ManjuSmriti/flare-oregon-sample). Executed notebook outputs and the map preview are included here. 

## Data and times

Every array has shape **5792 × 6672**, with dimensions `y, x`. `lat[y, x]` and `lon[y, x]` locate the forecast value at the same pixel. Coordinates are copied in full from the shared static grid identified by each source manifest. Latitude and longitude are two-dimensional coordinates, not regularly spaced map axes.

Forecast issue time is **03:00 UTC**. Each file covers **12:00 UTC on its issue date through 12:00 UTC the following day**. July 21 therefore covers through July 22 at 12:00 UTC.

| Variable | Type | Meaning |
| --- | --- | --- |
| `outlook_index` | float32 | Original FLARE Outlook index; NaN where unavailable |
| `category` | uint8 | 0 unavailable, 1 minimal, 2 low, 3 moderate, 4 high, 5 very high, 6 extreme |
| `lat` | float32 | Latitude in degrees north |
| `lon` | float32 | Longitude in degrees east |

Zero is retained as an explicit unavailable class in the integer layers. Do not interpret it as the lowest available category. Forecast issue time is stored in `forecast_issue_time`; valid times are in `time_coverage_start` and `time_coverage_end`. The example reader creates a time axis when combining daily point values.

## Open the notebooks

Use Python 3.11 or newer. From this folder:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
jupyter lab
```

On Windows, activate with `.venv\Scripts\activate` instead.

1. [Open and check](notebooks/01_open_and_check.ipynb) — choose a date, inspect metadata and verify its checksum.
2. [Geographic maps](notebooks/02_geographic_maps.ipynb) — plot Outlook index and category over country and state boundaries, then select a geographic region.
3. [Wheeler County analysis](notebooks/03_daily_point_series.ipynb) — examine county distributions and high-index area, then compare July 13-16 maps with SPC and USGS products.
4. [July 15 forecast progression](notebooks/04_seven_day_outlook.ipynb) — compare seven evening updates for one target period, with animation and five fire-location examples.

Clone the parent repository and enter `outlook/` before running the setup commands. The daily NetCDF files are included in `outlook/data/`. You can inspect the saved outputs immediately without running the notebooks.

The notebooks use the bundled NetCDF files, boundaries and reference datasets.
Maps use geographic coordinates. Where a plotting stride is used, it reduces
display density while leaving the data unchanged. The Oregon notebooks in the
repository root provide the separate spectral-imagery examples.

## Daily files and verification

Files are in `data/`, named `FLARE_Outlook_v11_YYYYMMDDT0300Z.nc`. `manifest.json` lists every issue date, valid interval, byte size and SHA-256 digest. `SHA256SUMS.txt` supports independent verification. Index and coordinate arrays were checked against their sources, including NaN locations. Categories were checked against the published v11 thresholds, with the unavailable mask preserved.

The 19 NetCDF files total **1,903,992,727 bytes (1.90 GB)**. Individual files range from **99.11 to 100.80 MB**, including the full latitude/longitude arrays in every file. Every daily file is below 100 MiB (104,857,600 bytes). Storage figures labelled MB and GB use decimal units.

Each file includes its own coordinates and can be downloaded independently from `outlook/data/`.

Files use native NetCDF4 **zlib level 9**, byte shuffling and **512 × 512** chunks. They open directly with xarray; no ZIP extraction is needed. Compression is lossless and preserves all original numeric values and missing-value positions. Equivalent xarray write settings are:

```python
encoding = {
    name: {"zlib": True, "complevel": 9, "shuffle": True,
           "chunksizes": (512, 512)}
    for name in ["outlook_index", "category", "lat", "lon"]
}
ds.to_netcdf("outlook.nc", engine="netcdf4", encoding=encoding)
```

## Attribution and license

Creator: **Manju Smriti**. Institution: **BRIDGE - Research and Policy Foundation; ARTH GEO Intelligence**. GitHub repository: **ManjuSmriti/flare-oregon-sample**, under `outlook/`.

The dataset is licensed under **Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)**. See `LICENSE.txt` and the [license terms](https://creativecommons.org/licenses/by-nc-nd/4.0/). Cite this repository and the commit used for Outlook analyses; the Oregon FireScore DOI identifies a separate dataset.

The manifest retains source run identifiers and hashes for provenance.

Basemap boundaries: [Natural Earth](https://www.naturalearthdata.com/), 1:110m countries and state/province lines, public domain. Their accompanying source readme and version files are bundled under `assets/natural_earth/`.
