# FLARE FireOutlook: seven daily forecasts

Explore one issuance across seven consecutive 24-hour forecast windows. This
package adds FireOutlook2.0 alongside the original July v11 Day-1 examples.
Seven forecast leads from one issuance are different from seven forecasts
issued on successive dates.

## Start here

Open [the seven-day notebook](../notebooks/04_seven_day_outlook.ipynb) after
installing [the notebook requirements](../requirements.txt). Run all cells from
top to bottom. The bundled sample is included in Git, so no external drive,
account, or separate forecast download is required.

The notebook checks the file checksum, displays each forecast's valid period,
maps all seven leads, and exports a selected location's forecast to CSV. It
uses the stored category values and decodes quality flags.

## What is included?

- **Issuance:** November 2, 2026 at 03:00 UTC.
- **Coverage:** a native-grid rectangular window around Wheeler County, Oregon.
  This is a regional sample, not the full western-domain archive or a county mask.
- **Valid periods:** Day 1 starts November 2 at 12:00 UTC; Day 7 ends November 9
  at 12:00 UTC. Every lead covers 24 hours, using half-open [start, end) windows.
- **Values:** original index, category, quality flags, and two-dimensional
  latitude/longitude arrays. No interpolation, quantization, or resampling.
- **Provenance:** issue signature, grid signature, algorithm version, exact source
  grid window, and SHA-256 checksum in [manifest.json](manifest.json).

This sample illustrates the seven-day data format. It does not replace the July
case-study data or establish forecast skill for the additional lead times.

## Weather by forecast day

| Lead | Weather source in this issuance |
| --- | --- |
| Day 1 | HRRR |
| Day 2 | HRRR f36-f47 combined with NBM f48-f60 |
| Days 3-7 | NBM; experimental longer leads |

Vegetation, snow support, and the pre-issue proximity prior remain frozen at
issuance. The longer leads represent changing forecast weather against that
frozen state, rather than new satellite observations of future conditions.
`weather_cycle` records the weather initialization, while `valid_start` and
`valid_end` describe the forecast window. Consult the issuance metadata when
using another algorithm version; the earlier base product used NBM on Day 2.

## Categories and missing data

Codes 1-6 mean **Minimal, Low, Moderate, High, Very high, Extreme**. Code 0
means **Unavailable**. A numerical index of zero can be valid; category zero is
the unavailable marker. The index is an engineering indicator, not a calibrated
probability of ignition or spread.

Use `outlook_category` directly. This version's five category edges are stored
in `category_edges`; the notebook displays their exact values. They differ from
the rounded thresholds used in some earlier story displays. Do not reclassify
this sample using those older thresholds.

Quality flags are bitwise and can coexist:

| Bit | Meaning |
| --- | --- |
| 1 | Excluded land |
| 2 | No paired vegetation donor |
| 4 | Missing trend |
| 8 | Missing weather |
| 16 | Historical vegetation donor |
| 32 | NIFC proximity prior applied |
| 64 | Experimental longer lead |

Only read leads whose `complete` marker is true. The example reader rejects
incomplete leads instead of displaying them as low danger. The stored pre-issue
NIFC proximity prior is distinct from later incident observations used for
evaluation; this sample makes no new retrospective performance claim.

## Reuse with another complete issuance

For your own single-issuance Zarr, install `zarr>=2.18,<3` and open it with
`xarray.open_zarr(path, consolidated=True, mask_and_scale=False, chunks=None)`.
Use `validate`, `select_day`, and `schedule` from `examples/seven_day.py`.
For a multi-issue archive, select one issue first and attach its correct issue
metadata. The point helper and map function load spatial arrays, so subset a
large domain before using them.

The reproducible sample exporter is `examples/export_seven_day_sample.py`:

```bash
python examples/export_seven_day_sample.py YOUR_ISSUANCE.zarr seven_day/sample.nc
```

It checks completion and valid windows, exports a native-grid window, compares
every exported array value with the source, and writes a checksum manifest.
Supply your own source issuance; the full operational archive is not bundled.

Creator: **Manju Smriti**, BRIDGE - Research and Policy Foundation;
ARTH GEO Intelligence. The repository's **CC BY-NC-ND 4.0** license applies.
