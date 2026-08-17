# Status Board / Leaderboard — reusable build spec

A single-file **SVG** that shows, in one glance, how complete a system is: a compact
**module map** on top, a ranked **completeness leaderboard** below it, an **auxiliary**
section for things that don't count toward the core score, and a footer legend.

This document is project-independent. It describes the *format and rules*, not any one
system's modules. Drop your own modules and numbers into the structure and it works for any
project.

---

## 1. What the artifact is for

One picture that answers three questions at once:

1. **What are the parts and how do they connect?** → the map header.
2. **How done is each part, ranked worst-to-best visibility?** → the leaderboard.
3. **What doesn't count toward "done" and why?** → the auxiliary section.

Keep it to a single SVG so it renders inline anywhere, versions cleanly in git, and needs no
runtime. Regenerate it at each milestone rather than editing in place.

---

## 2. Completeness — define it before you draw it

**The score is meaningless until "100%" is defined.** Pick a definition and put it in the
footer so the number can't be silently reinterpreted later. A useful default:

> **100% = code-complete + debugged + validated in simulation.** Live / production /
> end-to-end testing is explicitly **not** required for 100%.

Consequences of that choice, which the board must honour:

- A module whose code is done, gated, and proven against sims/fakes **is 100%** — the
  absence of live testing does not hold it back.
- What *does* hold a module below 100% is **unbuilt code, uncalled code, or unfinished
  sim-validation** — real gaps, not the live-test asterisk.
- If you choose a different bar (e.g. "100% includes production canary"), state *that* in the
  footer instead. The rule is: the definition is written on the artifact.

**Per-module %** is a judgement unless you have a derived metric. If you can derive it (e.g.
`code-complete × gate-bound × sim-validated`), do — and say so. If it's an estimate, treat
every number as a claim you'd defend, not a vibe.

---

## 3. Color bands (default)

| Band | Range | Fill (hex) | Text on fill |
|---|---|---|---|
| Complete | 90–100 | `#2ea043` (green) | white |
| Substantial | 70–89 | `#8bc34a` (light-green) | dark `#12210a` |
| Partial | 40–69 | `#e3b341` (amber) | dark `#241a02` |
| Early | 10–39 | `#db6d28` (orange) | dark `#1a1206` |
| Not started | 0–9 | `#545d68` (grey) | light `#c9d1d9` |

Special, off the completeness scale:

- **Plug-in slot** — a swappable component that is *required to run* but is not core
  infrastructure. Draw **off-scale**: dashed violet outline (`#8957c9` on `#1c1526`), no %.
  The *interface/contract* around the slot is infra and IS scored; the swappable thing behind
  it is not.
- **External / unscored** — third-party endpoints you don't build (a venue, an upstream API).
  Slate `#30363d`, labelled "external", no %.
- **Auxiliary** — real components you build but that don't count toward core completeness
  (read-only observability, dashboards). Scored on the normal bands, but **listed in a
  separate section** so they don't move the core aggregate.

Canvas: dark background `#0d1117`, panel fills `#161b22`/`#0f141b`, hairlines `#21262d`/`#30363d`,
body text `#e6edf3` / muted `#8b949e`.

---

## 4. Layout (top to bottom)

```
┌───────────────────────────────────────────────────────────┐
│ TITLE + one-line completeness definition                  │
├───────────────────────────────────────────────────────────┤
│ MODULE MAP (compact)                                      │
│   modules as boxes, colored by band, grouped by subsystem │
│   connectors typed + legended (see §5)                    │
│   plug-in slot (off-scale) · external (slate)             │
├───────────────────────────────────────────────────────────┤
│ COMPLETENESS LEADERBOARD                                  │
│   core modules, ranked DESCENDING by %                    │
│   row = rank | name | bar(track+fill) | %                 │
│   ── weighted INFRASTRUCTURE aggregate bar ──             │
├───────────────────────────────────────────────────────────┤
│ AUXILIARY (not counted in core %)                         │
│   plug-in slot(s) · observability · anything off-core     │
├───────────────────────────────────────────────────────────┤
│ FOOTER LEGEND: color bands + completeness definition      │
└───────────────────────────────────────────────────────────┘
```

### 4a. Leaderboard rows — the core of it

- **Rank descending by %** — best-done at top, or worst at top if you prefer to lead with
  the gaps; pick one and keep it. (Descending/best-first is the default.)
- Each row, left to right:
  - **rank number** (colored to the band)
  - **module name** (+ a muted sub-tag like the phase/subsystem that owns it)
  - **bar**: a full-width grey **track** (`#21262d`) with a colored **fill** whose width =
    `% × track_width`. Even 0% draws a tiny nub so the row reads as a bar, not a gap.
  - **% label**, right-aligned, colored to the band.
- After the last core row, a divider, then a **weighted aggregate** row ("INFRASTRUCTURE",
  or whatever the core set is called) with its own bar. Weight by rough size/effort if you
  can; a plain mean is fine if you say so.

### 4b. Auxiliary section

Everything that must not drag the core number: the plug-in slot (shown "off-scale"), the
dashboard / observability layer (shown on the bands but below the aggregate line, so it's
visibly *excluded* from the core %). Label the section "not counted in [core] %".

### 4c. Map header

A condensed version of the system's architecture diagram — enough to see the parts and the
primary flow. "Condensed" means **smaller boxes and tighter spacing, NOT fewer connectors.**
Boxes colored by the same bands so map and leaderboard agree at a glance.

**Connector completeness is mandatory (see also §6, rule 7).** The header must draw the
*full* typed connector set — every bus, every write path, every shared-memory channel, every
plug-in seam, every read-only subscriber, every not-yet-built link, plus the external
in/out arrows. Do **not** drop connectors to save space: a header that shows some tunnels but
not others misrepresents the architecture (it reads as "these are the only connections"),
which is the exact failure this format exists to avoid. If space is tight, shrink boxes,
thin the strokes, or grow the panel — never omit a typed connector. Include the connector
legend *inside* the map panel so every line drawn is identified.

---

## 5. Connector typing (map header)

Give every connector a *type* and legend it — a diagram where all lines look alike hides the
architecture. A reusable palette:

| Meaning | Style |
|---|---|
| Primary message/state bus | **thick** translucent band + thin bright line + arrow (e.g. cyan). Widest band = the most important bus. |
| Shared-memory / special-case channel | thick **dashed** band, distinct color (e.g. magenta), labelled as the exception |
| Plug-in contract seam | dashed line, the plug-in color (violet), arrow toward the consumer |
| In-process / zero-dependency call | solid thin line, distinct color (e.g. orange) |
| Durable write path (to a store) | solid thin line (e.g. blue) |
| Read-only subscriber (e.g. dashboard) | **thin** dashed line off the bus — visibly lighter than the bus itself |
| Not-yet-built / watch / future link | dashed grey |

Rule of thumb: **thickness = importance, dashing = "special or not-yet-real", color = kind.**

---

## 6. Rules that keep it honest

These are what stop the board from becoming a feel-good poster:

1. **The completeness definition is written on the artifact.** No floating "100%" without its
   meaning attached.
2. **Auxiliary and plug-in items never inflate the core aggregate.** They live below the
   aggregate line or off-scale. A dashboard at 15% must not make the system look 15% less done,
   and a swappable strategy at 5% must not make the infrastructure look unfinished.
3. **"Built" ≠ "called" ≠ "wired."** If a module's code exists but nothing invokes it, that's a
   real gap and the % must reflect it — flag it inline (a caution strip on the box) rather than
   rounding up. (This is the single most common way these boards lie.)
4. **Every number is a claim.** Estimate or derived — say which. Prefer a derived metric when
   one exists.
5. **Regenerate, don't patch.** Rebuild the whole board at each milestone from the current
   numbers so the map and the leaderboard can never drift apart. Keep the previous versions.
6. **Ranking direction is fixed once.** Don't flip best-first/worst-first between versions or
   the trend becomes unreadable.
7. **The map header carries the FULL connector set — never a subset.** Compress by shrinking
   boxes and strokes, not by dropping tunnels/lines. A diagram showing some connections but
   not others reads as "these are all the connections" and hides the architecture — the same
   class of lie as a green box that measures nothing. Every typed connector in the full map
   appears in the header, with an in-panel legend identifying each.

---

## 7. Minimal build recipe

1. List the **core modules**; assign each a band % under your stated definition.
2. List **auxiliary** items (observability, tooling) and **plug-in slots** separately.
3. Compute the **weighted aggregate** over core modules only.
4. Draw the **map header**: boxes by band, the **full** typed connector set (§4c/§5 — every
   bus, write path, shared-mem channel, plug-in seam, read-only subscriber, not-built link,
   and external in/out arrow), an in-panel connector legend, plug-in slot off-scale, external
   slate.
5. Draw the **leaderboard**: core rows ranked descending, track+fill bars, aggregate bar.
6. Draw the **auxiliary** rows below the aggregate line.
7. Draw the **footer legend**: bands + the completeness definition sentence.
8. Save as one SVG. Regenerate next milestone.

---

## 8. SVG scaffold (drop-in skeleton)

Coordinates assume a ~1200-wide canvas; the bar **track** runs `x=360 … 1000` (640 px wide),
so a fill for value `p` (0–100) has `width = 6.4 × p` (min ~6 px so 0% still shows a nub).

```xml
<svg viewBox="0 0 1200 1160" xmlns="http://www.w3.org/2000/svg"
     font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial">
  <rect x="0" y="0" width="1200" height="1160" fill="#0d1117"/>

  <!-- TITLE + definition -->
  <text x="40" y="46" fill="#e6edf3" font-size="26" font-weight="700">Project — status board</text>
  <text x="40" y="70" fill="#8b949e" font-size="13">Completeness = code + debug + sim (live not required for 100%).</text>

  <!-- MODULE MAP panel -->
  <rect x="40" y="90" width="1120" height="418" rx="14" fill="#0f141b" stroke="#21262d"/>
  <text x="58" y="116" fill="#6e7681" font-size="12" font-weight="700" letter-spacing="1">MODULE MAP</text>
  <!-- ... module boxes (fill = band color) + typed connectors + legend ... -->

  <!-- LEADERBOARD -->
  <text x="40" y="552" fill="#e6edf3" font-size="18" font-weight="700">Completeness leaderboard</text>

  <!-- one row template (repeat, y += 32), fill width = 6.4 * pct -->
  <g font-size="14">
    <text x="52" y="616" fill="#7ee787" font-weight="700">1</text>
    <text x="80" y="616" fill="#e6edf3">module-name</text>
    <rect x="360" y="604" width="640" height="16" rx="8" fill="#21262d"/>       <!-- track -->
    <rect x="360" y="604" width="640" height="16" rx="8" fill="#2ea043"/>       <!-- fill: width=6.4*pct -->
    <text x="1012" y="617" fill="#7ee787" font-weight="700">100%</text>
  </g>

  <!-- aggregate -->
  <line x1="40" y1="894" x2="1160" y2="894" stroke="#30363d"/>
  <text x="80" y="920" fill="#e6edf3" font-size="14" font-weight="700">CORE (weighted)</text>
  <rect x="360" y="908" width="640" height="16" rx="8" fill="#21262d"/>
  <rect x="360" y="908" width="474" height="16" rx="8" fill="#8bc34a"/>          <!-- 6.4 * 74 ≈ 474 -->
  <text x="1012" y="921" fill="#d7f0b0" font-size="14" font-weight="700">~74%</text>

  <!-- AUXILIARY (below the aggregate line, excluded from core %) -->
  <text x="40" y="968" fill="#8b949e" font-size="13" font-weight="700">Auxiliary — not counted in core %</text>
  <!-- plug-in slot row: dashed violet track, "off-scale" instead of % -->
  <!-- observability row: normal band bar -->

  <!-- FOOTER LEGEND: five band swatches + the completeness definition sentence -->
</svg>
```

**Fill-width cheat sheet** (track = 640 px): 100→640, 95→608, 88→563, 78→499, 74→474,
40→256, 15→96, 0→~6 (nub).

---

That's the whole format. Any project: swap the module list, the % values, and the map header;
keep the structure, the honesty rules, and the written completeness definition.
