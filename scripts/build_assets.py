#!/usr/bin/env python3
"""Generate the animated SVG artwork used in the profile README.

All text is converted to outlines so the images render identically everywhere
(GitHub serves README images through a proxy that blocks external fonts).

    python3 -m venv .venv && .venv/bin/pip install fonttools
    .venv/bin/python scripts/build_assets.py
"""

from __future__ import annotations

import random
import textwrap
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONT_DIR = Path(__file__).resolve().parent / ".fonts"

FONTS = {
    "Anton.ttf": "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf",
    "JetBrainsMono.ttf": "https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}


def num(v: float) -> str:
    s = f"{v:.1f}"
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return "0" if s == "-0" else s


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #


def ensure_fonts() -> None:
    FONT_DIR.mkdir(exist_ok=True)
    for name, url in FONTS.items():
        target = FONT_DIR / name
        if not target.exists():
            print(f"downloading {name}")
            urllib.request.urlretrieve(url, target)


class Face:
    def __init__(self, file: str, weight: int | None = None):
        self.font = TTFont(FONT_DIR / file)
        location = {"wght": weight} if weight else None
        self.glyphs = self.font.getGlyphSet(location=location)
        self.cmap = self.font.getBestCmap()
        self.upm = self.font["head"].unitsPerEm

    def glyph(self, ch: str):
        if ord(ch) not in self.cmap:
            raise ValueError(f"glyph {ch!r} missing from {self.font.reader.file.name}")
        return self.glyphs[self.cmap[ord(ch)]]

    def advance(self, ch: str, size: float) -> float:
        return self.glyph(ch).width * size / self.upm

    def measure(self, text: str, size: float, tracking: float = 0) -> float:
        return sum(self.advance(c, size) + tracking for c in text) - tracking

    def path(self, text: str, size: float, x: float, y: float, tracking: float = 0) -> str:
        """Outline a whole string as one path, baseline at y."""
        pen = SVGPathPen(self.glyphs, ntos=num)
        s = size / self.upm
        for ch in text:
            g = self.glyph(ch)
            g.draw(TransformPen(pen, (s, 0, 0, -s, x, y)))
            x += g.width * s + tracking
        return pen.getCommands()


class GlyphAtlas:
    """Deduplicates glyph outlines into <defs> and places them with <use>."""

    def __init__(self, prefix: str):
        self.prefix = prefix
        self.defs: dict[tuple, str] = {}
        self.paths: list[str] = []

    def ref(self, face: Face, key: str, size: float, ch: str) -> str:
        k = (key, size, ch)
        if k not in self.defs:
            ident = f"{self.prefix}{len(self.defs)}"
            self.defs[k] = ident
            d = face.path(ch, size, 0, 0)
            if d:
                self.paths.append(f'<path id="{ident}" d="{d}"/>')
            else:  # whitespace
                self.paths.append(f'<path id="{ident}" d=""/>')
        return self.defs[k]

    def text(self, face: Face, key: str, text: str, size: float, x: float, y: float,
             fill: str | None = None, tracking: float = 0, attrs: str = "") -> str:
        parts = []
        for ch in text:
            if ch != " ":
                ident = self.ref(face, key, size, ch)
                parts.append(f'<use href="#{ident}" x="{num(x)}" y="{num(y)}"/>')
            x += face.advance(ch, size) + tracking
        fill_attr = f' fill="{fill}"' if fill else ""
        return f'<g{fill_attr}{attrs}>{"".join(parts)}</g>'

    def svg_defs(self) -> str:
        return "".join(self.paths)


# --------------------------------------------------------------------------- #
# Themes
# --------------------------------------------------------------------------- #


@dataclass
class Theme:
    name: str
    bg: str
    bg2: str
    panel: str
    panel_bar: str
    border: str
    text: str
    muted: str
    faint: str
    ember: str
    ember2: str
    chrome: list[tuple[float, str]]
    shine: str
    grid: str
    cyan: str
    green: str
    violet: str
    yellow: str


DARK = Theme(
    name="dark",
    bg="#09090b",
    bg2="#1a0b07",
    panel="#0e1015",
    panel_bar="#161920",
    border="#262b35",
    text="#e6edf3",
    muted="#8b949e",
    faint="#4b535e",
    ember="#ff4d1a",
    ember2="#ffb020",
    chrome=[(0, "#ffffff"), (0.38, "#d7dbe2"), (0.52, "#7d838f"), (0.53, "#3b3f47"),
            (0.62, "#9aa1ad"), (0.85, "#eef1f5"), (1, "#8a909b")],
    shine="#ffffff",
    grid="#ffffff",
    cyan="#56d4dd",
    green="#7ee787",
    violet="#d2a8ff",
    yellow="#f2cc60",
)

LIGHT = Theme(
    name="light",
    bg="#f6f7f9",
    bg2="#ffe9dc",
    panel="#ffffff",
    panel_bar="#f1f3f6",
    border="#d0d7de",
    text="#1f2328",
    muted="#59636e",
    faint="#a0a8b2",
    ember="#d9360b",
    ember2="#e08a00",
    chrome=[(0, "#4a515c"), (0.38, "#1f2328"), (0.52, "#0b0d10"), (0.53, "#5b636f"),
            (0.62, "#2c3139"), (0.85, "#11141a"), (1, "#3a4049")],
    shine="#ffffff",
    grid="#1f2328",
    cyan="#0a7f8c",
    green="#1a7f37",
    violet="#8250df",
    yellow="#9a6700",
)

LANG_COLORS = {
    "Rust": "#dea584",
    "C#": "#178600",
    "Python": "#3572A5",
    "TypeScript": "#3178c6",
    "Shell": "#89e051",
}

REDUCED_MOTION = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"


def stops(pairs: list[tuple[float, str]]) -> str:
    return "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in pairs)


# --------------------------------------------------------------------------- #
# Banner
# --------------------------------------------------------------------------- #


def banner(t: Theme, anton: Face, mono: Face, mono_bold: Face) -> str:
    W, H = 1280, 420
    rnd = random.Random(54)
    atlas = GlyphAtlas("b")
    out: list[str] = []

    # Name
    name, size, tracking = "DARIUSZ PARYS", 168, 6
    name_w = anton.measure(name, size, tracking)
    name_x, name_y = (W - name_w) / 2, 262
    name_d = anton.path(name, size, name_x, name_y, tracking)

    # Kicker line
    kicker = "HI THERE, I'M"
    k_size, k_track = 20, 8
    k_w = mono.measure(kicker, k_size, k_track)
    out.append(atlas.text(mono, "r", kicker, k_size, (W - k_w) / 2, 76, t.muted, k_track))

    # Subtitle with flanking rules
    sub = "CODER · DIE-HARD METALHEAD · CLUB SUPPORTER"
    s_size, s_track = 22, 4
    s_w = mono_bold.measure(sub, s_size, s_track)
    s_x = (W - s_w) / 2
    out_sub = atlas.text(mono_bold, "b", sub, s_size, s_x, 318, t.ember, s_track)

    # Equalizer bars
    bars = []
    bar_w, gap = 12, 6
    count = (W + gap) // (bar_w + gap)
    offset = (W - (count * (bar_w + gap) - gap)) / 2
    for i in range(count):
        x = offset + i * (bar_w + gap)
        # taller in the middle, like a spectrum hump
        centre = 1 - abs(i - count / 2) / (count / 2)
        h = 18 + 60 * (0.35 + 0.65 * centre) * rnd.uniform(0.55, 1.0)
        dur = rnd.uniform(0.7, 1.6)
        delay = -rnd.uniform(0, 2)
        bars.append(
            f'<rect class="bar" x="{num(x)}" y="{num(H - h)}" width="{bar_w}" height="{num(h)}" rx="2" '
            f'style="animation-duration:{dur:.2f}s;animation-delay:{delay:.2f}s"/>'
        )

    # Embers
    embers = []
    for _ in range(34):
        x = rnd.uniform(40, W - 40)
        r = rnd.uniform(0.8, 2.6)
        dur = rnd.uniform(4.5, 10)
        delay = -rnd.uniform(0, 10)
        drift = rnd.uniform(-40, 40)
        rise = rnd.uniform(180, 340)
        color = t.ember2 if rnd.random() < 0.4 else t.ember
        embers.append(
            f'<circle class="ember" cx="{num(x)}" cy="{H - 20}" r="{num(r)}" fill="{color}" '
            f'style="--dx:{num(drift)}px;--dy:-{num(rise)}px;animation-duration:{dur:.2f}s;animation-delay:{delay:.2f}s"/>'
        )

    rule_y = 311
    rule_gap = 26
    rule_len = 120

    style = f"""
    .bar{{fill:url(#barGrad);transform-box:fill-box;transform-origin:50% 100%;animation:eq ease-in-out infinite alternate}}
    @keyframes eq{{0%{{transform:scaleY(.25)}}50%{{transform:scaleY(1)}}100%{{transform:scaleY(.45)}}}}
    .ember{{opacity:0;animation:rise linear infinite}}
    @keyframes rise{{0%{{opacity:0;transform:translate(0,0)}}12%{{opacity:.95}}70%{{opacity:.5}}100%{{opacity:0;transform:translate(var(--dx),var(--dy))}}}}
    .shine{{animation:shine 7s ease-in-out infinite}}
    @keyframes shine{{0%{{transform:translateX(-700px)}}55%,100%{{transform:translateX(1500px)}}}}
    .glow{{animation:pulse 4s ease-in-out infinite alternate}}
    @keyframes pulse{{from{{opacity:.55}}to{{opacity:1}}}}
    .rule{{transform-box:fill-box;animation:draw 1.2s cubic-bezier(.2,.8,.2,1) both .3s}}
    .rule.l{{transform-origin:100% 50%}}.rule.r{{transform-origin:0 50%}}
    @keyframes draw{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
    .rise-in{{animation:risein 1s cubic-bezier(.2,.8,.2,1) both}}
    @keyframes risein{{from{{opacity:0;transform:translateY(14px)}}to{{opacity:1;transform:none}}}}
    {REDUCED_MOTION}
    """

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="title desc">
<title id="title">Dariusz Parys</title>
<desc id="desc">Hi there, I'm Dariusz Parys. Coder, die-hard metalhead and club supporter.</desc>
<style>{style}</style>
<defs>
{atlas.svg_defs()}
<clipPath id="frame"><rect width="{W}" height="{H}" rx="18"/></clipPath>
<clipPath id="nameClip"><path d="{name_d}"/></clipPath>
<radialGradient id="glow" cx="50%" cy="100%" r="75%">
  <stop offset="0" stop-color="{t.ember}" stop-opacity="{'.42' if t.name == 'dark' else '.30'}"/>
  <stop offset=".45" stop-color="{t.bg2}" stop-opacity="{'.55' if t.name == 'dark' else '.6'}"/>
  <stop offset="1" stop-color="{t.bg}" stop-opacity="0"/>
</radialGradient>
<radialGradient id="vignette" cx="50%" cy="45%" r="70%">
  <stop offset=".6" stop-color="{t.bg}" stop-opacity="0"/>
  <stop offset="1" stop-color="{t.bg}" stop-opacity=".9"/>
</radialGradient>
<linearGradient id="chrome" x1="0" y1="{name_y - 125}" x2="0" y2="{name_y}" gradientUnits="userSpaceOnUse">{stops(t.chrome)}</linearGradient>
<linearGradient id="shineGrad" x1="0" x2="1" y1="0" y2="0">
  <stop offset="0" stop-color="{t.shine}" stop-opacity="0"/>
  <stop offset=".5" stop-color="{t.shine}" stop-opacity="{'.85' if t.name == 'dark' else '.6'}"/>
  <stop offset="1" stop-color="{t.shine}" stop-opacity="0"/>
</linearGradient>
<linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{t.ember2}" stop-opacity=".75"/>
  <stop offset="1" stop-color="{t.ember}" stop-opacity=".08"/>
</linearGradient>
<linearGradient id="ruleL" x1="0" x2="1"><stop offset="0" stop-color="{t.ember}" stop-opacity="0"/><stop offset="1" stop-color="{t.ember}"/></linearGradient>
<linearGradient id="ruleR" x1="0" x2="1"><stop offset="0" stop-color="{t.ember}"/><stop offset="1" stop-color="{t.ember}" stop-opacity="0"/></linearGradient>
<pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="{t.grid}" stroke-opacity=".045"/></pattern>
<filter id="soft" x="-10%" y="-30%" width="120%" height="160%"><feGaussianBlur stdDeviation="14"/></filter>
</defs>
<g clip-path="url(#frame)">
  <rect width="{W}" height="{H}" fill="{t.bg}"/>
  <rect width="{W}" height="{H}" fill="url(#grid)"/>
  <rect class="glow" width="{W}" height="{H}" fill="url(#glow)"/>
  <g>{''.join(bars)}</g>
  <g>{''.join(embers)}</g>
  <rect width="{W}" height="{H}" fill="url(#vignette)"/>
  <g class="rise-in">{out[0]}</g>
  <path d="{name_d}" fill="{t.ember}" opacity="{'.35' if t.name == 'dark' else '.18'}" filter="url(#soft)"/>
  <g class="rise-in" style="animation-delay:.1s">
    <path d="{name_d}" fill="url(#chrome)" stroke="{t.faint if t.name == 'dark' else '#000'}" stroke-opacity=".5" stroke-width="1"/>
    <g clip-path="url(#nameClip)"><rect class="shine" x="0" y="{name_y - 150}" width="220" height="180" fill="url(#shineGrad)" transform="skewX(-20)"/></g>
  </g>
  <rect class="rule l" x="{num(s_x - rule_gap - rule_len)}" y="{rule_y}" width="{rule_len}" height="2" fill="url(#ruleL)"/>
  <rect class="rule r" x="{num(s_x + s_w + rule_gap)}" y="{rule_y}" width="{rule_len}" height="2" fill="url(#ruleR)"/>
  <g class="rise-in" style="animation-delay:.25s">{out_sub}</g>
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="18" fill="none" stroke="{t.border}"/>
</svg>
"""


# --------------------------------------------------------------------------- #
# Terminal
# --------------------------------------------------------------------------- #


def terminal(t: Theme, mono: Face, mono_bold: Face) -> str:
    W = 1280
    pad_x, bar_h, pad_top = 44, 46, 40
    size, lh = 24, 40
    adv = mono.advance("M", size)
    atlas = GlyphAtlas("t")

    sessions: list[tuple[str, list[list[tuple[str, str]]]]] = [
        ("cat now.md", [[("AI agents & developer tooling", t.violet), ("  ·  ", t.faint),
                         ("platform engineering on Azure", t.cyan)]]),
        ("ls ~/stack", [[("rust", LANG_COLORS["Rust"] if t.name == "dark" else "#a0522d"), ("   csharp", t.green),
                         ("   typescript", "#58a6ff" if t.name == "dark" else "#0969da"), ("   python", t.yellow),
                         ("   go", t.cyan), ("   terraform", t.violet), ("   bicep", t.muted)]]),
        ("ls ~/contributions", [[("eclipse-chariott/chariott", t.text), ("   microsoft/rust-for-dotnet-devs", t.text)]]),
    ]

    rows = sum(1 + len(o) for _, o in sessions) + 1
    H = bar_h + pad_top * 2 + (rows - 1) * lh + 8

    body: list[str] = []
    styles: list[str] = []
    y = bar_h + pad_top + size
    clock = 0.8
    char_time = 0.06

    prompt_w = mono_bold.measure("❯ ", size)
    for i, (cmd, outputs) in enumerate(sessions):
        # prompt
        body.append(f'<g class="show" style="animation-delay:{clock:.2f}s">'
                    + atlas.text(mono_bold, "b", "❯", size, pad_x, y, t.ember)
                    + atlas.text(mono, "r", "~", size, pad_x + prompt_w, y, t.cyan)
                    + "</g>")
        cx = pad_x + prompt_w + adv * 2
        body.append(atlas.text(mono_bold, "b", cmd, size, cx, y, t.text))
        n = len(cmd)
        type_start = clock + 0.35
        type_dur = n * char_time
        styles.append(f"@keyframes ty{i}{{from{{transform:translateX(0)}}to{{transform:translateX({num(n * adv)}px)}}}}")
        cursor_off = type_start + type_dur + 0.3
        body.append(
            f'<g style="animation:ty{i} {type_dur:.2f}s steps({n}) {type_start:.2f}s both" class="typer">'
            f'<rect x="{num(cx)}" y="{num(y - size)}" width="{W}" height="{lh}" fill="{t.panel}"/>'
            f'<g class="show" style="animation-delay:{clock:.2f}s">'
            f'<rect class="hide" x="{num(cx)}" y="{num(y - size + 3)}" width="{num(adv)}" height="{size + 5}" fill="{t.ember}" '
            f'style="animation-delay:{cursor_off:.2f}s"/>'
            f"</g></g>"
        )
        clock = cursor_off
        for line in outputs:
            y += lh
            x = pad_x + adv * 2
            segs = []
            for text, color in line:
                segs.append(atlas.text(mono, "r", text, size, x, y, color))
                x += mono.measure(text, size)
            body.append(f'<g class="show" style="animation-delay:{clock:.2f}s">{"".join(segs)}</g>')
        clock += 0.55
        y += lh

    # final prompt with blinking cursor
    body.append(f'<g class="show" style="animation-delay:{clock:.2f}s">'
                + atlas.text(mono_bold, "b", "❯", size, pad_x, y, t.ember)
                + atlas.text(mono, "r", "~", size, pad_x + prompt_w, y, t.cyan)
                + f'<rect class="blink" x="{num(pad_x + prompt_w + adv * 2)}" y="{num(y - size + 3)}" width="{num(adv)}" height="{size + 5}" fill="{t.ember}"/>'
                + "</g>")

    title = "dariusz@stuttgart: ~ — zsh"
    title_size = 14
    title_w = mono.measure(title, title_size)
    title_svg = atlas.text(mono, "r", title, title_size, (W - title_w) / 2, bar_h / 2 + 5, t.muted)

    style = f"""
    .show{{animation:show .01s linear both}}
    @keyframes show{{from{{opacity:0}}to{{opacity:1}}}}
    .hide{{animation:hide .01s linear both}}
    @keyframes hide{{from{{opacity:1}}to{{opacity:0}}}}
    .blink{{animation:blink 1.1s steps(1) infinite}}
    @keyframes blink{{50%{{opacity:0}}}}
    {''.join(styles)}
    @media (prefers-reduced-motion: reduce){{*{{animation:none!important}}.typer{{display:none}}}}
    """

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="title desc">
<title id="title">Terminal</title>
<desc id="desc">Terminal session. Now: AI agents and developer tooling, platform engineering on Azure. Stack: Rust, C#, TypeScript, Python, Go, Terraform, Bicep. Contributions: eclipse-chariott/chariott, microsoft/rust-for-dotnet-devs.</desc>
<style>{style}</style>
<defs>
{atlas.svg_defs()}
<clipPath id="win"><rect width="{W}" height="{H}" rx="14"/></clipPath>
</defs>
<g clip-path="url(#win)">
  <rect width="{W}" height="{H}" fill="{t.panel}"/>
  <rect width="{W}" height="{bar_h}" fill="{t.panel_bar}"/>
  <rect y="{bar_h - 1}" width="{W}" height="1" fill="{t.border}"/>
  <circle cx="26" cy="{bar_h / 2}" r="7" fill="#ff5f57"/>
  <circle cx="50" cy="{bar_h / 2}" r="7" fill="#febc2e"/>
  <circle cx="74" cy="{bar_h / 2}" r="7" fill="#28c840"/>
  {title_svg}
  {''.join(body)}
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="{t.border}"/>
</svg>
"""


# --------------------------------------------------------------------------- #
# Project cards
# --------------------------------------------------------------------------- #


@dataclass
class Project:
    slug: str
    repo: str
    lang: str
    blurb: str
    private: bool = False


# Pinned repos already appear below the README, so only list work that isn't pinned.
PROJECTS = [
    Project("taube", "dariuszparys/taube", "C#",
            "Self-hosted email control plane: .NET API, CLI and delivery workers, with SDKs in seven languages.",
            private=True),
    Project("claude-code-toolkit", "dariuszparys/claude-code-toolkit", "Shell",
            "Claude Code plugin marketplace: commands, skills and hooks for work items, ADRs and Ralph loops."),
    Project("azdo-linter", "dariuszparys/azdo-linter", "Rust",
            "Validates Azure DevOps pipelines against the variable groups that actually exist."),
    Project("gpsify", "dariuszparys/gpsify", "Python",
            "Geolocates untagged photos from pixels; writes GPS only after a human accepts the pin."),
]


def card(p: Project, t: Theme, mono: Face, mono_bold: Face) -> str:
    W, H = 640, 214
    atlas = GlyphAtlas("c")
    color = LANG_COLORS[p.lang]
    parts: list[str] = []

    owner = p.repo.split("/")[0] + " /"
    parts.append(atlas.text(mono, "r", owner, 17, 36, 52, t.muted))
    parts.append(atlas.text(mono_bold, "b", p.slug, 30, 36, 92, t.text))
    if p.private:
        # mirrors GitHub's "Private" label; private repos get no link arrow
        label_x = 36 + mono_bold.measure(p.slug, 30) + 16
        label_w = mono.measure("Private", 14) + 22
        parts.append(f'<rect x="{num(label_x)}" y="69" width="{num(label_w)}" height="28" rx="14" fill="none" stroke="{t.border}" stroke-width="1.5"/>')
        parts.append(atlas.text(mono, "r", "Private", 14, label_x + 11, 88, t.muted))

    lines = textwrap.wrap(p.blurb, 50)
    if len(lines) > 2:
        raise ValueError(f"blurb for {p.slug} needs more than two lines: {lines}")
    for i, line in enumerate(lines):
        parts.append(atlas.text(mono, "r", line, 18, 36, 132 + i * 26, t.muted))

    if not p.private:
        parts.append(atlas.text(mono_bold, "b", "↗", 24, W - 54, 54, t.faint))

    # language
    lang_y = H - 22
    parts.append(f'<circle cx="43" cy="{lang_y - 6}" r="7" fill="{color}"/>')
    parts.append(atlas.text(mono, "r", p.lang, 16, 58, lang_y, t.muted))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{p.repo}: {p.blurb}">
<defs>
{atlas.svg_defs()}
<linearGradient id="edge" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{color}"/><stop offset=".6" stop-color="{t.ember}" stop-opacity="0"/></linearGradient>
<clipPath id="c"><rect width="{W}" height="{H}" rx="14"/></clipPath>
</defs>
<g clip-path="url(#c)">
  <rect width="{W}" height="{H}" fill="{t.panel}"/>
  <rect width="{W}" height="3" fill="url(#edge)"/>
  {''.join(parts)}
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="{t.border}"/>
</svg>
"""


# --------------------------------------------------------------------------- #
# Footer
# --------------------------------------------------------------------------- #


def footer(t: Theme, mono: Face) -> str:
    W, H = 1280, 90
    rnd = random.Random(666)
    atlas = GlyphAtlas("f")
    bars = []
    bar_w, gap, count = 6, 5, 41
    start = (W - (count * (bar_w + gap) - gap)) / 2
    for i in range(count):
        centre = 1 - abs(i - count // 2) / (count // 2)
        h = 6 + 34 * centre ** 1.4 * rnd.uniform(0.6, 1)
        bars.append(
            f'<rect class="bar" x="{num(start + i * (bar_w + gap))}" y="{num(46 - h)}" width="{bar_w}" height="{num(h)}" rx="2" '
            f'style="animation-duration:{rnd.uniform(.6, 1.4):.2f}s;animation-delay:-{rnd.uniform(0, 2):.2f}s"/>'
        )
    text = "MADE LOUD IN STUTTGART"
    tw = mono.measure(text, 13, 4)
    label = atlas.text(mono, "r", text, 13, (W - tw) / 2, 78, t.faint, 4)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Made loud in Stuttgart">
<style>
.bar{{fill:url(#g);transform-box:fill-box;transform-origin:50% 100%;animation:eq ease-in-out infinite alternate}}
@keyframes eq{{0%{{transform:scaleY(.2)}}60%{{transform:scaleY(1)}}100%{{transform:scaleY(.5)}}}}
{REDUCED_MOTION}
</style>
<defs>{atlas.svg_defs()}
<linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t.ember2}"/><stop offset="1" stop-color="{t.ember}" stop-opacity=".3"/></linearGradient>
</defs>
{''.join(bars)}
{label}
</svg>
"""


# --------------------------------------------------------------------------- #


def main() -> None:
    ensure_fonts()
    anton = Face("Anton.ttf")
    mono = Face("JetBrainsMono.ttf", 400)
    mono_bold = Face("JetBrainsMono.ttf", 700)

    (ASSETS / "projects").mkdir(parents=True, exist_ok=True)
    for t in (DARK, LIGHT):
        (ASSETS / f"banner-{t.name}.svg").write_text(banner(t, anton, mono, mono_bold))
        (ASSETS / f"terminal-{t.name}.svg").write_text(terminal(t, mono, mono_bold))
        (ASSETS / f"footer-{t.name}.svg").write_text(footer(t, mono))
        for p in PROJECTS:
            (ASSETS / "projects" / f"{p.slug}-{t.name}.svg").write_text(card(p, t, mono, mono_bold))
    print(f"wrote assets to {ASSETS.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
