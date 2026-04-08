"""
PACT Model Roster — Tekken-Style Character Card Generator

Generates fighting-game inspired roster cards for each AI model
in the PACT multi-model delegation system.

Usage:
  python .claude/tools/generate_roster_cards.py

Output:
  .claude/tools/roster/claude.png
  .claude/tools/roster/trinity.png
  .claude/tools/roster/m25.png
  .claude/tools/roster/roster_lineup.png  (all three side by side)
"""

import os
from PIL import Image, ImageDraw, ImageFont
import urllib.request
import io

ROSTER_DIR = os.path.join(os.path.dirname(__file__), "roster")
os.makedirs(ROSTER_DIR, exist_ok=True)

# Card dimensions
CARD_W = 480
CARD_H = 720

# Try to get a good font, fall back to default
def get_font(size, bold=False):
    """Try system fonts in order of preference."""
    font_candidates = [
        "C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/consola.ttf",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def get_title_font(size):
    """Get a bold/impact font for the model name."""
    bold_fonts = [
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/seguisb.ttf",
    ]
    for path in bold_fonts:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def hex_to_rgb(hex_str):
    """Convert '#RRGGBB' to (R, G, B)."""
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def draw_stat_bar(draw, x, y, width, value, color, label, fonts):
    """Draw a single stat bar with label and value."""
    bar_h = 16
    # Label
    draw.text((x, y - 2), label, fill=(180, 180, 180), font=fonts["small"])
    # Background bar
    draw.rounded_rectangle(
        [x + 110, y, x + 110 + width, y + bar_h],
        radius=3, fill=(40, 40, 50)
    )
    # Filled bar
    fill_w = int(width * value / 100)
    if fill_w > 0:
        draw.rounded_rectangle(
            [x + 110, y, x + 110 + fill_w, y + bar_h],
            radius=3, fill=color
        )
    # Value text
    draw.text(
        (x + 110 + width + 8, y - 2),
        str(value), fill=(220, 220, 220), font=fonts["small"]
    )


def draw_glow_circle(img, center, radius, color, alpha=40):
    """Draw a soft glow effect behind the icon area."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for r in range(radius, 0, -2):
        a = int(alpha * (r / radius))
        c = color + (a,)
        draw.ellipse(
            [center[0]-r, center[1]-r, center[0]+r, center[1]+r],
            fill=c
        )
    return Image.alpha_composite(img, overlay)


def fetch_logo(url, size=(120, 120)):
    """Download and resize a logo from URL. Returns None on failure."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (PACT Roster Generator)"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        logo = Image.open(io.BytesIO(data)).convert("RGBA")
        logo.thumbnail(size, Image.Resampling.LANCZOS)
        return logo
    except Exception as e:
        print(f"  Could not fetch logo from {url}: {e}")
        return None


def draw_role_icon(draw, center, role, color, size=60):
    """Draw a geometric icon representing the model's role."""
    cx, cy = center
    s = size

    if role == "orchestrator":
        # Star/crown shape
        points = []
        import math
        for i in range(5):
            # Outer point
            angle = math.radians(-90 + i * 72)
            points.append((cx + s * math.cos(angle), cy + s * math.sin(angle)))
            # Inner point
            angle = math.radians(-90 + i * 72 + 36)
            points.append((cx + s * 0.4 * math.cos(angle), cy + s * 0.4 * math.sin(angle)))
        draw.polygon(points, fill=color)

    elif role == "research":
        # Magnifying glass / eye shape
        draw.ellipse([cx-s, cy-s*0.6, cx+s, cy+s*0.6], outline=color, width=4)
        draw.ellipse([cx-s*0.35, cy-s*0.25, cx+s*0.35, cy+s*0.25], fill=color)

    elif role == "code":
        # Angle brackets < / >
        draw.line([(cx-s*0.3, cy-s*0.5), (cx-s*0.8, cy), (cx-s*0.3, cy+s*0.5)],
                  fill=color, width=5)
        draw.line([(cx+s*0.3, cy-s*0.5), (cx+s*0.8, cy), (cx+s*0.3, cy+s*0.5)],
                  fill=color, width=5)


def generate_card(name, full_name, tagline, role, color_hex, accent_hex,
                  stats, strengths, logo_url=None):
    """Generate a single Tekken-style character card."""
    color = hex_to_rgb(color_hex)
    accent = hex_to_rgb(accent_hex)

    # Create card with dark gradient background
    img = Image.new("RGBA", (CARD_W, CARD_H), accent + (255,))
    draw = ImageDraw.Draw(img)

    # Background gradient effect (darker at bottom)
    for y in range(CARD_H):
        t = y / CARD_H
        r = int(accent[0] * (1 - t * 0.5))
        g = int(accent[1] * (1 - t * 0.5))
        b = int(accent[2] * (1 - t * 0.5))
        draw.line([(0, y), (CARD_W, y)], fill=(r, g, b))

    # Accent stripe at top
    draw.rectangle([0, 0, CARD_W, 6], fill=color)

    # Diagonal accent lines (background texture)
    for i in range(-CARD_H, CARD_W + CARD_H, 40):
        draw.line([(i, 0), (i + CARD_H, CARD_H)],
                  fill=color + (15,) if len(color) == 3 else color, width=1)

    fonts = {
        "title": get_title_font(42),
        "subtitle": get_font(18),
        "tagline": get_font(22, bold=True),
        "body": get_font(15),
        "small": get_font(13),
        "stat_label": get_font(12),
    }

    # --- Icon / Logo Area ---
    icon_center = (CARD_W // 2, 130)
    img = draw_glow_circle(img, icon_center, 80, color, alpha=30)
    draw = ImageDraw.Draw(img)  # re-acquire after composite

    # Try to fetch and paste a logo
    logo = None
    if logo_url:
        logo = fetch_logo(logo_url, size=(100, 100))

    if logo:
        lx = icon_center[0] - logo.width // 2
        ly = icon_center[1] - logo.height // 2
        img.paste(logo, (lx, ly), logo)
        draw = ImageDraw.Draw(img)
    else:
        # Fallback: draw geometric role icon
        draw_role_icon(draw, icon_center, role, color, size=50)

    # --- Name & Tagline ---
    # Center the name
    bbox = draw.textbbox((0, 0), name.upper(), font=fonts["title"])
    tw = bbox[2] - bbox[0]
    draw.text(((CARD_W - tw) / 2, 200), name.upper(), fill=color, font=fonts["title"])

    # Tagline
    bbox = draw.textbbox((0, 0), tagline, font=fonts["tagline"])
    tw = bbox[2] - bbox[0]
    draw.text(((CARD_W - tw) / 2, 252), tagline, fill=(200, 200, 200), font=fonts["tagline"])

    # Full model name
    bbox = draw.textbbox((0, 0), full_name, font=fonts["small"])
    tw = bbox[2] - bbox[0]
    draw.text(((CARD_W - tw) / 2, 280), full_name,
              fill=(120, 120, 140), font=fonts["small"])

    # --- Divider ---
    draw.line([(40, 310), (CARD_W - 40, 310)], fill=color + (80,), width=1)

    # --- Stat Bars ---
    stat_names = ["Reasoning", "Speed", "Cost Eff.", "Context", "Code Qual."]
    stat_keys = ["reasoning", "speed", "cost_efficiency", "context_window", "code_quality"]
    bar_y = 325
    bar_w = 200

    for i, (label, key) in enumerate(zip(stat_names, stat_keys)):
        val = stats.get(key, 0)
        draw_stat_bar(draw, 30, bar_y + i * 28, bar_w, val, color, label, fonts)

    # --- Strengths ---
    draw.line([(40, bar_y + 5 * 28 + 10), (CARD_W - 40, bar_y + 5 * 28 + 10)],
              fill=color + (80,), width=1)

    sy = bar_y + 5 * 28 + 22
    draw.text((30, sy), "STRENGTHS", fill=color, font=fonts["small"])
    sy += 22

    for i, s in enumerate(strengths[:5]):
        bullet = f"  {s}"
        draw.text((30, sy + i * 20), bullet, fill=(170, 170, 180), font=fonts["small"])

    # --- Bottom accent ---
    draw.rectangle([0, CARD_H - 4, CARD_W, CARD_H], fill=color)

    # --- Border ---
    draw.rounded_rectangle([0, 0, CARD_W - 1, CARD_H - 1], radius=8,
                           outline=color + (100,), width=2)

    return img


def generate_lineup(cards, names):
    """Generate a side-by-side lineup image."""
    gap = 20
    total_w = len(cards) * CARD_W + (len(cards) - 1) * gap + 60
    total_h = CARD_H + 120

    img = Image.new("RGBA", (total_w, total_h), (10, 10, 18, 255))
    draw = ImageDraw.Draw(img)

    # Title
    title_font = get_title_font(36)
    title = "P A C T   M O D E L   R O S T E R"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((total_w - tw) / 2, 20), title, fill=(212, 168, 67), font=title_font)

    subtitle_font = get_font(16)
    sub = "Claude orchestrates. Workers execute. Hooks verify."
    bbox = draw.textbbox((0, 0), sub, font=subtitle_font)
    tw = bbox[2] - bbox[0]
    draw.text(((total_w - tw) / 2, 65), sub, fill=(140, 140, 160), font=subtitle_font)

    # Paste cards
    x = 30
    for card in cards:
        img.paste(card, (x, 95), card)
        x += CARD_W + gap

    return img


def main():
    print("Generating PACT Model Roster cards...")

    # Logo URLs (official or recognizable)
    # These may need updating if URLs change
    claude_logo = "https://avatars.githubusercontent.com/u/76263028?s=200"  # Anthropic GitHub avatar
    arcee_logo = "https://avatars.githubusercontent.com/u/110646689?s=200"  # Arcee AI GitHub avatar
    minimax_logo = "https://avatars.githubusercontent.com/u/129aborting?s=200"  # Will likely fail, use icon

    print("  Generating Claude card...")
    claude_card = generate_card(
        name="Claude",
        full_name="Claude Opus 4.6 (Anthropic)",
        tagline="The Architect",
        role="orchestrator",
        color_hex="#D4A843",
        accent_hex="#1A1A2E",
        stats={"reasoning": 99, "speed": 60, "cost_efficiency": 30,
               "context_window": 95, "code_quality": 98},
        strengths=[
            "Architecture & system design",
            "Complex debugging & causal tracing",
            "Security & encryption review",
            "Code review & final authority",
            "Multi-hop dependency analysis",
        ],
        logo_url=claude_logo,
    )
    claude_card.save(os.path.join(ROSTER_DIR, "claude.png"))
    print("    Saved claude.png")

    print("  Generating Trinity card...")
    trinity_card = generate_card(
        name="Trinity",
        full_name="Arcee Trinity-Large-Thinking",
        tagline="The Scholar",
        role="research",
        color_hex="#6C63FF",
        accent_hex="#1B1B3A",
        stats={"reasoning": 78, "speed": 85, "cost_efficiency": 96,
               "context_window": 75, "code_quality": 55},
        strengths=[
            "Web research & doc summarization",
            "Plan & feature flow drafting",
            "Content classification (maturity)",
            "Changelog & API pattern extraction",
            "Large context synthesis (262K)",
        ],
        logo_url=arcee_logo,
    )
    trinity_card.save(os.path.join(ROSTER_DIR, "trinity.png"))
    print("    Saved trinity.png")

    print("  Generating M2.5 card...")
    m25_card = generate_card(
        name="M2.5",
        full_name="MiniMax M2.5",
        tagline="The Coder",
        role="code",
        color_hex="#00E676",
        accent_hex="#0D1B0F",
        stats={"reasoning": 72, "speed": 90, "cost_efficiency": 96,
               "context_window": 65, "code_quality": 80},
        strengths=[
            "Boilerplate & CRUD generation",
            "Test file scaffolding",
            "Pattern replication from examples",
            "Bulk data processing scripts",
            "SWE-bench verified: 80.2%",
        ],
        logo_url=minimax_logo,
    )
    m25_card.save(os.path.join(ROSTER_DIR, "m25.png"))
    print("    Saved m25.png")

    print("  Generating Gemini card...")
    gemini_logo = "https://avatars.githubusercontent.com/u/1342004?s=200"  # Google GitHub avatar
    gemini_card = generate_card(
        name="Gemini",
        full_name="Gemini 2.5 Pro (Google)",
        tagline="The Commander",
        role="orchestrator",
        color_hex="#4285F4",
        accent_hex="#1A1A2E",
        stats={"reasoning": 90, "speed": 80, "cost_efficiency": 85,
               "context_window": 95, "code_quality": 85},
        strengths=[
            "Built-in Google Search",
            "Free tier — zero cost sessions",
            "Strong code generation",
            "Shares all PACT governance",
            "Orchestrates workers via pact-delegate",
        ],
        logo_url=gemini_logo,
    )
    gemini_card.save(os.path.join(ROSTER_DIR, "gemini.png"))
    print("    Saved gemini.png")

    print("  Generating lineup card...")
    lineup = generate_lineup(
        [claude_card, gemini_card, trinity_card, m25_card],
        ["Claude", "Gemini", "Trinity", "M2.5"]
    )
    lineup.save(os.path.join(ROSTER_DIR, "roster_lineup.png"))
    print("    Saved roster_lineup.png")

    print("Done! Cards at .claude/tools/roster/")


if __name__ == "__main__":
    main()
