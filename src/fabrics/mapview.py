"""map.html — contract output 4. Diagnose: points colored by cost-to-serve ($/unit).
Evaluate: assignment-change layer, chosen site starred, line-haul leg drawn.
This file is the screenshot that sells — tooltips and legends are product copy."""

import math
import os
import statistics

import folium

RAMP = ["#1a9850", "#91cf60", "#fee08b", "#fc8d59", "#d73027"]  # green -> red
CAPTURED = "#6a51a3"
MUTED = "#b8b8b8"
FACILITY = "#1f2937"
LINEHAUL = "#e6550d"


def _radius(units):
    return 3 + math.sqrt(max(units, 1)) / 22


def _cost_bins(demand):
    cpu = [p["base_cost"] / max(p["annual_units"], 1) for p in demand]
    edges = statistics.quantiles(cpu, n=5)  # 4 cut points -> 5 bins
    return edges


def _bin_color(value, edges):
    for i, e in enumerate(edges):
        if value <= e:
            return RAMP[i]
    return RAMP[-1]


def _card(html, top, left):
    return folium.Element(
        '<div style="position:fixed; top:{t}; left:{l}; z-index:9999;'
        ' background:rgba(255,255,255,.95); border:1px solid #d0d0d0; border-radius:8px;'
        ' padding:10px 14px; font-family:Segoe UI,system-ui,sans-serif; font-size:13px;'
        ' box-shadow:0 2px 8px rgba(0,0,0,.15); line-height:1.45;">{h}</div>'
        .format(t=top, l=left, h=html))


def render(out_dir, demand, existing, params, summary, candidates=None, results=None):
    lats = [p["lat"] for p in demand] + [f["lat"] for f in existing]
    lons = [p["lon"] for p in demand] + [f["lon"] for f in existing]
    m = folium.Map(location=[sum(lats) / len(lats), sum(lons) / len(lons)],
                   tiles="cartodbpositron", zoom_start=7, control_scale=True)
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    winner = next((r for r in (results or []) if r["opened"]), None)

    # --- layer 1: cost to serve (the Diagnose view) --------------------------
    edges = _cost_bins(demand)
    fg_cost = folium.FeatureGroup(name="Cost to serve ($/unit)",
                                  show=(winner is None))
    for p in demand:
        cpu = p["base_cost"] / max(p["annual_units"], 1)
        folium.CircleMarker(
            [p["lat"], p["lon"]], radius=_radius(p["annual_units"]),
            color=_bin_color(cpu, edges), weight=1, fill=True,
            fill_color=_bin_color(cpu, edges), fill_opacity=0.75,
            tooltip=(f"{p.get('name') or p['point_id']} · "
                     f"{p['annual_units']:,} units/yr · "
                     f"${p['base_cost']:,.0f}/yr (${cpu:.2f}/unit) · "
                     f"{p['base_miles']:.0f} mi from {p['base_facility']}"),
        ).add_to(fg_cost)
    fg_cost.add_to(m)

    # --- layer 2: assignment changes (the Evaluate view) ---------------------
    if winner:
        fg_new = folium.FeatureGroup(name="New assignments", show=True)
        for p in demand:
            moved = p["point_id"] in winner["captured_points"]
            folium.CircleMarker(
                [p["lat"], p["lon"]],
                radius=_radius(p["annual_units"]) if moved else 2.5,
                color=CAPTURED if moved else MUTED, weight=1, fill=True,
                fill_color=CAPTURED if moved else MUTED,
                fill_opacity=0.85 if moved else 0.45,
                tooltip=(f"{p.get('name') or p['point_id']} · "
                         + (f"moves {p['base_facility']} -> {winner['site_id']}"
                            if moved else f"stays with {p['base_facility']}")),
            ).add_to(fg_new)
        fg_new.add_to(m)

    # --- facilities and candidates -------------------------------------------
    for f in existing:
        folium.CircleMarker(
            [f["lat"], f["lon"]], radius=9, color="white", weight=2,
            fill=True, fill_color=FACILITY, fill_opacity=1.0,
            tooltip=f"{f.get('name') or f['facility_id']} (existing facility)",
        ).add_to(m)

    for c in (candidates or []):
        if winner and c["site_id"] == winner["site_id"]:
            continue
        folium.CircleMarker(
            [c["lat"], c["lon"]], radius=6, color="#888888", weight=2,
            fill=False, dash_array="3",
            tooltip=f"{c.get('name') or c['site_id']} (candidate — not selected)",
        ).add_to(m)

    if winner:
        site = next(c for c in candidates if c["site_id"] == winner["site_id"])
        folium.Marker(
            [site["lat"], site["lon"]],
            icon=folium.Icon(color="green", icon="star"),
            tooltip=(f"OPEN: {winner['name']} · NPV ${winner['npv'] / 1e3:,.0f}K · "
                     f"payback {winner['payback_years']:.1f}y · "
                     f"captures {winner['pct_demand_captured']:.0%} of volume"),
        ).add_to(m)
        origin = next(f for f in existing
                      if f["facility_id"] == winner["line_haul_origin_id"])
        folium.PolyLine(
            [[origin["lat"], origin["lon"]], [site["lat"], site["lon"]]],
            color=LINEHAUL, weight=3, dash_array="8 6", opacity=0.9,
            tooltip=(f"Line haul: {origin['facility_id']} -> {winner['site_id']} · "
                     f"{winner['line_haul_runs']} runs/yr"),
        ).add_to(m)

    # --- legend + verdict cards ----------------------------------------------
    swatches = ""
    lo = 0.0
    for i, e in enumerate(edges + [None]):
        label = (f"${lo:.2f}–{e:.2f}" if e is not None else f"&gt; ${lo:.2f}")
        swatches += ('<div><span style="display:inline-block;width:11px;height:11px;'
                     f'background:{RAMP[i]};border-radius:2px;margin-right:6px;"></span>'
                     f'{label}/unit</div>')
        lo = e if e is not None else lo
    m.get_root().html.add_child(_card(
        "<b>Cost to serve</b>" + swatches +
        '<div style="margin-top:4px;color:#666;">circle size = annual units</div>',
        "80px", "10px"))

    verdict = (f"<b>Fabrics</b> · {summary['facilities']} facilities · "
               f"{summary['units'] / 1e6:.1f}M units · "
               f"${summary['annual_cost'] / 1e6:.2f}M/yr · avg {summary['avg_miles']:.0f} mi")
    if winner:
        verdict += (f"<br><b style='color:#1a7a1a;'>Open {winner['name']}:</b> "
                    f"${winner['npv'] / 1e3:,.0f}K NPV · "
                    f"{winner['payback_years']:.1f}y payback · "
                    f"last-mile {winner['avg_miles_before']:.0f} -> "
                    f"{winner['avg_miles_after']:.0f} mi")
    elif results is not None:
        verdict += "<br><b>No candidate clears positive NPV — status quo wins.</b>"
    m.get_root().html.add_child(_card(verdict, "10px", "50px"))

    folium.LayerControl(collapsed=True).add_to(m)
    path = os.path.join(out_dir, "map.html")
    m.save(path)
    return path
