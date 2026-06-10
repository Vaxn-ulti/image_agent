from __future__ import annotations

import csv
import html
import json
import math
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_FEATURE_GROUP = "scientific_report"

_PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]

_SCIENTIFIC_COLORS = {
    "navy": "#17324d",
    "blue": "#1f77b4",
    "teal": "#2a9d8f",
    "orange": "#e76f51",
    "gold": "#f4a261",
    "red": "#d62828",
    "gray": "#6b7280",
    "grid": "#d7dee8",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "NA", "n/a", "N/A"):
        return None
    try:
        if isinstance(value, str):
            return float(value.replace(",", ""))
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_tsv_rows(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open(encoding="utf-8", errors="ignore") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [dict(row) for row in reader]


def _find_output(summary: dict[str, Any], name: str) -> dict[str, Any] | None:
    outputs = summary.get("outputs") or {}
    for section_items in outputs.values():
        for item in section_items:
            if item.get("name") == name:
                return item
    return None


def _path_for(summary: dict[str, Any], name: str) -> Path | None:
    item = _find_output(summary, name)
    if not item:
        return None
    path = item.get("path")
    return Path(path) if path else None


def _relative_to_reports(reports_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(reports_dir).as_posix()
    except ValueError:
        try:
            return Path(path).relative_to(reports_dir.parent).as_posix()
        except ValueError:
            return path.name


def _color_for_value(value: float, minimum: float, maximum: float) -> str:
    if not math.isfinite(value):
        return "#d0d0d0"
    if maximum <= minimum:
        return "#4c78a8"
    ratio = max(0.0, min(1.0, (value - minimum) / (maximum - minimum)))
    if ratio < 0.5:
        t = ratio / 0.5
        r = int(31 + (244 - 31) * t)
        g = int(119 + (109 - 119) * t)
        b = int(180 + (67 - 180) * t)
    else:
        t = (ratio - 0.5) / 0.5
        r = int(244 + (214 - 244) * t)
        g = int(109 + (39 - 109) * t)
        b = int(67 + (40 - 67) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _mpl():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _wrap_label(label: str, width: int = 16) -> str:
    value = str(label or "")
    return "\n".join(textwrap.wrap(value, width=width, break_long_words=False)) or value


def _style_axis(ax: Any, *, title: str, subtitle: str = "") -> None:
    ax.set_title(title, loc="left", fontsize=14, fontweight="bold", color=_SCIENTIFIC_COLORS["navy"], pad=22 if subtitle else 12)
    if subtitle:
        ax.text(
            0,
            1.03,
            subtitle,
            transform=ax.transAxes,
            fontsize=9,
            color=_SCIENTIFIC_COLORS["gray"],
            va="bottom",
        )
    ax.grid(axis="y", color=_SCIENTIFIC_COLORS["grid"], linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#9aa6b2")
    ax.spines["bottom"].set_color("#9aa6b2")
    ax.tick_params(axis="both", labelsize=8, colors="#344054")


def _save_empty_png(path: Path, title: str, message: str) -> None:
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(7.2, 2.8), dpi=160)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.axis("off")
    ax.text(0.02, 0.82, title, transform=ax.transAxes, fontsize=15, fontweight="bold", color=_SCIENTIFIC_COLORS["navy"])
    ax.text(0.02, 0.52, message, transform=ax.transAxes, fontsize=10, color=_SCIENTIFIC_COLORS["gray"])
    fig.tight_layout(pad=1.2)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _png_bar_chart(path: Path, title: str, items: list[tuple[str, float]], *, subtitle: str = "", ylabel: str = "Value") -> None:
    clean_items = [(str(label), float(value)) for label, value in items if isinstance(value, (int, float)) and math.isfinite(value)]
    if not clean_items:
        _save_empty_png(path, title, "No numeric data available for this indicator.")
        return
    plt = _mpl()
    labels = [_wrap_label(label, 14) for label, _ in clean_items]
    values = [value for _, value in clean_items]
    width = max(7.2, min(13.5, 0.58 * len(values) + 5.5))
    fig, ax = plt.subplots(figsize=(width, 4.4), dpi=160)
    fig.patch.set_facecolor("white")
    colors = [_SCIENTIFIC_COLORS["blue"], _SCIENTIFIC_COLORS["orange"], _SCIENTIFIC_COLORS["teal"], _SCIENTIFIC_COLORS["gold"], _SCIENTIFIC_COLORS["red"]]
    bars = ax.bar(range(len(values)), values, color=[colors[idx % len(colors)] for idx in range(len(values))], edgecolor="white", linewidth=0.8)
    _style_axis(ax, title=title, subtitle=subtitle)
    ax.set_ylabel(ylabel, fontsize=9, color="#344054")
    ax.set_xticks(range(len(values)), labels)
    ax.margins(y=0.18)
    for bar, value in zip(bars, values):
        y = bar.get_height()
        va = "bottom" if y >= 0 else "top"
        offset = 3 if y >= 0 else -5
        ax.annotate(f"{value:.3g}", xy=(bar.get_x() + bar.get_width() / 2, y), xytext=(0, offset), textcoords="offset points", ha="center", va=va, fontsize=8, color="#111827")
    fig.tight_layout(pad=1.35)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _png_line_chart(path: Path, title: str, series: list[dict[str, Any]], *, subtitle: str = "", ylabel: str = "Value") -> None:
    clean_series: list[dict[str, Any]] = []
    for item in series:
        values = [float(value) for value in item.get("values", []) if isinstance(value, (int, float)) and math.isfinite(value)]
        if len(values) >= 2:
            clean_series.append({**item, "values": values})
    if not clean_series:
        _save_empty_png(path, title, "No time-series data available for this indicator.")
        return
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(9.2, 4.2), dpi=160)
    fig.patch.set_facecolor("white")
    colors = [_SCIENTIFIC_COLORS["blue"], _SCIENTIFIC_COLORS["orange"], _SCIENTIFIC_COLORS["teal"], _SCIENTIFIC_COLORS["red"]]
    for idx, item in enumerate(clean_series):
        values = item["values"]
        ax.plot(range(len(values)), values, linewidth=1.8, color=item.get("color") or colors[idx % len(colors)], label=str(item.get("name", f"series_{idx}")))
    _style_axis(ax, title=title, subtitle=subtitle)
    ax.set_xlabel("Volume / sample index", fontsize=9, color="#344054")
    ax.set_ylabel(ylabel, fontsize=9, color="#344054")
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    fig.tight_layout(pad=1.35)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _png_heatmap(path: Path, title: str, matrix: list[list[float]], row_labels: list[str], col_labels: list[str], *, subtitle: str = "", cmap: str = "coolwarm") -> None:
    clean_matrix = [
        [float(value) if isinstance(value, (int, float)) and math.isfinite(value) else 0.0 for value in row]
        for row in matrix
    ]
    if not clean_matrix or not row_labels or not col_labels:
        _save_empty_png(path, title, "No matrix data available for this indicator.")
        return
    plt = _mpl()
    fig_w = max(6.8, min(12.5, 0.42 * len(col_labels) + 4.2))
    fig_h = max(5.6, min(12.0, 0.36 * len(row_labels) + 3.6))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=160)
    fig.patch.set_facecolor("white")
    image = ax.imshow(clean_matrix, cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(col_labels)), [_wrap_label(label, 10) for label in col_labels], rotation=45, ha="right")
    ax.set_yticks(range(len(row_labels)), [_wrap_label(label, 12) for label in row_labels])
    _style_axis(ax, title=title, subtitle=subtitle)
    ax.grid(False)
    colorbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.025)
    colorbar.ax.tick_params(labelsize=8, colors="#344054")
    fig.tight_layout(pad=1.3)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _png_metric_panel(path: Path, title: str, metrics: list[tuple[str, str]], *, subtitle: str = "") -> None:
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(8.4, 4.2), dpi=160)
    fig.patch.set_facecolor("white")
    ax.axis("off")
    ax.text(0.02, 0.96, title, transform=ax.transAxes, fontsize=15, fontweight="bold", color=_SCIENTIFIC_COLORS["navy"], va="top")
    if subtitle:
        ax.text(0.02, 0.86, subtitle, transform=ax.transAxes, fontsize=9, color=_SCIENTIFIC_COLORS["gray"], va="top")
    cols = 2
    start_y = 0.68
    row_h = 0.2
    for idx, (label, value) in enumerate(metrics):
        col = idx % cols
        row = idx // cols
        x = 0.04 + col * 0.48
        y = start_y - row * row_h
        ax.add_patch(plt.Rectangle((x, y - 0.09), 0.42, 0.13, transform=ax.transAxes, color="#f8fafc", ec="#d7dee8", lw=0.8))
        ax.text(x + 0.02, y + 0.01, str(label), transform=ax.transAxes, fontsize=8.5, color=_SCIENTIFIC_COLORS["gray"], va="center")
        ax.text(x + 0.02, y - 0.045, str(value), transform=ax.transAxes, fontsize=12, fontweight="bold", color=_SCIENTIFIC_COLORS["navy"], va="center")
    fig.tight_layout(pad=1.1)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _svg_text(x: float, y: float, text_value: str, *, size: int = 12, anchor: str = "start", weight: str = "normal", fill: str = "#1f2937") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Inter, Segoe UI, Arial, sans-serif" '
        f'font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{fill}">'
        f"{html.escape(text_value)}</text>"
    )


def _svg_rect(x: float, y: float, width: float, height: float, fill: str, *, stroke: str = "#ffffff", stroke_width: float = 1.0, rx: float = 2.0) -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
        f'rx="{rx:.1f}" ry="{rx:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width:.1f}" />'
    )


def _svg_doc(width: int, height: int, title: str, body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{html.escape(title)}">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"{body}\n"
        "</svg>\n"
    )


def _svg_bar_chart(title: str, items: list[tuple[str, float]], *, width: int = 960, height: int = 320, subtitle: str = "") -> str:
    left = 50
    top = 48
    bottom = 50
    right = 30
    plot_w = width - left - right
    plot_h = height - top - bottom
    body: list[str] = [
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />',
        _svg_text(left, 24, title, size=18, weight="700"),
    ]
    if subtitle:
        body.append(_svg_text(left, 42, subtitle, size=11, fill="#4b5563"))
    if not items:
        body.append(_svg_text(left, top + plot_h / 2, "No numeric data available", size=13, fill="#6b7280"))
        return _svg_doc(width, height, title, "\n".join(body))
    values = [value for _, value in items if math.isfinite(value)]
    if not values:
        values = [0.0]
    maximum = max(values)
    minimum = min(0.0, min(values))
    if maximum <= minimum:
        maximum = minimum + 1.0
    body.extend(
        [
            _svg_rect(left, top, plot_w, plot_h, "#fafafa", stroke="#e5e7eb", rx=4),
            _svg_text(left, top + plot_h + 18, "Lower", size=10, fill="#6b7280"),
            _svg_text(left + plot_w, top + plot_h + 18, "Higher", size=10, anchor="end", fill="#6b7280"),
        ]
    )
    bar_gap = 10
    bar_width = max(12, (plot_w - bar_gap * (len(items) - 1)) / max(len(items), 1))
    for idx, (label, value) in enumerate(items):
        x = left + idx * (bar_width + bar_gap)
        ratio = 0.0 if maximum <= minimum else (value - minimum) / (maximum - minimum)
        ratio = max(0.0, min(1.0, ratio))
        bar_h = ratio * plot_h
        y = top + plot_h - bar_h
        color = _PALETTE[idx % len(_PALETTE)]
        body.append(_svg_rect(x, y, bar_width, bar_h, color, stroke="#ffffff", rx=3))
        body.append(_svg_text(x + bar_width / 2, top + plot_h + 12, label[:14], size=10, anchor="middle", fill="#374151"))
        body.append(_svg_text(x + bar_width / 2, y - 4, f"{value:.3g}", size=10, anchor="middle", fill="#111827"))
    body.append(_svg_text(left, top + plot_h + 32, f"Range: {minimum:.3g} to {maximum:.3g}", size=10, fill="#6b7280"))
    return _svg_doc(width, height, title, "\n".join(body))


def _svg_line_chart(title: str, series: list[dict[str, Any]], *, width: int = 960, height: int = 320, subtitle: str = "") -> str:
    left = 56
    top = 48
    bottom = 48
    right = 24
    plot_w = width - left - right
    plot_h = height - top - bottom
    body: list[str] = [
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />',
        _svg_text(left, 24, title, size=18, weight="700"),
    ]
    if subtitle:
        body.append(_svg_text(left, 42, subtitle, size=11, fill="#4b5563"))
    all_values = [value for item in series for value in item.get("values", []) if isinstance(value, (int, float)) and math.isfinite(value)]
    if not all_values:
        body.append(_svg_text(left, top + plot_h / 2, "No time-series data available", size=13, fill="#6b7280"))
        return _svg_doc(width, height, title, "\n".join(body))
    minimum = min(all_values)
    maximum = max(all_values)
    if math.isclose(minimum, maximum):
        maximum = minimum + 1.0
    body.append(_svg_rect(left, top, plot_w, plot_h, "#fafafa", stroke="#e5e7eb", rx=4))
    for grid in range(5):
        y = top + plot_h * grid / 4
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1" />')
        tick = maximum - (maximum - minimum) * grid / 4
        body.append(_svg_text(left - 8, y + 4, f"{tick:.3g}", size=9, anchor="end", fill="#6b7280"))
    for idx, item in enumerate(series):
        values = [value for value in item.get("values", []) if isinstance(value, (int, float)) and math.isfinite(value)]
        if len(values) < 2:
            continue
        color = item.get("color") or _PALETTE[idx % len(_PALETTE)]
        points = []
        for point_idx, value in enumerate(values):
            x = left + (plot_w * point_idx / (len(values) - 1))
            ratio = (value - minimum) / (maximum - minimum)
            y = top + plot_h - max(0.0, min(1.0, ratio)) * plot_h
            points.append(f"{x:.1f},{y:.1f}")
        body.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />')
    legend_x = left
    legend_y = height - 22
    for idx, item in enumerate(series):
        label = item.get("name", f"series_{idx}")
        color = item.get("color") or _PALETTE[idx % len(_PALETTE)]
        body.append(_svg_rect(legend_x, legend_y - 10, 12, 12, color, stroke=color, rx=2))
        body.append(_svg_text(legend_x + 18, legend_y, label, size=10, fill="#374151"))
        legend_x += 18 + len(label) * 6.2 + 16
    return _svg_doc(width, height, title, "\n".join(body))


def _svg_heatmap(title: str, matrix: list[list[float]], row_labels: list[str], col_labels: list[str], *, width: int = 980, height: int = 900, subtitle: str = "") -> str:
    pad_left = 170
    pad_top = 120
    cell = 24
    plot_w = len(col_labels) * cell
    plot_h = len(row_labels) * cell
    width = max(width, pad_left + plot_w + 40)
    height = max(height, pad_top + plot_h + 80)
    body: list[str] = [
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />',
        _svg_text(24, 28, title, size=18, weight="700"),
    ]
    if subtitle:
        body.append(_svg_text(24, 46, subtitle, size=11, fill="#4b5563"))
    if not matrix or not row_labels or not col_labels:
        body.append(_svg_text(24, pad_top + 20, "No connectivity matrix available", size=13, fill="#6b7280"))
        return _svg_doc(width, height, title, "\n".join(body))
    flat_values = [value for row in matrix for value in row if isinstance(value, (int, float)) and math.isfinite(value)]
    minimum = min(flat_values) if flat_values else -1.0
    maximum = max(flat_values) if flat_values else 1.0
    if math.isclose(minimum, maximum):
        minimum, maximum = -1.0, 1.0
    body.append(_svg_rect(pad_left, pad_top, plot_w, plot_h, "#fafafa", stroke="#e5e7eb", rx=4))
    for col_idx, label in enumerate(col_labels):
        x = pad_left + col_idx * cell + cell / 2
        body.append(
            f'<text x="{x:.1f}" y="{pad_top - 10}" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="9" '
            f'text-anchor="end" fill="#374151" transform="rotate(-45 {x:.1f},{pad_top - 10:.1f})">{html.escape(label[:16])}</text>'
        )
    for row_idx, label in enumerate(row_labels):
        y = pad_top + row_idx * cell + cell * 0.68
        body.append(_svg_text(pad_left - 8, y, label[:18], size=9, anchor="end", fill="#374151"))
    for row_idx, row in enumerate(matrix):
        for col_idx, value in enumerate(row):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                fill = "#d1d5db"
            else:
                fill = _color_for_value(float(value), minimum, maximum)
            x = pad_left + col_idx * cell
            y = pad_top + row_idx * cell
            body.append(_svg_rect(x, y, cell, cell, fill, stroke="#ffffff", rx=0.5))
    body.append(_svg_text(pad_left, pad_top + plot_h + 24, f"Scale: {minimum:.3g} to {maximum:.3g}", size=10, fill="#6b7280"))
    return _svg_doc(width, height, title, "\n".join(body))


def _summary_cards(summary: dict[str, Any], modality: str) -> list[dict[str, str]]:
    provenance = summary.get("provenance") or {}
    outputs = summary.get("outputs") or {}
    cards = [
        {"label": "Task", "value": str(summary.get("task_id", "unknown"))},
        {"label": "Workflow", "value": str(summary.get("workflow_type", "unknown"))},
        {"label": "Spaces", "value": ", ".join(summary.get("spaces") or []) or "n/a"},
        {"label": "Sections", "value": str(len(outputs))},
    ]
    if modality == "T1":
        cards.extend(
            [
                {"label": "Brain measures", "value": str(provenance.get("parsed_counts", {}).get("brain_measures", "n/a"))},
                {"label": "Regions", "value": str(provenance.get("parsed_counts", {}).get("regions", "n/a"))},
                {"label": "Stats files", "value": str(provenance.get("parsed_counts", {}).get("stats_files", "n/a"))},
            ]
        )
    elif modality == "BOLD":
        cards.extend(
            [
                {"label": "Volumes", "value": str(summary.get("provenance", {}).get("n_volumes", summary.get("n_volumes", "n/a")))},
                {"label": "TR (s)", "value": str(summary.get("provenance", {}).get("tr_seconds", summary.get("tr_seconds", "n/a")))},
                {"label": "Seeds", "value": str(summary.get("provenance", {}).get("seed_count", "n/a"))},
            ]
        )
    elif modality == "DWI":
        cards.extend(
            [
                {"label": "Runtime (s)", "value": str(provenance.get("runtime_sec", "n/a"))},
                {"label": "Limit (s)", "value": str(provenance.get("max_runtime_sec", "n/a"))},
                {"label": "Atlas", "value": str(provenance.get("atlas", "n/a"))},
            ]
        )
    return cards


def _output_table_html(summary: dict[str, Any]) -> str:
    outputs = summary.get("outputs") or {}
    rows: list[str] = [
        "<table>",
        "<thead><tr><th>Section</th><th>Name</th><th>Path</th><th>Notes</th></tr></thead>",
        "<tbody>",
    ]
    reports_dir = Path(summary.get("out_dir", ".")) / "reports"
    for section, items in outputs.items():
        for item in items:
            path = Path(item.get("path", ""))
            if not path:
                continue
            rel = _relative_to_reports(reports_dir, path)
            notes = []
            if item.get("space"):
                notes.append(f"space={item['space']}")
            if item.get("atlas"):
                notes.append(f"atlas={item['atlas']}")
            if item.get("feature_group"):
                notes.append(f"group={item['feature_group']}")
            rows.append(
                "<tr>"
                f"<td>{html.escape(section)}</td>"
                f"<td><a href=\"{html.escape(rel)}\" download>{html.escape(item.get('name', path.name))}</a></td>"
                f"<td>{html.escape(rel)}</td>"
                f"<td>{html.escape('; '.join(notes))}</td>"
                "</tr>"
            )
    rows.extend(["</tbody>", "</table>"])
    return "\n".join(rows)


def _build_report_html(title: str, modality: str, summary: dict[str, Any], sections: list[dict[str, Any]], notes: list[str]) -> str:
    cards = "".join(
        "<div class=\"card\"><div class=\"label\">{label}</div><div class=\"value\">{value}</div></div>".format(
            label=html.escape(card["label"]),
            value=html.escape(card["value"]),
        )
        for card in _summary_cards(summary, modality)
    )
    section_html = []
    for section in sections:
        section_html.append(
            f'<section><h2>{html.escape(section["title"])}</h2>{section["body"]}</section>'
        )
    notes_html = "".join(f"<li>{html.escape(note)}</li>" for note in notes)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f5;
      --panel: #ffffff;
      --line: #d9dde3;
      --text: #1f2937;
      --muted: #5b6472;
      --accent: #184e77;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, Segoe UI, Arial, sans-serif;
      line-height: 1.45;
    }}
    main {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{
      margin: 0 0 6px 0;
      font-size: 28px;
    }}
    .subtitle {{
      color: var(--muted);
      margin: 0 0 18px 0;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin: 18px 0 20px 0;
    }}
    .card, section, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }}
    .label {{
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .value {{
      font-size: 18px;
      font-weight: 700;
      margin-top: 4px;
    }}
    section {{
      margin: 18px 0;
    }}
    section h2 {{
      margin: 0 0 10px 0;
      font-size: 20px;
    }}
    figure {{
      margin: 0 0 18px 0;
    }}
    figure img, figure object {{
      width: 100%;
      max-width: 100%;
      display: block;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 6px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 700;
      background: #fcfcfb;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
    }}
    .note {{
      color: var(--muted);
      font-size: 13px;
    }}
    .artifacts a {{
      color: var(--accent);
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <p class="subtitle">{html.escape(modality)} scientific report generated from backend outputs on {_now_iso()}</p>
    <div class="cards">{cards}</div>
    {''.join(section_html)}
    <section class="artifacts">
      <h2>Registered Artifacts</h2>
      {_output_table_html(summary)}
    </section>
    <section>
      <h2>Report Notes</h2>
      <ul>{notes_html}</ul>
    </section>
  </main>
</body>
</html>
"""


def _report_output_item(path: Path, name: str, *, description: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "path": path,
        "feature_group": REPORT_FEATURE_GROUP,
        "description": description,
    }


def _render_t1(summary: dict[str, Any], reports_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    provenance = summary.get("provenance") or {}
    brain_rows = _read_tsv_rows(_path_for(summary, "t1_brain_measures"))
    region_rows = _read_tsv_rows(_path_for(summary, "t1_t1w_regions"))
    inventory_rows = _read_tsv_rows(_path_for(summary, "t1_freesurfer_stats_inventory"))
    brain_chart_items = []
    for row in brain_rows[:8]:
        value = _safe_float(row.get("value"))
        if value is None:
            continue
        brain_chart_items.append((row.get("measure") or row.get("metric") or "measure", value))
    region_chart_items = []
    sortable_regions = []
    for row in region_rows:
        thickness = _safe_float(row.get("cortical_thickness_mm"))
        if thickness is None:
            continue
        sortable_regions.append((row.get("region") or "region", thickness))
    sortable_regions.sort(key=lambda item: item[1], reverse=True)
    region_chart_items = sortable_regions[:8]
    overview_png = reports_dir / "t1_brain_measures_overview.png"
    regions_png = reports_dir / "t1_region_thickness.png"
    _png_bar_chart(
        overview_png,
        "T1 brain measures",
        brain_chart_items,
        subtitle="Representative FreeSurfer-derived measures parsed from the real DeepPrep output",
        ylabel="Parsed value",
    )
    _png_bar_chart(
        regions_png,
        "T1 cortical thickness by region",
        region_chart_items,
        subtitle="Highest cortical thickness regions in the parsed T1w summary",
        ylabel="Thickness (mm)",
    )
    sections = [
        {
            "title": "T1 overview",
            "body": f"""
            <figure><img src="{overview_png.name}" alt="T1 brain measures overview" /></figure>
            <figure><img src="{regions_png.name}" alt="T1 region thickness overview" /></figure>
            <div class="panel">
              <p><strong>Extraction status:</strong> {html.escape(str(provenance.get("extraction_status", "unknown")))}</p>
              <p><strong>Parsed counts:</strong> {html.escape(json.dumps(provenance.get("parsed_counts", {}), ensure_ascii=False))}</p>
            </div>
            """,
        },
        {
            "title": "Brain measures",
            "body": _table_or_message(
                brain_rows,
                ["measure", "metric", "description", "value", "unit"],
                empty_message="No brain measures were parsed.",
            ),
        },
        {
            "title": "Regional measures",
            "body": _table_or_message(
                region_rows[:20],
                ["region", "space", "source_hemi", "num_vertices", "surface_area_mm2", "gray_matter_volume_mm3", "cortical_thickness_mm"],
                empty_message="No regional measures were parsed.",
            ),
        },
        {
            "title": "Stats inventory",
            "body": _table_or_message(
                inventory_rows,
                ["file", "measure_count", "data_row_count", "colheaders", "path"],
                empty_message="No FreeSurfer inventory rows found.",
            ),
        },
    ]
    notes = [
        "T1 report figures are generated from the parsed DeepPrep/Freesurfer outputs.",
        "MNI152 references in T1 remain transform/map references only; no invented regional MNI values are added.",
        "The report is a presentation layer on top of the result-summary contract.",
    ]
    html_path = reports_dir / "index.html"
    html_path.write_text(_build_report_html("T1 Scientific Report", "T1", summary, sections, notes), encoding="utf-8")
    manifest_path = reports_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "modality": "T1",
                "generated_at": _now_iso(),
                "sections": [section["title"] for section in sections],
                "assets": [html_path.name, "report_manifest.json", overview_png.name, regions_png.name],
                "source_outputs": list((summary.get("outputs") or {}).keys()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return [
        _report_output_item(html_path, "scientific_report_index", description="T1 scientific report HTML"),
        _report_output_item(manifest_path, "scientific_report_manifest", description="T1 scientific report manifest"),
        _report_output_item(overview_png, "t1_brain_measures_overview_png", description="T1 brain measure chart"),
        _report_output_item(regions_png, "t1_region_thickness_png", description="T1 regional thickness chart"),
    ], sections, notes


def _table_or_message(rows: list[dict[str, str]], columns: list[str], *, empty_message: str) -> str:
    if not rows:
        return f'<div class="note">{html.escape(empty_message)}</div>'
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body_rows = []
    for row in rows[:20]:
        cells = []
        for column in columns:
            value = row.get(column, "")
            cells.append(f"<td>{html.escape(str(value))}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return "<table><thead><tr>" + header + "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table>"


def _render_bold(summary: dict[str, Any], reports_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    metric_summary = _load_json(_path_for(summary, "bold_metrics_summary"))
    provenance = summary.get("provenance") or {}
    seed_rows = _read_tsv_rows(_path_for(summary, "seed_to_roi"))
    fd_rows = _read_tsv_rows(_path_for(summary, "fd_timeseries"))
    dvars_rows = _read_tsv_rows(_path_for(summary, "dvars_timeseries"))
    whole_rows = _read_tsv_rows(_path_for(summary, "wholebrain_timeseries"))
    psd_rows = _read_tsv_rows(_path_for(summary, "mean_psd"))
    seed_timeseries_rows = _read_tsv_rows(_path_for(summary, "seed_timeseries"))
    seed_records = metric_summary.get("seeds") or []
    seed_ids = [record.get("preset_id") or record.get("seed_id") or f"seed_{idx}" for idx, record in enumerate(seed_records)]
    if not seed_ids:
        seed_ids = sorted({row.get("seed_id", "") for row in seed_rows if row.get("seed_id")})[:15]
    matrix: list[list[float]] = []
    if seed_ids and seed_rows:
        lookup: dict[tuple[str, str], float] = {}
        for row in seed_rows:
            seed_id = row.get("seed_id")
            roi_id = row.get("roi_id")
            corr = _safe_float(row.get("correlation_r"))
            if seed_id and roi_id and corr is not None:
                lookup[(seed_id, roi_id)] = corr
        for seed_id in seed_ids:
            matrix.append([lookup.get((seed_id, roi_id), 0.0) for roi_id in seed_ids])
    qc_series = []
    fd_values = [_safe_float(row.get("framewise_displacement")) for row in fd_rows if _safe_float(row.get("framewise_displacement")) is not None]
    dvars_values = [_safe_float(row.get("dvars")) for row in dvars_rows if _safe_float(row.get("dvars")) is not None]
    whole_values = [_safe_float(row.get("whole_brain_signal")) for row in whole_rows if _safe_float(row.get("whole_brain_signal")) is not None]
    if fd_values:
        qc_series.append({"name": "Framewise displacement", "values": fd_values, "color": _PALETTE[0]})
    if dvars_values:
        qc_series.append({"name": "DVARS", "values": dvars_values, "color": _PALETTE[1]})
    if whole_values:
        qc_series.append({"name": "Whole-brain signal", "values": whole_values, "color": _PALETTE[2]})
    voxelwise_means = metric_summary.get("voxelwise_means") or {}
    metric_cards = [(key, float(value)) for key, value in voxelwise_means.items() if _safe_float(value) is not None]
    if not metric_cards:
        metric_cards = []
    if metric_cards:
        metric_cards.sort(key=lambda item: item[0])
    voxel_png = reports_dir / "bold_voxelwise_metrics.png"
    qc_png = reports_dir / "bold_qc_timeseries.png"
    seed_png = reports_dir / "bold_seed_connectivity_heatmap.png"
    _png_bar_chart(
        voxel_png,
        "BOLD voxel-wise summary",
        [(label, value) for label, value in metric_cards],
        subtitle="Mean values extracted from the downstream BOLD metric bundle",
        ylabel="Mean metric value",
    )
    _png_line_chart(
        qc_png,
        "BOLD QC traces",
        qc_series,
        subtitle="Framewise displacement, DVARS, and whole-brain signal traces from the real outputs",
        ylabel="QC value",
    )
    _png_heatmap(
        seed_png,
        "BOLD seed-to-ROI connectivity",
        matrix,
        seed_ids,
        seed_ids,
        subtitle="Correlation matrix derived from the seed MNI152 connectivity table",
        cmap="coolwarm",
    )
    psd_png = reports_dir / "bold_mean_psd.png"
    if psd_rows:
        freq_series = []
        freqs = []
        amps = []
        for row in psd_rows:
            freq = _safe_float(row.get("frequency_hz"))
            amp = _safe_float(row.get("mean_amplitude"))
            if freq is None or amp is None:
                continue
            freqs.append(freq)
            amps.append(amp)
        if freqs and amps:
            _png_line_chart(
                psd_png,
                "BOLD mean power spectrum",
                [{"name": "mean amplitude", "values": amps, "color": _SCIENTIFIC_COLORS["red"]}],
                subtitle=f"Frequency range {min(freqs):.3g} to {max(freqs):.3g} Hz",
                ylabel="Mean amplitude",
            )
        else:
            _save_empty_png(psd_png, "BOLD mean power spectrum", "No PSD values available.")
    else:
        _save_empty_png(psd_png, "BOLD mean power spectrum", "No PSD values available.")
    sections = [
        {
            "title": "BOLD overview",
            "body": f"""
            <figure><img src="{voxel_png.name}" alt="BOLD voxel-wise metric summary" /></figure>
            <figure><img src="{qc_png.name}" alt="BOLD QC traces" /></figure>
            <figure><img src="{seed_png.name}" alt="BOLD seed connectivity heatmap" /></figure>
            <figure><img src="{psd_png.name}" alt="BOLD power spectrum" /></figure>
            """,
        },
        {
            "title": "Seed connectivity",
            "body": _table_or_message(
                seed_rows,
                ["seed_id", "seed_label", "seed_family", "roi_id", "roi_label", "roi_family", "correlation_r", "correlation_z", "space"],
                empty_message="No seed-to-ROI rows found.",
            ),
        },
        {
            "title": "QC traces",
            "body": _table_or_message(
                fd_rows[:20] + dvars_rows[:0],
                ["volume_index", "framewise_displacement", "dvars", "std_dvars"],
                empty_message="No QC timeseries rows found.",
            ),
        },
        {
            "title": "Whole-brain signal",
            "body": _table_or_message(
                whole_rows,
                ["volume_index", "whole_brain_signal"],
                empty_message="No whole-brain timeseries rows found.",
            ),
        },
        {
            "title": "Seed inventory",
            "body": _table_or_message(
                seed_timeseries_rows[:20],
                ["volume_index"] + seed_ids[:8],
                empty_message="No seed timeseries table found.",
            ),
        },
    ]
    notes = [
        "BOLD report assets are generated from the downstream metric bundle and MNI152 outputs.",
        "The heatmap uses the 15 seed presets that drive the real seed-to-ROI tables.",
        "The report keeps the raw result-summary contract as the source of truth and adds a presentation layer on top.",
    ]
    html_path = reports_dir / "index.html"
    html_path.write_text(_build_report_html("BOLD Scientific Report", "BOLD", summary, sections, notes), encoding="utf-8")
    manifest_path = reports_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "modality": "BOLD",
                "generated_at": _now_iso(),
                "sections": [section["title"] for section in sections],
                "assets": [html_path.name, "report_manifest.json", voxel_png.name, qc_png.name, seed_png.name, psd_png.name],
                "seed_count": len(seed_ids),
                "metrics": list(voxelwise_means.keys()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return [
        _report_output_item(html_path, "scientific_report_index", description="BOLD scientific report HTML"),
        _report_output_item(manifest_path, "scientific_report_manifest", description="BOLD scientific report manifest"),
        _report_output_item(voxel_png, "bold_voxelwise_metrics_png", description="BOLD voxel-wise summary chart"),
        _report_output_item(qc_png, "bold_qc_timeseries_png", description="BOLD QC traces"),
        _report_output_item(seed_png, "bold_seed_connectivity_heatmap_png", description="BOLD seed connectivity heatmap"),
        _report_output_item(psd_png, "bold_mean_psd_png", description="BOLD mean power spectrum"),
    ], sections, notes


def _render_dwi(summary: dict[str, Any], reports_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    provenance = summary.get("provenance") or {}
    combined_rows = _read_tsv_rows(_path_for(summary, "combined_region_dti"))
    metric_rows = {
        metric: _read_tsv_rows(_path_for(summary, f"{metric}_regions"))
        for metric in ("fa", "md", "ad", "rd")
    }
    metric_means: list[tuple[str, float]] = []
    for metric, rows in metric_rows.items():
        values = [_safe_float(row.get("mean")) for row in rows if _safe_float(row.get("mean")) is not None]
        if values:
            metric_means.append((metric.upper(), sum(values) / len(values)))
    if not metric_means and combined_rows:
        for metric in ("fa", "md", "ad", "rd"):
            values = [_safe_float(row.get(metric)) for row in combined_rows if _safe_float(row.get(metric)) is not None]
            if values:
                metric_means.append((metric.upper(), sum(values) / len(values)))
    metric_png = reports_dir / "dwi_tensor_metrics.png"
    _png_bar_chart(
        metric_png,
        "DWI tensor metrics",
        metric_means,
        subtitle="Mean regional values from the native and MNI152 DTI tables",
        ylabel="Mean regional value",
    )
    sanitization = provenance.get("metric_sanitization") or {}
    native_replacements = sum(
        int(info.get("nonfinite_replaced", 0)) for info in (sanitization.get("native") or {}).values()
    ) if isinstance(sanitization.get("native"), dict) else 0
    mni_replacements = sum(
        int(info.get("nonfinite_replaced", 0)) for info in (sanitization.get("mni152") or {}).values()
    ) if isinstance(sanitization.get("mni152"), dict) else 0
    runtime_png = reports_dir / "dwi_runtime_registration.png"
    _png_metric_panel(
        runtime_png,
        "DWI runtime and registration",
        [
            ("Runtime (s)", str(provenance.get("runtime_sec", "n/a"))),
            ("Runtime limit (s)", str(provenance.get("max_runtime_sec", "n/a"))),
            ("Atlas", str(provenance.get("atlas", "n/a"))),
            ("Registration", str(provenance.get("mni_registration_method", "n/a"))),
            ("Subset volumes", str(provenance.get("dti_subset_metadata", {}).get("selected_volume_count", "n/a"))),
            ("Native replacements", str(native_replacements)),
            ("MNI152 replacements", str(mni_replacements)),
        ],
        subtitle="Fast GPU DTI path, registration metadata, and sanitization audit",
    )
    atlas_png = reports_dir / "dwi_atlas_region_means.png"
    atlas_values = []
    for row in combined_rows[:12]:
        region = row.get("region") or "region"
        value = _safe_float(row.get("fa"))
        if value is None:
            continue
        atlas_values.append((region, value))
    _png_bar_chart(
        atlas_png,
        "DWI atlas regional FA",
        atlas_values,
        subtitle="Representative atlas-region values from the combined regional DTI table",
        ylabel="FA",
    )
    sections = [
        {
            "title": "DWI overview",
            "body": f"""
            <figure><img src="{metric_png.name}" alt="DWI tensor metrics" /></figure>
            <figure><img src="{runtime_png.name}" alt="DWI runtime and registration summary" /></figure>
            <figure><img src="{atlas_png.name}" alt="DWI atlas region summary" /></figure>
            """,
        },
        {
            "title": "Combined region table",
            "body": _table_or_message(
                combined_rows[:20],
                ["region", "fa", "md", "ad", "rd", "atlas"],
                empty_message="No combined DWI table rows found.",
            ),
        },
        {
            "title": "Metric-specific regional tables",
            "body": "\n".join(
                f"<h3>{metric.upper()}</h3>" + _table_or_message(rows[:12], ["region", "metric", "mean", "atlas"], empty_message=f"No {metric.upper()} rows found.")
                for metric, rows in metric_rows.items()
            ),
        },
    ]
    notes = [
        "DWI report assets are generated from the fast GPU DTI outputs and MNI152 registration summary.",
        "The report preserves the fast-production DTI path and does not substitute the legacy QSI container workflow.",
        "Non-finite replacements are reported so that the presentation layer remains scientifically honest.",
    ]
    html_path = reports_dir / "index.html"
    html_path.write_text(_build_report_html("DWI Scientific Report", "DWI", summary, sections, notes), encoding="utf-8")
    manifest_path = reports_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "modality": "DWI",
                "generated_at": _now_iso(),
                "sections": [section["title"] for section in sections],
                "assets": [html_path.name, "report_manifest.json", metric_png.name, runtime_png.name, atlas_png.name],
                "atlas": provenance.get("atlas"),
                "registration_method": provenance.get("mni_registration_method"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return [
        _report_output_item(html_path, "scientific_report_index", description="DWI scientific report HTML"),
        _report_output_item(manifest_path, "scientific_report_manifest", description="DWI scientific report manifest"),
        _report_output_item(metric_png, "dwi_tensor_metrics_png", description="DWI tensor metric chart"),
        _report_output_item(runtime_png, "dwi_runtime_registration_png", description="DWI runtime and registration summary"),
        _report_output_item(atlas_png, "dwi_atlas_region_means_png", description="DWI atlas regional summary"),
    ], sections, notes


def _render_generic(summary: dict[str, Any], reports_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    html_path = reports_dir / "index.html"
    html_path.write_text(
        _build_report_html(
            f"{summary.get('modality', 'Unknown')} Scientific Report",
            str(summary.get("modality", "UNKNOWN")),
            summary,
            [{"title": "Overview", "body": "<div class=\"note\">No modality-specific renderer available.</div>"}],
            ["A generic report was generated because no modality-specific renderer matched this summary."],
        ),
        encoding="utf-8",
    )
    manifest_path = reports_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "modality": summary.get("modality"),
                "generated_at": _now_iso(),
                "sections": ["Overview"],
                "assets": [html_path.name, "report_manifest.json"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return [
        _report_output_item(html_path, "scientific_report_index", description="Scientific report HTML"),
        _report_output_item(manifest_path, "scientific_report_manifest", description="Scientific report manifest"),
    ], [{"title": "Overview", "body": "<div class=\"note\">No modality-specific renderer available.</div>"}], ["A generic report was generated because no modality-specific renderer matched this summary."]


def build_scientific_report_bundle(out_dir: Path, summary: dict[str, Any]) -> list[dict[str, Any]]:
    out_dir = Path(out_dir)
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    modality = str(summary.get("modality") or "").upper()
    summary = dict(summary)
    summary["out_dir"] = str(out_dir)
    if modality == "T1":
        outputs, _, _ = _render_t1(summary, reports_dir)
    elif modality == "BOLD":
        outputs, _, _ = _render_bold(summary, reports_dir)
    elif modality == "DWI":
        outputs, _, _ = _render_dwi(summary, reports_dir)
    else:
        outputs, _, _ = _render_generic(summary, reports_dir)
    return outputs


def _summary_report_relative_path(item: dict[str, Any]) -> str:
    return str(item.get("relative_path") or item.get("path") or "")


def _is_generated_scientific_report_item(item: dict[str, Any]) -> bool:
    relative_path = _summary_report_relative_path(item).replace("\\", "/")
    return (
        item.get("source_stage") == "scientific_report"
        or item.get("artifact_role") == "derived_presentation_asset"
        or item.get("artifact_origin") == "generated_from_result_summary"
        or relative_path.startswith("reports/")
    )


def _merge_report_outputs(existing_reports: Any, report_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = existing_reports if isinstance(existing_reports, list) else []
    generated_paths = {_summary_report_relative_path(item) for item in report_outputs if isinstance(item, dict)}
    preserved = [
        item
        for item in existing
        if isinstance(item, dict)
        and _summary_report_relative_path(item) not in generated_paths
        and not _is_generated_scientific_report_item(item)
    ]
    return [*preserved, *report_outputs]


def build_scientific_report_summary(out_dir: Path, task_id: int, workflow_type: str, summary: dict[str, Any]) -> Path:
    modality = str(summary.get("modality") or "").upper() or "UNKNOWN"
    report_items = build_scientific_report_bundle(out_dir, summary)
    from app.workflows.result_contract import build_scientific_report_summary as _build_summary

    report_summary_path = _build_summary(
        out_dir=out_dir,
        task_id=task_id,
        workflow_type=workflow_type,
        modality=modality,
        spaces=list(summary.get("spaces") or []),
        feature_groups=list(summary.get("feature_groups") or []),
        report_items=report_items,
        provenance={
            "source_summary": summary.get("summary_path"),
            "report_assets": [item.get("relative_path") for item in report_items],
        },
        summary_name=f"{modality.lower()}_scientific_report_summary.json",
    )
    source_summary_path = summary.get("summary_path")
    if source_summary_path:
        source_path = Path(str(source_summary_path))
        if source_path.exists():
            try:
                source_payload = json.loads(source_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                source_payload = None
            if isinstance(source_payload, dict):
                try:
                    report_payload = json.loads(report_summary_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    report_payload = {}
                report_outputs = (report_payload.get("outputs") or {}).get("reports") or []
                outputs = source_payload.setdefault("outputs", {})
                outputs["reports"] = _merge_report_outputs(outputs.get("reports"), report_outputs)
                provenance = source_payload.setdefault("provenance", {})
                provenance["scientific_report_summary_path"] = str(report_summary_path)
                provenance["scientific_report_report_count"] = len(report_outputs)
                source_path.write_text(json.dumps(source_payload, indent=2), encoding="utf-8")
    return report_summary_path
