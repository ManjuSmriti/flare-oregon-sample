"""Generate the July 15 fixed-target forecast progression notebook."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
notebook = nbf.v4.new_notebook(cells=[
    md('''# FireOutlook for July 15: how the forecast changed

Hold **July 15, 2026** fixed and follow seven evening forecast updates for
Wheeler County, Oregon, starting **July 8 at 8 p.m. PDT** and ending **July 14
at 8 p.m. PDT**. Every map targets the same period: **July 15 at 5 a.m. through
July 16 at 5 a.m. PDT**. This reproduces the sequence in the Wheeler County presentation.

Each daily issuance brings a new forecast for that fixed target, moving from
**Day 7 to Day 1**. This notebook uses the original July FireOutlook2.0 archive:
NBM for Days 7-2 and HRRR for Day 1. Longer leads are experimental.

The sample, county boundary, and five reported fire locations are bundled.
Install `outlook/requirements.txt`, then run all cells from the cloned repository.'''),
    code('''from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, Image

cwd = Path.cwd().resolve()
ROOT = next((base for parent in [cwd, *cwd.parents]
             for base in (parent / "outlook", parent)
             if (base / "examples" / "seven_day.py").exists()), None)
if ROOT is None:
    raise RuntimeError("Run this notebook from within the cloned repository")
sys.path.insert(0, str(ROOT / "examples"))
from seven_day import (open_sample, schedule, select_update, plot_progression,
                       point_forecast, county_statistics, references, draw_update,
                       flag_names, LABELS)
ds = open_sample()
context = references()
output = ROOT / "outputs"
output.mkdir(exist_ok=True)
print("Forecast and reference checksums verified")
print("Product:", ds.attrs["product"])
print("Dimensions:", dict(ds.sizes))'''),
    md('''## 1. One target date, seven updates

All times labeled PDT use Oregon local time. **July 8 at 8 p.m. PDT is July 9
at 03:00 UTC**, the first stored issuance covering the July 15 target at Day 7.
The July 8 **UTC** issuance reaches only July 14 at Day 7. Keeping both time
zones visible prevents shifting the sequence by a day.'''),
    code('''timeline = schedule(ds)
display(timeline)
assert ds.complete.values.all()
assert timeline.issued_PDT.dt.day.tolist() == list(range(8, 15))
assert timeline.forecast_day.tolist() == list(range(7, 0, -1))
assert timeline.valid_start_PDT.nunique() == timeline.valid_end_PDT.nunique() == 1'''),
    md('''## 2. Compare the maps

The target period, map extent, and category colors stay the same in every panel.
The forecast values change with each issuance. Numbered points mark the five
reported fire origins. The July 16-17 observed outlines provide fixed reference
geography; they do not represent forecast fire boundaries.

Gray means unavailable. The maps use stored category codes and original
two-dimensional coordinates, with no interpolation of forecast categories.'''),
    code('''fig = plot_progression(ds)
fig.savefig(output / "july15_forecast_progression.png", dpi=140)
plt.show()'''),
    md('''## 3. Follow the updates one at a time

This animation keeps July 15 fixed while advancing the issue date from July 8
to July 14. The full seven-panel figure above remains available for comparison.'''),
    code('''from matplotlib.animation import FuncAnimation, PillowWriter
fig, ax = plt.subplots(figsize=(8, 7), constrained_layout=True)
mesh = draw_update(ds, 0, ax, context)
fig.colorbar(mesh, ax=ax, orientation="horizontal", fraction=.045,
             ticks=range(7)).ax.set_xticklabels(LABELS, fontsize=8)
fig.suptitle("Wheeler County: forecast for July 15, 5 a.m. to July 16, 5 a.m. PDT", fontsize=11)
def animate(i):
    ax.clear()
    draw_update(ds, i, ax, context)
animation = FuncAnimation(fig, animate, frames=7, interval=1200, repeat=True)
animation.save(output / "july15_forecast_progression.gif", writer=PillowWriter(fps=1), dpi=100)
plt.close(fig)
display(Image(filename=str(output / "july15_forecast_progression.gif")))'''),
    md('''## 4. How much of Wheeler County was High or above?

Recompute the county percentages from the bundled forecast pixels. Each pixel
center inside the Census county boundary contributes its source geodesic area.
The denominator includes all county pixel centers, including unavailable areas,
matching the presentation's calculation. Boundary pixels use center inclusion.
This is forecast danger area, not burned area.'''),
    code('''county = county_statistics(ds)
display(county[["issued_PDT", "forecast_day", "county_high_or_above_pct", "county_scored_pct"]].round(2))
fig, ax = plt.subplots(figsize=(10, 4), constrained_layout=True)
labels = county.issued_PDT.dt.strftime("Jul %d").tolist()
ax.plot(range(7), county.county_high_or_above_pct, marker="o", color="#17624d")
for i, value in enumerate(county.county_high_or_above_pct):
    ax.annotate(f"{value:.1f}%", (i, value), xytext=(0, 8), textcoords="offset points", ha="center")
ax.set(xticks=range(7), xticklabels=labels, ylim=(0, 65),
       xlabel="Forecast issued at 8 p.m. PDT", ylabel="County area High or above (%)",
       title="Every update forecasts the same July 15 period")
ax.grid(axis="y", alpha=.2)
plt.show()'''),
    md('''## 5. Compare the five reported fire locations

For each origin, use the same nearest native-grid pixel across all seven
issuances. The table reports category names; the chart shows the underlying
indices. This examines changing forecast guidance at later reported fire
locations, rather than predicted ignition times or fire spread.'''),
    code('''origins = [f for f in context["features"] if f["geometry"]["type"] == "Point"]
series = {}
for feature in origins:
    lon, lat = feature["geometry"]["coordinates"]
    values = point_forecast(ds, lat, lon)
    values["fire"] = feature["properties"]["name"]
    values["quality_notes"] = [", ".join(flag_names(ds, int(v))) or "None set"
                               for v in values.quality_flags]
    series[feature["properties"]["name"]] = values
comparison = pd.DataFrame({name: values.category.to_list() for name, values in series.items()},
                          index=pd.Index(labels, name="Issued at 8 p.m. PDT"))
display(comparison)
fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
for feature in origins:
    name = feature["properties"]["name"]
    ax.plot(range(7), series[name]["index"], marker="o", label=name, color=feature["properties"]["color"])
ax.set(xticks=range(7), xticklabels=labels, ylim=(0, 1), xlabel="Forecast issuance (PDT)",
       ylabel="FireOutlook index", title="Forecasts for July 15 at the five reported origins")
ax.legend(loc="lower left", ncol=3, frameon=False)
ax.grid(axis="y", alpha=.2)
plt.show()'''),
    md('''## 6. Explore your own location and export results

Change the coordinate below to a location within the sample. The default is the
reported Crosswhite origin. The table preserves the selected pixel, distance
from the requested location, valid period, weather source, and quality flags.'''),
    code('''latitude, longitude = 44.803333, -120.199167
point = point_forecast(ds, latitude, longitude)
display(point)
point.to_csv(output / "july15_selected_location.csv", index=False)
county.to_csv(output / "july15_county_progression.csv", index=False)
pd.concat(series.values(), ignore_index=True).to_csv(output / "july15_five_fire_locations.csv", index=False)
print("Saved figures and three CSV files in outlook/outputs")'''),
    md('''## Data and interpretation

This is a historical forecast replay from `FireOutlook2.0-hrrr1-nbm2to7-1`.
The July archive uses NBM on Day 2, unlike the later hybrid operational version.
Vegetation, snow support, and the pre-issue prior are frozen separately for each
issuance. The experiment's retained audit verified weather publication and
vegetation observation times before issue; historical prior receipt times were
not fully verified. Prior-application flags remain available for inspection.

Codes 1-6 mean Minimal through Extreme; code 0 means Unavailable. The five
category edges below come directly from this product. The index is an engineering
indicator, not a calibrated probability. Forecast changes are not themselves
evidence of increasing accuracy. This notebook makes no new skill claim.

County geometry: US Census TIGERweb, BAS 2026. Observed reference origins and
perimeters: retained NIFC/WFIGS NIFS records, July 16-17, with record timestamps
and IRWIN identifiers in the bundled GeoJSON. All maps and calculations use
the bundled source values, not pixels extracted from the presentation.'''),
    code('''print("Category edges:", ds.attrs["category_edges"])
print("Weather policy:", ds.attrs["forecast_policy"])
ds.close()'''),
])
notebook.metadata['kernelspec'] = {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}
nbf.write(notebook, ROOT / 'notebooks' / '04_seven_day_outlook.ipynb')
