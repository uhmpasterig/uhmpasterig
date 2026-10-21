#!/usr/bin/env python3
"""Generates assets/*.svg for the profile README.

    pip install fonttools brotli pillow && python3 build.py

Fonts (JetBrains Mono, OFL) and the avatar are downloaded into .cache/ on first run.
"""
import base64
import html
import io
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).parent
CACHE, OUT = ROOT / ".cache", ROOT / "assets"
FONT_URL = "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-{}.ttf"
AVATAR_URL = "https://avatars.githubusercontent.com/u/90611943?v=4&s=460"

BG, PANEL = "#060607", "#0b0b0d"
RED, TXT, MUT, DIM = "#ff1a35", "#e9e7e4", "#7d7d84", "#45454c"
CHARS = "".join(map(chr, range(32, 127))) + "·→←↗─│●▌█°"


def fetch(name, url):
    p = CACHE / name
    if not p.exists():
        CACHE.mkdir(exist_ok=True)
        urllib.request.urlretrieve(url, p)
    return p


def font(weight):
    return TTFont(fetch(f"JetBrainsMono-{weight}.ttf", FONT_URL.format(weight)), recalcTimestamp=False)  # stable output, no diff noise


def woff2(weight):
    opts = subset.Options()
    opts.flavor, opts.hinting, opts.layout_features = "woff2", False, []  # no GSUB: keeps "//" and "->" from turning into ligatures
    f = font(weight)
    s = subset.Subsetter(opts)
    s.populate(text=CHARS)
    s.subset(f)
    buf = io.BytesIO()
    f.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


FONT_CSS = "".join(
    f"@font-face{{font-family:'JBM';font-weight:{w};src:url(data:font/woff2;base64,{woff2(n)}) format('woff2')}}"
    for w, n in ((400, "Regular"), (700, "Bold"))
)
BASE_CSS = (
    ".m{font-family:'JBM',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre}"
    ".bl{animation:bl 1.05s steps(1) infinite}@keyframes bl{50%{opacity:0}}"
    ".fi{opacity:0;animation:fi .35s ease-out forwards}@keyframes fi{to{opacity:1}}"
    ".br{animation:br 6s ease-in-out infinite}@keyframes br{0%,100%{opacity:.5}50%{opacity:1}}"
    ".sw{animation:sw 8s linear infinite}@keyframes sw{from{transform:translateY(0)}to{transform:translateY(600px)}}"
)
# film grain + CRT scanlines, shared by the big panels
FX_DEFS = (
    '<filter id="nz" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter>'
    '<pattern id="scl" width="4" height="3" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#000" opacity=".3"/></pattern>'
    '<linearGradient id="swg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".85" stop-color="#fff" stop-opacity=".04"/><stop offset="1" stop-color="#fff" stop-opacity=".1"/></linearGradient>'
)


def fx(w, h, sweep=True):
    out = f'<rect width="{w}" height="{h}" filter="url(#nz)" opacity=".06"/><rect width="{w}" height="{h}" fill="url(#scl)"/>'
    return out + (f'<rect class="sw" y="-160" width="{w}" height="160" fill="url(#swg)"/>' if sweep else "")


def esc(s):
    return html.escape(s, quote=False)


def weight(w):
    return f' font-weight="{w}"'


def t(x, y, s, size=12, fill=TXT, w=400, anchor=None, ls=None, cls="", style="", op=None):
    """Text at (x, y). `s` is a string or a list of (text, fill[, weight]) runs."""
    if isinstance(s, str):
        s = [(s, fill)]
    runs = "".join(f'<tspan fill="{r[1]}"{weight(r[2]) if len(r) > 2 else ""}>{esc(r[0])}</tspan>' for r in s)
    attrs = weight(w) if w != 400 else ""
    attrs += f' text-anchor="{anchor}"' if anchor else ""
    attrs += f' letter-spacing="{ls}"' if ls else ""
    attrs += f' style="{style}"' if style else ""
    attrs += f' fill-opacity="{op}"' if op is not None else ""
    return f'<text x="{x:.6g}" y="{y:.6g}" class="m {cls}" font-size="{size}"{attrs}>{runs}</text>'


def typed(uid, x, y, runs, size, begin, step=0.07, hide_at=None):
    """Types `runs` out char by char starting at `begin` seconds, with a red block cursor (gone at `hide_at`)."""
    n, cw = sum(len(r[0]) for r in runs), size * 0.6
    hide = f'<set attributeName="visibility" to="hidden" begin="{hide_at:.2f}s" fill="freeze"/>' if hide_at else ""
    keys = ";".join(f"{i / (n + 1):.4f}" for i in range(n + 1))
    anim = lambda attr, off: (
        f'<animate attributeName="{attr}" values="{";".join(f"{off + i * cw:.2f}" for i in range(n + 1))}" '
        f'keyTimes="{keys}" dur="{(n + 1) * step:.2f}s" begin="{begin}s" calcMode="discrete" fill="freeze"/>'
    )
    return (
        f'<clipPath id="{uid}"><rect x="{x}" y="{y - size}" height="{size * 1.5}" width="0">{anim("width", 0)}</rect></clipPath>'
        f'<g clip-path="url(#{uid})">{t(x, y, runs, size)}</g>'
        f'<rect x="{x}" y="{y - size * 0.8:.1f}" width="{cw:.1f}" height="{size:.1f}" fill="{RED}" class="bl">{anim("x", x)}{hide}</rect>'
    )


def write(name, w, h, body, css="", defs="", frame=True):
    clip = f'<clipPath id="fr"><rect width="{w}" height="{h}" rx="14"/></clipPath>' if frame else ""
    clip_ref = ' clip-path="url(#fr)"' if frame else ""
    border = f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="13.5" stroke="#fff" stroke-opacity=".08"/>' if frame else ""
    doc = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none">'
        f"<style>{FONT_CSS}{BASE_CSS}{css}</style><defs>{clip}{defs}</defs>"
        f"<g{clip_ref}>{body}</g>{border}</svg>"
    )
    ET.fromstring(doc)  # fail loudly on broken markup instead of shipping a blank image
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.svg").write_text(doc, encoding="utf-8")
    print(f"assets/{name}.svg  {len(doc) // 1024}K")


# ---------------------------------------------------------------- whoami (neofetch)

RAMP = " .:-=+*#%@"


def ascii_avatar(cols=40, rows=20):
    im = Image.open(fetch("avatar.png", AVATAR_URL)).convert("L").filter(ImageFilter.GaussianBlur(4))
    # inverted: the dark hood becomes dense glyphs; soft ellipse fades out the busy corners
    im = ImageOps.invert(ImageOps.autocontrast(im, cutoff=2))
    fade = Image.new("L", im.size, 0)
    ImageDraw.Draw(fade).ellipse((40, 60, 420, 640), fill=255)
    im = ImageChops.multiply(im, fade.filter(ImageFilter.GaussianBlur(40))).resize((cols, rows), Image.LANCZOS)
    return ["".join(RAMP[im.getpixel((x, y)) * len(RAMP) // 256] for x in range(cols)) for y in range(rows)]


def shade(ch):
    i = RAMP.index(ch)
    return RED if i >= 7 else "#9b9996" if i >= 4 else DIM


def runs_by_color(line):
    out = []
    for ch in line:
        c = shade(ch) if ch != " " else (out[-1][1] if out else DIM)
        if out and out[-1][1] == c:
            out[-1] = (out[-1][0] + ch, c)
        else:
            out.append((ch, c))
    return out


INFO = [
    ("OS", "macOS · Arch · Debian"),
    ("Host", "github.com/uhmpasterig"),
    ("Role", "full-stack developer"),
    ("Uptime", "since 2021"),
    ("Shell", "zsh"),
    ("Editor", "VS Code"),
    ("Langs", "TypeScript · C# · Rust · Lua"),
    ("Stack", "Next.js · NestJS · Docker · Redis"),
    ("Status", "probably refactoring something"),
]
PROMPT = [("uhmpasterig", RED, 700), ("@fsociety", TXT), (" ~ $ ", MUT)]


def whoami():
    W, H = 1000, 420
    out_at = 0.5 + 9 * 0.07 + 0.25
    art = "".join(
        t(28, 118 + i * 13, runs_by_color(row), 10.5, cls="fi", style=f"animation-delay:{out_at + i * 0.025:.3f}s")
        for i, row in enumerate(ascii_avatar())
    )
    lines = [[("uhmpasterig", RED, 700), ("@", MUT), ("fsociety", TXT, 700)], [("─" * 22, DIM)]]
    lines += [[(f"{k:<8}", RED, 700), (v, TXT)] for k, v in INFO]
    info = "".join(
        t(330, 118 + i * 21, l, 13, cls="fi", style=f"animation-delay:{out_at + 0.1 + i * 0.05:.2f}s") for i, l in enumerate(lines)
    )
    blocks_at = out_at + 0.1 + len(lines) * 0.05
    blocks = "".join(
        f'<rect class="fi" style="animation-delay:{blocks_at:.2f}s" x="{330 + i * 28}" y="{118 + len(lines) * 21 - 6}" width="24" height="14" fill="{c}"/>'
        for i, c in enumerate(["#1a1a1d", "#3b0a12", "#7a0f1c", "#c4122a", RED, "#5a5a60", "#9b9996", TXT])
    )
    prompt_at = blocks_at + 0.4
    body = (
        f'<rect width="{W}" height="{H}" fill="{PANEL}"/>'
        f'<rect width="{W}" height="40" fill="#fff" fill-opacity=".02"/><path d="M0 40.5H{W}" stroke="#fff" stroke-opacity=".07"/>'
        + "".join(f'<circle cx="{24 + i * 18}" cy="20" r="5" fill="{c}"/>' for i, c in enumerate([RED, "#2a2a2f", "#2a2a2f"]))
        + t(500, 24, "uhmpasterig@fsociety: ~", 11, MUT, anchor="middle")
        + t(976, 24, "zsh", 11, DIM, anchor="end")
        + t(28, 80, PROMPT, 13)
        + typed("tw", 28 + 25 * 7.8, 80, [("neofetch", TXT)], 13, 0.5, hide_at=prompt_at)
        + art + info + blocks
        + f'<g class="fi" style="animation-delay:{prompt_at:.2f}s">{t(28, 396, PROMPT, 13)}'
        f'<rect x="{28 + 25 * 7.8}" y="385.6" width="7.8" height="13" fill="{RED}" class="bl"/></g>'
        + fx(W, H, sweep=False)
    )
    write("whoami", W, H, body, defs=FX_DEFS)


# --------------------------------------------- prompt dividers (one shell session)

DIVIDERS = [
    ("projects", "ls ~/projects"),
    ("stack", "cat ~/.stack"),
    ("public", "ls ~/public"),
]


def dividers():
    for name, cmd in DIVIDERS:
        cur = 28 + (25 + len(cmd)) * 7.8  # prompt "uhmpasterig@fsociety ~ $ " is 25 chars at 13px
        body = (
            t(28, 30, PROMPT + [(cmd, TXT)], 13)
            + f'<rect x="{cur:.0f}" y="19" width="7.8" height="13" fill="{RED}" class="bl"/>'
            + f'<path d="M{cur + 24:.0f} 26.5H980" stroke="#fff" stroke-opacity=".08"/>'
        )
        write(f"divider-{name}", 1000, 46, body, frame=False)


# ---------------------------------------------- project cards (as terminal windows)

LANG_COLOR = {"C++": "#f34b7d", "TypeScript": "#3178c6", "Lua": "#8a95ff"}
CX = 250  # card centre; vizes fill the window body x24..476, y48..150


def vis_netlogger():
    ev = [
        ("→", "playerConnecting", "212B"), ("←", "esx:getSharedObject", "96B"), ("→", "chat:addMessage", "148B"),
        ("←", "txAdmin:heartbeat", "64B"), ("→", "baseevents:onPlayerDied", "88B"), ("←", "vMenu:sync", "1.2K"),
        ("→", "hud:updateStatus", "40B"), ("←", "inventory:refresh", "3.4K"),
    ]
    rows = "".join(
        t(32, 60 + i * 14, [(a, RED if a == "→" else MUT), (" " + e, "#b9b7b4")], 9.5) + t(468, 60 + i * 14, b, 9.5, MUT, anchor="end")
        for i, (a, e, b) in enumerate(ev * 2)
    )
    return (
        '<linearGradient id="fd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".25" stop-color="#fff"/><stop offset=".75" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        '<mask id="fm"><rect x="24" y="48" width="452" height="100" fill="url(#fd)"/></mask>'
        f'<g mask="url(#fm)"><g style="animation:up 9s linear infinite;--h:-{len(ev) * 14}px">{rows}</g></g>'
    )


def vis_orbit():
    cy = 98
    out = f'<circle cx="{CX}" cy="{cy}" r="20" fill="{RED}" opacity=".12" class="br"/><circle cx="{CX}" cy="{cy}" r="7" fill="{RED}"/>'
    out += "".join(f'<circle cx="{CX}" cy="{cy}" r="{r}" stroke="#fff" stroke-opacity=".14" stroke-dasharray="2 4"/>' for r in (32, 54))
    for r, pr, c, dur, *start in [(32, 4.5, TXT, 4), (54, 3.5, RED, 7), (54, 3, MUT, 7, 180)]:
        a = start[0] if start else 0
        out += (
            f'<g><animateTransform attributeName="transform" type="rotate" from="{a} {CX} {cy}" to="{a + 360} {CX} {cy}" dur="{dur}s" repeatCount="indefinite"/>'
            f'<circle cx="{CX + r}" cy="{cy}" r="{pr}" fill="{c}"/></g>'
        )
    return out


def vis_redis():
    cy = 98
    nodes = [(150, 66), (350, 66), (150, 130), (350, 130)]
    out = "".join(f'<path d="M{CX} {cy}L{x} {y}" stroke="#fff" stroke-opacity=".14" stroke-dasharray="2 3"/>' for x, y in nodes)
    out += "".join(
        f'<circle r="2.5" fill="{RED}"><animate attributeName="cx" values="{CX};{x}" dur="1.8s" begin="{i * 0.45}s" repeatCount="indefinite"/>'
        f'<animate attributeName="cy" values="{cy};{y}" dur="1.8s" begin="{i * 0.45}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="0;1;1;0" dur="1.8s" begin="{i * 0.45}s" repeatCount="indefinite"/></circle>'
        for i, (x, y) in enumerate(nodes)
    )
    out += "".join(f'<rect x="{x - 8}" y="{y - 8}" width="16" height="16" rx="3" fill="{PANEL}" stroke="#fff" stroke-opacity=".4"/>' for x, y in nodes)
    out += f'<circle cx="{CX}" cy="{cy}" r="19" fill="{RED}" opacity=".12" class="br"/><circle cx="{CX}" cy="{cy}" r="11" fill="{PANEL}" stroke="{RED}" stroke-width="1.5"/>'
    return out + t(CX, cy + 3.5, "R", 11, RED, 700, "middle")


def vis_unluac():
    hexb = " ".join("1B 4C 75 61 54 00 19 93".split())
    cur = CX + len("local f = function()") / 2 * 6.6
    return (
        t(CX, 64, "LUAC 5.4 HEADER", 9, MUT, anchor="middle", ls=2)
        + t(CX, 86, hexb, 11, "#b9b7b4", anchor="middle")
        + t(CX, 110, "↓ decompile", 10, RED, anchor="middle")
        + t(CX, 134, [("local ", RED), ("f = ", TXT), ("function", RED), ("()", TXT)], 11, anchor="middle")
        + f'<rect x="{cur:.0f}" y="124" width="6.6" height="12" fill="{RED}" class="bl"/>'
    )


def vis_escrow():
    k = 'keyTimes="0;.35;.45;.85;.95;1" dur="4s" repeatCount="indefinite"'
    show = lambda v: f'<animate attributeName="opacity" values="{v}" {k} calcMode="discrete"/>'
    locked, open_ = show("1;1;0;0;1;1"), show("0;0;1;1;0;0")
    return (
        t(CX, 60, "resource.lua  ·  asset escrow", 9, MUT, anchor="middle", ls=1)
        + f'<g><animateTransform attributeName="transform" type="translate" values="0 0;0 0;0 -8;0 -8;0 0;0 0" {k}/>'
        f'<path d="M{CX - 11} 96V84a11 11 0 0 1 22 0V96" stroke="{TXT}" stroke-width="3"/></g>'
        + f'<rect x="{CX - 17}" y="92" width="34" height="28" rx="4" fill="{PANEL}" stroke="{RED}" stroke-width="1.5"/>'
        + f'<circle cx="{CX}" cy="104" r="3.5" fill="{RED}"/><path d="M{CX} 106v6" stroke="{RED}" stroke-width="2"/>'
        + f'<g>{locked}{t(CX, 144, "ENCRYPTED", 9, MUT, anchor="middle", ls=3)}</g>'
        + f'<g opacity="0">{open_}{t(CX, 144, "BYPASSED", 9, RED, 700, "middle", 3)}</g>'
    )


def vis_botting():
    cols, cell = 16, 13
    x0 = CX - cols * cell / 2
    cells = "".join(
        f'<rect x="{x0 + i % cols * cell:.0f}" y="{74 + i // cols * cell}" width="9" height="9" rx="2" fill="{RED}" fill-opacity=".08">'
        f'<animate attributeName="fill-opacity" values=".08;.08;.9;.9;.08" keyTimes="0;{0.05 + i * 0.012:.3f};{0.07 + i * 0.012:.3f};.92;1" dur="6s" repeatCount="indefinite"/></rect>'
        for i in range(cols * 4)
    )
    return t(CX, 62, "PLAYER SLOTS  ·  BOTS JOINING", 9, MUT, anchor="middle", ls=2) + cells


def redact(line):
    return [(m, "#2a2a30" if m[0] == "█" else "#8a8a90") for m in re.findall(r"█+|[^█]+", line)]


# lang=None marks a project that is no longer public; dead=status word shown in red
CARDS = [
    ("netlogger", "network-logger.cpp", "LIVE CAPTURE",
     "Logs every in- and outbound event of every resource.", "fivem · citizen-server", "C++", vis_netlogger),
    ("unluac", "unluac-54.lua", "REVERSING",
     "Turns dumped .luac files back into readable Lua.", "lua 5.4 · decompiler", "Lua", vis_unluac),
    ("escrow", "escrow-exploit.lua~", "SEIZED",
     "Broke FiveM's asset escrow. Had to pull it. ██████.", "fivem · cfx.re", None, vis_escrow),
    ("botting", "player-botting.lua~", "OFFLINE",
     "Botted players onto servers to fill their slots. ████.", "fivem · bots", None, vis_botting),
    ("orbit", "react-orbit.tsx", "UI COMPONENT",
     "Puts any element on an animated orbit. Published on npm.", "react · npm", "TypeScript", vis_orbit),
    ("redis", "nest-redis-config.ts", "MICROSERVICES",
     "Shared NestJS config over Redis. Published on npm.", "nestjs · redis", "TypeScript", vis_redis),
]


def cards():
    W, H = 500, 250
    for key, file, kicker, desc, meta, lang, vis in CARDS:
        dead = lang is None
        if dead:
            status = f'<circle cx="{476 - len(kicker) * 6.2 - 11:.0f}" cy="226" r="4" fill="{RED}" class="bl"/>' + t(476, 230, kicker, 10, RED, 700, "end")
        else:
            status = f'<circle cx="{476 - len(lang) * 6.2 - 11:.0f}" cy="226" r="4" fill="{LANG_COLOR[lang]}"/>' + t(476, 230, lang, 10, MUT, anchor="end")
        body = (
            f'<rect width="{W}" height="{H}" fill="{PANEL}"/>'
            # window title bar
            + f'<rect width="{W}" height="36" fill="#fff" fill-opacity=".02"/><path d="M0 36.5H{W}" stroke="#fff" stroke-opacity=".07"/>'
            + "".join(f'<circle cx="{22 + i * 16}" cy="18" r="4.5" fill="{c}"/>' for i, c in enumerate([RED, "#2a2a2f", "#2a2a2f"]))
            + t(82, 22, file, 12, MUT if dead else TXT, 700)
            + t(476, 22, kicker if not dead else "ARCHIVED", 9, RED if dead else DIM, 700, "end", 2)
            # body = the viz as hero
            + vis()
            + t(28, 186, redact(desc), 11)
            # status bar
            + f'<path d="M24 206.5H476" stroke="#fff" stroke-opacity=".06"/>'
            + t(24, 230, meta, 10, "#55555b")
            + status
        )
        write(f"card-{key}", W, H, body, "@keyframes up{to{transform:translateY(var(--h))}}")


# ---------------------------------------------------------------- stack (tree output)

STACK = [
    ("languages", ["TypeScript", "C#", "Rust", "Lua", "JavaScript", "C++"]),
    ("frontend", ["Next.js", "React", "SvelteKit", "Vue", "Tauri", "Tailwind"]),
    ("backend", ["NestJS", "Bun", "Elysia", "Express", "ASP.NET Core", "Prisma"]),
    ("data", ["PostgreSQL", "Redis", "MySQL", "MongoDB"]),
    ("infra", ["Docker", "Linux", "Git", "Vercel"]),
]


def stack():
    W, top, gap = 1000, 46, 46
    H = top + (len(STACK) - 1) * gap + 42
    body = f'<rect width="{W}" height="{H}" fill="{PANEL}"/>'
    n = 0
    for r, (label, items) in enumerate(STACK):
        y = top + r * gap
        conn = "└─" if r == len(STACK) - 1 else "├─"
        body += t(40, y + 4, [(conn + " ", DIM), (label, TXT, 700)], 12, ls=1)
        x = 210
        for i, it in enumerate(items):
            w = len(it) * 7.2 + 24
            hot = i < 2  # first two per row are the ones I actually reach for
            body += (
                f'<g class="fi" style="animation-delay:{0.2 + n * 0.035:.2f}s">'
                f'<rect x="{x}" y="{y - 13}" width="{w:.1f}" height="26" rx="5" fill="{RED if hot else "#fff"}" fill-opacity="{".1" if hot else ".03"}" stroke="{RED if hot else "#fff"}" stroke-opacity="{".5" if hot else ".12"}"/>'
                + t(x + w / 2, y + 4, it, 12, TXT if hot else "#b9b7b4", anchor="middle")
                + "</g>"
            )
            x += w + 8
            n += 1
    write("stack", W, H, body + fx(W, H, sweep=False), defs=FX_DEFS)


# ---------------------------------------------------------------- footer + buttons


def footer():
    W, H = 1000, 196
    exit_at = 0.5
    bye_at = exit_at + 5 * 0.07 + 0.5
    closed_at = bye_at + 16 * 0.09 + 0.4
    body = (
        f'<rect width="{W}" height="{H}" fill="{PANEL}"/>'
        + t(36, 52, PROMPT, 13)
        + typed("te", 36 + 25 * 7.8, 52, [("exit", TXT)], 13, exit_at, hide_at=bye_at)
        + typed("tb", 36, 108, [("goodbye, friend.", TXT, 700)], 30, bye_at, 0.09)
        + t(36, 148, "[ connection to fsociety closed ]", 12, DIM, cls="fi", style=f"animation-delay:{closed_at:.2f}s")
        + t(36, 172, "uptime: since 2021   ·   control is an illusion", 11, "#55555b", cls="fi", style=f"animation-delay:{closed_at + 0.3:.2f}s")
        + fx(W, H)
    )
    write("footer", W, H, body, defs=FX_DEFS)


BUTTONS = [
    ("github", "GITHUB", "@uhmpasterig"),
    ("npm", "NPM", "~uhmpasterig"),
]


def buttons():
    W, H = 490, 64
    for key, label, value in BUTTONS:
        body = (
            f'<rect width="{W}" height="{H}" fill="{PANEL}"/>'
            '<linearGradient id="tl" x1="0" x2="1"><stop offset="0" stop-color="#ff1a35"/><stop offset="1" stop-color="#ff1a35" stop-opacity="0"/></linearGradient>'
            f'<rect width="{W}" height="1.5" fill="url(#tl)" opacity=".7"/>'
            + t(22, 26, label, 9, MUT, ls=2)
            + t(22, 46, value, 14, TXT, 700)
            + t(W - 22, 41, "↗", 18, RED, 700, "end")
        )
        write(f"btn-{key}", W, H, body)


if __name__ == "__main__":
    whoami()
    dividers()
    cards()
    stack()
    footer()
    buttons()
