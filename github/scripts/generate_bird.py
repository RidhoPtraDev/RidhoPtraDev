#!/usr/bin/env python3
"""
Generate animasi SVG: burung terbang menyapu contribution graph GitHub
dan "memakan" setiap kotak kontribusi. Tanpa dependency (stdlib saja).

Pemakaian:
  python generate_bird.py --user USERNAME --out dist/bird.svg     (butuh env GITHUB_TOKEN)
  python generate_bird.py --demo --out demo.svg                   (data acak, untuk tes)
"""
import argparse
import json
import math
import os
import random
import sys
import urllib.request

# ------------------------- KONFIGURASI (boleh diubah) -------------------------
CELL = 12          # ukuran kotak
GAP = 3            # jarak antar kotak
DURATION = 32      # detik per loop
FLIGHT = 0.90      # porsi loop untuk terbang (sisanya jeda + kotak tumbuh lagi)

# warna kotak: level 0 (kosong) sampai 4 (paling aktif) - tema cyan
CELL_COLORS = ["#161B22", "#0B4F63", "#0A7C99", "#00A8CC", "#00D4FF"]

# warna burung
BODY = "#FFC857"
WING = "#FF9F1C"
BEAK = "#FF6B35"
EYE = "#0D1117"
# ------------------------------------------------------------------------------

PITCH = CELL + GAP
PAD = int(PITCH * 2.6)   # ruang kosong kiri/kanan agar burung bisa berbelok
PAD_Y = 22

LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { weekday contributionLevel } }
      }
    }
  }
}
"""


def fetch_grid(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "bird-contribution-graph",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if data.get("errors") or not data.get("data", {}).get("user"):
        sys.exit(f"Gagal ambil data GitHub: {data.get('errors')}")
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    cells = []
    for c, week in enumerate(weeks):
        for day in week["contributionDays"]:
            cells.append((c, day["weekday"], LEVELS[day["contributionLevel"]]))
    return len(weeks), cells


def demo_grid(weeks=53, seed=7):
    rnd = random.Random(seed)
    cells = []
    for c in range(weeks):
        for r in range(7):
            cells.append((c, r, rnd.choices([0, 1, 2, 3, 4], [40, 20, 18, 14, 8])[0]))
    return weeks, cells


def xc(col):
    return PAD + col * PITCH + CELL / 2


def yc(row):
    return PAD_Y + row * PITCH + CELL / 2


def build_path(weeks):
    """Jalur terbang: sapu baris demi baris, kiri->kanan lalu kanan->kiri."""
    pts, turns = [], []   # turns: index titik awal segmen vertikal
    for r in range(7):
        d = 1 if r % 2 == 0 else -1
        cols = list(range(weeks)) if d == 1 else list(range(weeks - 1, -1, -1))
        pts.append((xc(cols[0] - 2 * d), yc(r)))
        for c in cols:
            pts.append((xc(c), yc(r)))
        pts.append((xc(cols[-1] + 2 * d), yc(r)))
        if r < 6:
            turns.append(len(pts) - 1)
    return pts, turns


def cumulative(pts):
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    return cum


def f(v):
    return f"{v:.5f}".rstrip("0").rstrip(".")


def bird_svg(flip_values, flip_times, motion_path, key_times):
    return f"""
  <g>
    <animateMotion dur="{DURATION}s" repeatCount="indefinite" calcMode="linear"
      keyPoints="0;1;1" keyTimes="0;{f(FLIGHT)};1" path="{motion_path}"/>
    <animate attributeName="opacity" dur="{DURATION}s" repeatCount="indefinite"
      values="0;1;1;0;0" keyTimes="0;0.01;{f(FLIGHT - 0.005)};{f(FLIGHT + 0.01)};1"/>
    <g>
      <animateTransform attributeName="transform" type="scale" calcMode="discrete"
        dur="{DURATION}s" repeatCount="indefinite"
        values="{flip_values}" keyTimes="{flip_times}"/>
      <!-- ekor -->
      <polygon points="-6,-1 -13,-4.5 -12,1.5 -6,2" fill="{WING}"/>
      <!-- badan -->
      <ellipse cx="0" cy="0" rx="7.5" ry="4.6" fill="{BODY}"/>
      <!-- kepala -->
      <circle cx="6.5" cy="-2.6" r="3.2" fill="{BODY}"/>
      <polygon points="9,-3.4 13,-2.2 9,-1.2" fill="{BEAK}"/>
      <circle cx="7.4" cy="-3.3" r="0.8" fill="{EYE}"/>
      <!-- sayap mengepak -->
      <g transform="translate(-1.5,-1)">
        <g>
          <animateTransform attributeName="transform" type="scale" dur="0.32s"
            repeatCount="indefinite" values="1 1;1 -0.75;1 1"/>
          <path d="M2,0 Q1,-11 -9,-10 Q-5,-5 -4,0 Z" fill="{WING}"/>
        </g>
      </g>
    </g>
  </g>"""


def generate(weeks, cells):
    pts, turns = build_path(weeks)
    cum = cumulative(pts)
    total = cum[-1]

    def t_at(dist):
        return dist / total * FLIGHT

    # posisi -> waktu saat burung melewati pusat kotak
    time_of = {}
    idx = 0
    for r in range(7):
        d = 1 if r % 2 == 0 else -1
        idx += 1  # lewati titik masuk
        cols = range(weeks) if d == 1 else range(weeks - 1, -1, -1)
        for c in cols:
            time_of[(c, r)] = t_at(cum[idx])
            idx += 1
        idx += 1  # lewati titik keluar

    # waktu berbalik arah (tengah segmen vertikal)
    flip_vals, flip_times = ["1 1"], ["0"]
    for i, ti in enumerate(turns):
        mid = cum[ti] + PITCH / 2
        flip_vals.append("-1 1" if i % 2 == 0 else "1 1")
        flip_times.append(f(t_at(mid)))
    flip_vals.append(flip_vals[-1])
    flip_times.append("1")

    width = 2 * PAD + weeks * PITCH - GAP
    height = 2 * PAD_Y + 7 * PITCH - GAP

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="Bird eating contribution graph">'
    ]

    empty = CELL_COLORS[0]
    for c, r, level in cells:
        x, y = PAD + c * PITCH, PAD_Y + r * PITCH
        color = CELL_COLORS[level]
        rect = f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{color}"'
        if level == 0 or (c, r) not in time_of:
            out.append(rect + "/>")
            continue
        t = time_of[(c, r)]
        out.append(
            rect + f'><animate attributeName="fill" dur="{DURATION}s" repeatCount="indefinite" '
            f'values="{color};{color};{empty};{empty};{color}" '
            f'keyTimes="0;{f(t)};{f(t + 0.004)};{f(FLIGHT + 0.06)};1"/></rect>'
        )

    motion_path = "M" + " L".join(f"{f(x)} {f(y)}" for x, y in pts)
    out.append(bird_svg(";".join(flip_vals), ";".join(flip_times), motion_path, None))
    out.append("</svg>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", help="username GitHub")
    ap.add_argument("--out", default="dist/github-contribution-grid-bird-dark.svg")
    ap.add_argument("--demo", action="store_true", help="pakai data acak (tanpa API)")
    args = ap.parse_args()

    if args.demo:
        weeks, cells = demo_grid()
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not args.user or not token:
            sys.exit("Butuh --user dan env GITHUB_TOKEN (atau pakai --demo).")
        weeks, cells = fetch_grid(args.user, token)

    svg = generate(weeks, cells)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"OK -> {args.out} ({len(svg) // 1024} KB)")


if __name__ == "__main__":
    main()
