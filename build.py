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
from fontTools.pens.svgPathPen import SVGPathPen
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
    return TTFont(fetch(f"JetBrainsMono-{weight}.ttf", FONT_URL.format(weight)))


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


def glyph_paths(text, x, baseline, size, weight="ExtraBold"):
    f = font(weight)
    gs, cmap, s = f.getGlyphSet(), f.getBestCmap(), size / f["head"].unitsPerEm
    out = []
    for ch in text:
        name = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[name].draw(pen)
        out.append(f'<path transform="translate({x:.2f} {baseline}) scale({s:.5f} {-s:.5f})" d="{pen.getCommands()}"/>')
        x += f["hmtx"][name][0] * s
    return "".join(out)


def corners(w, h, m=16, l=18):
    return "".join(
        f'<path d="M{a} {b + dy}V{b}H{a + dx}" stroke="#fff" stroke-opacity=".35" stroke-width="1.5"/>'
        for a, b, dx, dy in ((m, m, l, l), (w - m, m, -l, l), (m, h - m, l, -l), (w - m, h - m, -l, -l))
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


# ---------------------------------------------------------------- hero

LOG = [
    "[+] nmap -sS -T4 10.0.0.0/24", "PORT      STATE  SERVICE", "22/tcp    open   ssh", "80/tcp    open   http",
    "443/tcp   open   https", "6379/tcp  open   redis", "[*] fsociety00.dat   2.1K   -rw-r--r--",
    "root@fsociety:~# whoami", "root", "[+] handshake captured  ch 6  -71dBm",
    "hash  5f4dcc3b5aa765d61d8327deb882cf99", "[!] e-corp backup node unreachable", "$ tail -f /var/log/auth.log",
    "sshd[1337]: Accepted publickey for elliot", "[*] mounting /dev/sdb1 on /mnt/ecoin",
    "00000000: 8f3a 1c9e 77b2 04de 5a11 c0de", "00000010: dead beef 0b5e 55ed f50c 1e77",
    "[+] payload staged  stage2.bin  4096B", "$ ./fsociety.sh --phase 2", "[*] 5/9 countdown armed",
    "[+] whiterose: time is never time at all", "$ shred -u ~/.bash_history",
]


def log_column(x, lines, dur, lh=18):
    rows = "".join(
        t(x, 14 + i * lh, [(l[:3], RED), (l[3:], "#fff")] if l.startswith("[") else l, 11, "#fff", op=".05")
        for i, l in enumerate(lines * 2)
    )
    return f'<g style="animation:up {dur}s linear infinite;--h:-{len(lines) * lh}px">{rows}</g>'


def hero():
    W, H = 1000, 400
    size, base = 104, 232
    adv = 600 * size / 1000
    x0 = (W - 11.7 * adv) / 2  # "uhmpasterig" + a tucked-in red dot
    gk = 'keyTimes="0;.80;.82;.85;.87;.90;.92;.95" dur="5s" calcMode="discrete" repeatCount="indefinite"'
    an = lambda attr, v: f'<animate attributeName="{attr}" values="{v}" {gk}/>'
    tr = lambda v: f'<animateTransform attributeName="transform" type="translate" values="{v}" {gk}/>'
    slices = [
        ("s1", "150;162;206;178;232;158;150;150", "8;16;10;22;8;18;8;8", RED, "0 0;18 0;-12 0;10 0;-24 0;6 0;0 0;0 0", "0;1;0;1;1;0;0;0"),
        ("s2", "150;214;170;238;190;220;150;150", "8;12;20;9;14;7;8;8", TXT, "0 0;-14 0;10 0;-8 0;18 0;-5 0;0 0;0 0", "0;1;1;0;1;1;0;0"),
        ("s3", "150;190;150;246;150;170;150;150", "8;6;8;4;8;3;8;8", RED, "0 0;30 0;0 0;-32 0;0 0;14 0;0 0;0 0", "0;1;0;1;0;1;0;0"),
    ]
    glitch = "".join(
        f'<clipPath id="{i}"><rect width="{W}" y="150" height="8">{an("y", y)}{an("height", h)}</rect></clipPath>'
        f'<g clip-path="url(#{i})" opacity="0"><use href="#ttl" fill="{c}">{tr(m)}</use>{an("opacity", o)}</g>'
        for i, y, h, c, m, o in slices
    )
    defs = (
        FX_DEFS + f'<g id="ttl">{glyph_paths("uhmpasterig", x0, base, size)}</g>'
        '<radialGradient id="gl"><stop offset="0" stop-color="#ff1a35" stop-opacity=".28"/><stop offset=".6" stop-color="#ff1a35" stop-opacity=".06"/><stop offset="1" stop-color="#ff1a35" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="vg" cx="50%" cy="50%" r="70%"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".85"/></radialGradient>'
    )
    css = (
        "@keyframes up{to{transform:translateY(var(--h))}}"
        ".fl{animation:fl 7s steps(1) infinite}@keyframes fl{0%,100%{opacity:1}91%{opacity:.35}92%{opacity:1}95%{opacity:.7}96%{opacity:1}}"
    )
    body = (
        f'<rect width="{W}" height="{H}" fill="{BG}"/>'
        + log_column(40, LOG, 70) + log_column(560, LOG[11:] + LOG[:11], 55)
        + f'<ellipse class="br" cx="500" cy="205" rx="420" ry="170" fill="url(#gl)"/>'
        + f'<rect width="{W}" height="{H}" fill="url(#vg)"/>'
        + '<g class="fl">'
        + f'<use href="#ttl" fill="#fff" opacity=".18" transform="translate(-2 1)"/>'
        + f'<use href="#ttl" fill="{RED}" opacity=".85" transform="translate(3 0)"/>'
        + f'<use href="#ttl" fill="{TXT}">{tr("0 0;-4 0;3 0;0 0;-2 0;0 0;0 0;0 0")}</use>'
        + f'<g fill="{RED}">{glyph_paths(".", x0 + 10.7 * adv, base, size)}</g>'
        + glitch + "</g>"
        + typed("tp", 500 - 16 * 11.4 / 2, 304, [(">", RED, 700), (" hello, friend.", TXT)], 19, 0.8, 0.09)
        + t(36, 46, "UHMPASTERIG", 12, TXT, 700, ls=2.4)
        + t(36, 66, "FULL-STACK DEVELOPER", 11, MUT, ls=2)
        + t(964, 46, "EPS1.0_HELLOFRIEND.MOV", 12, TXT, 700, "end", 2.4)
        + t(964, 66, "S01E00  ·  1080P", 11, MUT, anchor="end", ls=2)
        + f'<circle cx="41" cy="359" r="4" fill="{RED}" class="bl"/>'
        + t(54, 363, "CONTROL IS AN ILLUSION", 11, MUT, ls=2)
        + t(964, 363, "GITHUB.COM/UHMPASTERIG", 11, MUT, anchor="end", ls=2)
        + corners(W, H) + fx(W, H)
    )
    write("hero", W, H, body, css, defs)


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


# ---------------------------------------------------------------- section labels

LABELS = [
    ("whoami", "01", "eps1.1_wh0ami.sh"),
    ("work", "02", "eps1.2_pr0jects.tar"),
    ("stack", "03", "eps1.3_st4ck.dat"),
    ("repos", "04", "eps1.4_r3pos.log"),
    ("eof", "05", "eps1.9_g00dbye.avi"),
]


def labels():
    for name, num, title in LABELS:
        end = (8 + len(title)) * 8.2 + 14  # "// " + num + "   " + title at 12px, letter-spacing 1
        body = t(0, 16, [("// ", RED), (num, RED, 700), ("   " + title, MUT)], 12, ls=1) + f'<path d="M{end:.0f} 12.5H1000" stroke="#fff" stroke-opacity=".1"/>'
        write(f"label-{name}", 1000, 24, body, frame=False)


# ---------------------------------------------------------------- project cards

LANG_COLOR = {"C++": "#f34b7d", "TypeScript": "#3178c6", "Lua": "#8a95ff"}


def vis_netlogger():
    ev = [
        ("→", "playerConnecting", "212B"), ("←", "esx:getSharedObject", "96B"), ("→", "chat:addMessage", "148B"),
        ("←", "txAdmin:heartbeat", "64B"), ("→", "baseevents:onPlayerDied", "88B"), ("←", "vMenu:sync", "1.2K"),
        ("→", "hud:updateStatus", "40B"), ("←", "inventory:refresh", "3.4K"),
    ]
    rows = "".join(
        t(300, 66 + i * 14, [(a, RED if a == "→" else MUT), (f" {e:<23}", "#b9b7b4"), (f"{b:>5}", MUT)], 9.5)
        for i, (a, e, b) in enumerate(ev * 2)
    )
    return (
        '<linearGradient id="fd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".3" stop-color="#fff"/><stop offset=".7" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        '<mask id="fm"><rect x="290" y="50" width="190" height="80" fill="url(#fd)"/></mask>'
        f'<g mask="url(#fm)"><g style="animation:up 9s linear infinite;--h:-{len(ev) * 14}px">{rows}</g></g>'
    )


def vis_orbit():
    cx, cy = 404, 88
    planets = [(22, 4, TXT, 4), (38, 3, RED, 7), (38, 2.5, MUT, 7, 180)]
    out = f'<circle cx="{cx}" cy="{cy}" r="16" fill="{RED}" opacity=".12" class="br"/><circle cx="{cx}" cy="{cy}" r="6" fill="{RED}"/>'
    out += "".join(f'<circle cx="{cx}" cy="{cy}" r="{r}" stroke="#fff" stroke-opacity=".14" stroke-dasharray="2 4"/>' for r in (22, 38))
    for r, pr, c, dur, *start in planets:
        a = start[0] if start else 0
        out += (
            f'<g><animateTransform attributeName="transform" type="rotate" from="{a} {cx} {cy}" to="{a + 360} {cx} {cy}" dur="{dur}s" repeatCount="indefinite"/>'
            f'<circle cx="{cx + r}" cy="{cy}" r="{pr}" fill="{c}"/></g>'
        )
    return out


def vis_redis():
    cx, cy = 404, 88
    nodes = [(334, 60), (474, 60), (334, 116), (474, 116)]
    out = "".join(f'<path d="M{cx} {cy}L{x} {y}" stroke="#fff" stroke-opacity=".14" stroke-dasharray="2 3"/>' for x, y in nodes)
    out += "".join(
        f'<circle r="2.5" fill="{RED}"><animate attributeName="cx" values="{cx};{x}" dur="1.8s" begin="{i * 0.45}s" repeatCount="indefinite"/>'
        f'<animate attributeName="cy" values="{cy};{y}" dur="1.8s" begin="{i * 0.45}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="0;1;1;0" dur="1.8s" begin="{i * 0.45}s" repeatCount="indefinite"/></circle>'
        for i, (x, y) in enumerate(nodes)
    )
    out += "".join(f'<rect x="{x - 7}" y="{y - 7}" width="14" height="14" rx="3" fill="{PANEL}" stroke="#fff" stroke-opacity=".4"/>' for x, y in nodes)
    out += f'<circle cx="{cx}" cy="{cy}" r="18" fill="{RED}" opacity=".12" class="br"/><circle cx="{cx}" cy="{cy}" r="10" fill="{PANEL}" stroke="{RED}" stroke-width="1.5"/>'
    return out + t(cx, cy + 3.5, "R", 10, RED, 700, "middle")


def vis_unluac():
    hexb = "1B 4C 75 61 54 00 19 93".split()
    cw = 9.5 * 0.6
    keys = ";".join(f"{i / len(hexb):.3f}" for i in range(len(hexb)))
    xs = ";".join(f"{300 + i * 3 * cw - 2:.1f}" for i in range(len(hexb)))
    return (
        t(300, 60, "LUAC 5.4 HEADER", 9, MUT, ls=2)
        + f'<rect y="70" width="{2 * cw + 4:.1f}" height="14" rx="2" fill="{RED}" opacity=".25"><animate attributeName="x" values="{xs}" keyTimes="{keys}" dur="3.2s" calcMode="discrete" repeatCount="indefinite"/></rect>'
        + t(300, 81, " ".join(hexb), 9.5, "#b9b7b4")
        + t(300, 102, "↓ decompile", 9.5, RED)
        + t(300, 122, [("local ", RED), ("f = ", TXT), ("function", RED), ("()", TXT)], 9.5)
        + f'<rect x="{300 + 20 * cw:.1f}" y="113" width="{cw:.1f}" height="11" fill="{RED}" class="bl"/>'
    )


def vis_escrow():
    cx, k = 448, 'keyTimes="0;.35;.45;.8;.9;1" dur="4s" repeatCount="indefinite"'
    show = lambda v: f'<animate attributeName="opacity" values="{v}" {k} calcMode="discrete"/>'
    locked, open_ = show("1;1;0;0;1;1"), show("0;0;1;1;0;0")
    return (
        t(300, 60, "ASSET ESCROW", 9, MUT, ls=2)
        + f'<g>{locked}{t(300, 84, "a3f9 1c0e 77b2 04de", 9.5, "#b9b7b4")}{t(300, 100, "5a11 c0de 9f02 e8d2", 9.5, "#b9b7b4")}{t(300, 120, "ENCRYPTED", 9, MUT, ls=2)}</g>'
        + f'<g opacity="0">{open_}{t(300, 84, [("local ", RED), ("Config = {}", TXT)], 9.5)}{t(300, 100, "Config.Debug = false", 9.5, TXT)}{t(300, 120, "BYPASSED", 9, RED, 700, ls=2)}</g>'
        + f'<g><animateTransform attributeName="transform" type="translate" values="0 0;0 0;0 -7;0 -7;0 0;0 0" {k}/>'
        f'<path d="M{cx - 10} 92V80a10 10 0 0 1 20 0V92" stroke="{TXT}" stroke-width="3"/></g>'
        + f'<rect x="{cx - 16}" y="88" width="32" height="26" rx="4" fill="{PANEL}" stroke="{RED}" stroke-width="1.5"/>'
        + f'<circle cx="{cx}" cy="99" r="3" fill="{RED}"/><path d="M{cx} 101v6" stroke="{RED}" stroke-width="2"/>'
    )


def vis_botting():
    cells = "".join(
        f'<rect x="{300 + i % 12 * 14}" y="{70 + i // 12 * 14}" width="9" height="9" rx="2" fill="{RED}" fill-opacity=".08">'
        f'<animate attributeName="fill-opacity" values=".08;.08;.9;.9;.08" keyTimes="0;{0.05 + i * 0.015:.3f};{0.07 + i * 0.015:.3f};.92;1" dur="6s" repeatCount="indefinite"/></rect>'
        for i in range(48)
    )
    return t(300, 60, "SLOTS", 9, MUT, ls=2) + t(466, 60, "BOTS JOINING", 9, RED, anchor="end", ls=2) + cells


def redact(line):
    return [(m, "#2a2a30" if m[0] == "█" else "#8a8a90") for m in re.findall(r"█+|[^█]+", line)]


# lang=None marks a project that is no longer public
CARDS = [
    ("escrow", "TAKEN DOWN", "ESCROW-EXPLOIT", "FiveM asset escrow exploit",
     ["Exploit for FiveM's asset escrow system. Had to take", "it offline, so this card is all that's left. ██████."],
     "fivem · cfx.re · asset escrow", None, vis_escrow),
    ("botting", "EXPLOIT", "PLAYER-BOTTING", "FiveM player botting exploit",
     ["Joined bot players to FiveM servers and filled up", "their player slots. ████ ███████ ██ ████."],
     "fivem · player slots · bots", None, vis_botting),
    ("netlogger", "NETWORK", "NETWORK-LOGGER", "FiveM server network logger",
     ["Patched citizen-server build that logs every incoming", "and outgoing event of every resource on your server."],
     "fivem · citizen-server · events", "C++", vis_netlogger),
    ("orbit", "UI COMPONENT", "REACT-ORBIT", "Orbit component for React",
     ["Puts any element on an animated orbit around a center.", "Published on npm, live demo on Vercel."],
     "react · npm · animation", "TypeScript", vis_orbit),
    ("redis", "MICROSERVICES", "NEST-REDIS-CONFIG", "Shared config for NestJS services",
     ["Alternative to @nestjs/config that stores values in", "Redis, so every microservice reads the same config."],
     "nestjs · redis · npm", "TypeScript", vis_redis),
    ("unluac", "REVERSING", "UNLUAC-54", "Lua 5.4 bytecode decompiler",
     ["Turns dumped .luac files back into runnable Lua source.", "Drop the file in, run one script, read the code."],
     "luac · lua 5.4 · decompiler", "Lua", vis_unluac),
]


def cards():
    W, H = 500, 250
    for n, (key, tag, name, sub, desc, meta, lang, vis) in enumerate(CARDS, 1):
        num = f"{n:02}"
        status = (
            f'<circle cx="{472 - 7 * 6 - 10}" cy="222.5" r="4" fill="{RED}" class="bl"/>' + t(472, 226, "OFFLINE", 10, RED, 700, "end")
            if lang is None
            else f'<circle cx="{472 - len(lang) * 6 - 10}" cy="222.5" r="4" fill="{LANG_COLOR[lang]}"/>' + t(472, 226, lang, 10, MUT, anchor="end")
        )
        tw = len(tag) * (9 * 0.6 + 1.5) + 18
        body = (
            f'<rect width="{W}" height="{H}" fill="{PANEL}"/>'
            '<linearGradient id="tl" x1="0" x2="1"><stop offset="0" stop-color="#ff1a35" stop-opacity="0"/><stop offset=".5" stop-color="#ff1a35"/><stop offset="1" stop-color="#ff1a35" stop-opacity="0"/></linearGradient>'
            f'<rect width="{W}" height="1.5" fill="url(#tl)" opacity=".7"/>'
            + t(28, 40, [(num, RED, 700), ("  /  PROJECT", MUT)], 10, ls=2)
            + f'<rect x="{472 - tw:.1f}" y="26" width="{tw:.1f}" height="19" rx="9.5" fill="{RED}" fill-opacity=".1" stroke="{RED}" stroke-opacity=".6"/>'
            + t(472 - tw / 2, 39, tag, 9, RED, 700, "middle", 1.5)
            + vis()
            + t(28, 104, name, 24, TXT, 700)
            + t(28, 128, sub, 12, TXT, 700)
            + "".join(t(28, 162 + i * 18, redact(l), 11) for i, l in enumerate(desc))
            + '<path d="M28 200.5H472" stroke="#fff" stroke-opacity=".07"/>'
            + t(28, 226, meta, 10, "#55555b")
            + status
        )
        write(f"card-{key}", W, H, body, "@keyframes up{to{transform:translateY(var(--h))}}")


# ---------------------------------------------------------------- stack

STACK = [
    ("LANGUAGES", ["TypeScript", "C#", "Rust", "Lua", "JavaScript", "C++"]),
    ("FRONTEND", ["Next.js", "React", "SvelteKit", "Vue", "Tauri", "Tailwind"]),
    ("BACKEND", ["NestJS", "Bun", "Elysia", "Express", "ASP.NET Core", "Prisma"]),
    ("DATA", ["PostgreSQL", "Redis", "MySQL", "MongoDB"]),
    ("INFRA", ["Docker", "Linux", "Git", "Vercel"]),
]


def stack():
    W, top, gap = 1000, 82, 46
    H = top + (len(STACK) - 1) * gap + 42
    body = f'<rect width="{W}" height="{H}" fill="{PANEL}"/>' + t(36, 38, [("$ ", RED, 700), ("cat ~/.stack", MUT)], 12)
    body += '<path d="M36 54.5H964" stroke="#fff" stroke-opacity=".06"/>'
    n = 0
    for r, (label, items) in enumerate(STACK):
        y = top + r * gap
        body += t(36, y + 4, [("— ", RED), (label, TXT, 700)], 11, ls=2)
        x = 200
        for i, it in enumerate(items):
            w = len(it) * 7.2 + 24
            hot = i < 2
            body += (
                f'<g class="fi" style="animation-delay:{0.3 + n * 0.04:.2f}s">'
                f'<rect x="{x}" y="{y - 13}" width="{w:.1f}" height="26" rx="5" fill="{RED if hot else "#fff"}" fill-opacity="{".1" if hot else ".03"}" stroke="{RED if hot else "#fff"}" stroke-opacity="{".55" if hot else ".12"}"/>'
                + t(x + w / 2, y + 4, it, 12, TXT if hot else "#b9b7b4", anchor="middle")
                + "</g>"
            )
            x += w + 8
            n += 1
    write("stack", W, H, body + fx(W, H, sweep=False), defs=FX_DEFS)


# ---------------------------------------------------------------- footer + buttons


def footer():
    W, H = 1000, 230
    exit_at = 0.5
    bye_at = exit_at + 5 * 0.07 + 0.5
    closed_at = bye_at + 17 * 0.09 + 0.4
    body = (
        f'<rect width="{W}" height="{H}" fill="{PANEL}"/>'
        + t(972, 196, "fsociety", 150, "#fff", 700, "end", op=".03")
        + t(36, 56, PROMPT, 13)
        + typed("te", 36 + 25 * 7.8, 56, [("exit", TXT)], 13, exit_at, hide_at=bye_at)
        + typed("tb", 36, 112, [("goodbye, friend.", TXT, 700)], 30, bye_at, 0.09)
        + t(36, 156, "logout", 12, MUT, cls="fi", style=f"animation-delay:{closed_at:.2f}s")
        + t(36, 178, "[connection to fsociety closed.]", 12, DIM, cls="fi", style=f"animation-delay:{closed_at + 0.3:.2f}s")
        + t(36, 206, "// thanks for scrolling this far.", 11, "#55555b", cls="fi", style=f"animation-delay:{closed_at + 0.6:.2f}s")
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
    hero()
    whoami()
    labels()
    cards()
    stack()
    footer()
    buttons()
