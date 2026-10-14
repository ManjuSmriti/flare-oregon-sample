# FLARE Outlook v11 daily forecasts

Nineteen full western domain daily forecast files for July 3–21, 2026, prepared for **ManjuSmriti**. Each self-contained NetCDF includes the original Outlook index, category, latitude and longitude arrays. The native grid and numeric values are preserved without trimming, resampling or quantization.

Part of [ManjuSmriti/flare-oregon-sample](https://github.com/ManjuSmriti/flare-oregon-sample). Executed notebook outputs and the map preview are included here. The 19 daily NetCDF files are awaiting separate Release upload; download links will be added when that upload completes.

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
3. [Daily point series](notebooks/03_daily_point_series.ipynb) — select latitude and longitude and compare all 19 daily forecasts at the nearest original grid pixel.

Clone the parent repository and enter `outlook/` before running the setup commands. After the data upload is complete, save the daily NetCDF files in `outlook/data/`. You can inspect the saved outputs immediately without downloading data or running the notebooks.

The notebooks use only the packaged NetCDF files and bundled public-domain map boundaries. No external drive or private source code is needed. Maps use true latitude/longitude axes. Display stride reduces rendering cost only; the files remain full resolution. There are no spectral bands in this package, so these notebooks map Outlook products rather than false-color RGB imagery.

## Daily files and verification

Files are in `data/`, named `FLARE_Outlook_v11_YYYYMMDDT0300Z.nc`. `manifest.json` lists every issue date, valid interval, byte size and SHA-256 digest. `SHA256SUMS.txt` supports independent file verification. Every exported pixel in all four arrays is compared against its original source, including NaN locations.

The 19 NetCDF files total **1,902,289,034 bytes (1.90 GB)**. Individual files range from **99.02 to 100.73 MB**, including the full latitude/longitude arrays in every file. Every daily file is below 100 MiB (104,857,600 bytes). Storage figures labelled MB and GB use decimal units.

Each file includes its own coordinates and can be downloaded independently after publication. Daily binaries are excluded from Git history by `.gitignore`; they are prepared for separate GitHub Release assets. No live download URLs are included before publication.

Files use native NetCDF4 **zlib level 9**, byte shuffling and **512 × 512** chunks. They open directly with xarray; no ZIP extraction is needed. Compression is lossless and preserves all original numeric values and missing-value positions. Equivalent xarray write settings are:

```python
encoding = {
    name: {"zlib": True, "complevel": 9, "shuffle": True,
           "chunksizes": (512, 512)}
    for name in ["outlook_index", "category", "lat", "lon"]
}
ds.to_netcdf("outlook.nc", engine="netcdf4", encoding=encoding)
```

## Attribution and publication review

Creator: **Manju Smriti**. Institution: **BRIDGE - Research and Policy Foundation; ARTH GEO Intelligence**. GitHub repository: **ManjuSmriti/flare-oregon-sample**, under `outlook/`.

The dataset is licensed under **Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)**, matching the license selected on the existing Zenodo record. See `LICENSE.txt` and the [license terms](https://creativecommons.org/licenses/by-nc-nd/4.0/). The Oregon sample DOI is not assigned to this distinct Outlook product.

Original run identifiers and manifest/result hashes are retained for provenance. Private local filesystem paths and the underlying forecasting implementation are not included.

Basemap boundaries: [Natural Earth](https://www.naturalearthdata.com/), 1:110m countries and state/province lines, public domain. Their accompanying source readme and version files are bundled under `assets/natural_earth/`.
