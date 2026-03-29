"""Generate PACT visual diagrams for Reddit post."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np


def draw_compound_intelligence():
    """Show how knowledge compounds across sessions."""
    fig, ax = plt.subplots(1, 1, figsize=(16, 9))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis('off')

    # Colors
    bg_dark = '#161b22'
    border = '#30363d'
    blue = '#58a6ff'
    green = '#3fb950'
    purple = '#bc8cff'
    orange = '#d29922'
    text_primary = '#e6edf3'
    text_secondary = '#8b949e'
    red = '#f85149'

    # Title
    ax.text(8, 8.5, 'PACT', ha='center', va='center',
            fontsize=26, fontweight='bold', color=text_primary, family='monospace')
    ax.text(8, 8.0, 'Compound Intelligence Across Sessions',
            ha='center', va='center', fontsize=14, color=text_secondary, family='monospace')

    # === Session boxes ===
    box_w = 4.0
    box_h = 5.5
    box_y = 1.5

    session_data = [
        (0.8, 'Session 1', blue,
         'Training data\n+ context window',
         'Researches sync strategy\nReads code + searches docs\nSaves synthesis to research/'),
        (5.8, 'Session 2', green,
         'Training data\n+ context window\n+ Session 1 synthesis',
         'Finds existing research\nDeepens with new angle\nApplies fix from Solutions KB'),
        (10.8, 'Session 3', purple,
         'Training data\n+ context window\n+ ALL prior synthesis',
         'Reads Knowledge Directory\nSkips 2 hours of research\nBuilds on compound intelligence'),
    ]

    for x, title, color, knows, does in session_data:
        # Main box
        box = FancyBboxPatch((x, box_y), box_w, box_h,
                             boxstyle="round,pad=0.15",
                             facecolor=bg_dark, edgecolor=color, linewidth=2.5)
        ax.add_patch(box)

        # Title bar background
        title_bar = FancyBboxPatch((x + 0.05, box_y + box_h - 0.7), box_w - 0.1, 0.6,
                                   boxstyle="round,pad=0.05",
                                   facecolor=color, edgecolor='none', alpha=0.15)
        ax.add_patch(title_bar)

        ax.text(x + box_w/2, box_y + box_h - 0.4, title,
                ha='center', va='center', fontsize=14, fontweight='bold',
                color=color, family='monospace')

        # KNOWS section
        ax.text(x + 0.3, box_y + box_h - 1.1, 'KNOWS',
                fontsize=9, color=text_secondary, family='monospace', fontweight='bold')
        ax.text(x + 0.3, box_y + box_h - 1.5, knows,
                fontsize=10, color=text_primary, family='monospace',
                va='top', linespacing=1.5)

        # Divider
        div_y = box_y + 2.8
        ax.plot([x + 0.2, x + box_w - 0.2], [div_y, div_y],
                color=border, linewidth=1, alpha=0.6)

        # DOES section
        ax.text(x + 0.3, div_y - 0.3, 'DOES',
                fontsize=9, color=text_secondary, family='monospace', fontweight='bold')
        ax.text(x + 0.3, div_y - 0.65, does,
                fontsize=9.5, color=text_primary, family='monospace',
                va='top', linespacing=1.6)

    # === Arrows between sessions ===
    arrow_y = box_y + box_h / 2 + 0.3
    for start_x, label in [(4.8, 'synthesis\nsaved'), (9.8, 'knowledge\ncompounds')]:
        ax.annotate('', xy=(start_x + 1.1, arrow_y),
                    xytext=(start_x, arrow_y),
                    arrowprops=dict(arrowstyle='->', color=orange,
                                   linewidth=3, mutation_scale=20))
        ax.text(start_x + 0.5, arrow_y + 0.55, label,
                ha='center', fontsize=8.5, color=orange, family='monospace',
                fontstyle='italic', linespacing=1.3)

    # === Bottom bar: knowledge systems ===
    bar_y = 0.35
    bar_h = 0.7
    bar = FancyBboxPatch((0.5, bar_y), 15, bar_h,
                         boxstyle="round,pad=0.08",
                         facecolor=bg_dark, edgecolor=border, linewidth=1.2)
    ax.add_patch(bar)

    systems = [
        ('Research Files', blue),
        ('Knowledge Directory', green),
        ('Bug Solutions', purple),
        ('Package Knowledge', orange),
        ('Feature Flows', red),
        ('Capability Baseline', '#8b949e'),
    ]

    spacing = 15.0 / len(systems)
    for i, (name, color) in enumerate(systems):
        cx = 0.5 + spacing * i + spacing / 2
        ax.text(cx, bar_y + bar_h/2, name, ha='center', va='center',
                fontsize=8.5, color=color, family='monospace', fontweight='bold')

    ax.text(8, 0.08, 'Persistent Knowledge Layer  (survives across sessions)',
            ha='center', fontsize=9, color=text_secondary, family='monospace',
            fontstyle='italic')

    plt.tight_layout(pad=0.3)
    plt.savefig('assets/pact-compound-intelligence.png', dpi=180,
                facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close()
    print("Saved: assets/pact-compound-intelligence.png")


def draw_pillars():
    """Show the 6 pillars as a clean architecture diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(16, 8))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 8)
    ax.axis('off')

    bg_dark = '#161b22'
    border = '#30363d'
    blue = '#58a6ff'
    green = '#3fb950'
    purple = '#bc8cff'
    orange = '#d29922'
    red = '#f85149'
    cyan = '#39d353'
    text_primary = '#e6edf3'
    text_secondary = '#8b949e'

    # Title
    ax.text(8, 7.5, 'PACT', ha='center', va='center',
            fontsize=26, fontweight='bold', color=text_primary, family='monospace')
    ax.text(8, 7.05, '6 Pillars of Agent Governance',
            ha='center', va='center', fontsize=14, color=text_secondary, family='monospace')

    pillars = [
        ('Mechanical\nEnforcement', '10 shell hooks\nthat BLOCK\nviolations', red,
         'Secrets, force push,\nedit-before-read,\ncommit behind remote'),
        ('Context\nReplacement', 'Architecture maps\n& lifecycle flows\nreplace memory', blue,
         'SYSTEM_MAP.yaml\nfeature flows\npackage knowledge'),
        ('Self-Evolving\nReasoning', '19 questions\nthe agent asks\nat decision points', green,
         'Agent adds its own\nredirections over time'),
        ('Structure vs\nBehavior', 'Wiring (spatial)\nvs flow (temporal)\nNever mix them.', purple,
         '"What files to touch?"\nvs\n"What breaks if wrong?"'),
        ('Multi-Agent\nResilience', 'Claude + Gemini\nshare hooks, rules\n& task tracker', orange,
         'Zero context loss\non agent switch\nOne set of rules'),
        ('Compound\nIntelligence', 'Research synthesis\nknowledge directory\ncapability baseline', cyan,
         'Each session\nsmarter than\nthe last'),
    ]

    pillar_width = 2.2
    gap = 0.2
    total_width = len(pillars) * pillar_width + (len(pillars) - 1) * gap
    start_x = (16 - total_width) / 2
    pillar_h = 5.6
    pillar_y = 0.8

    for i, (title, desc, color, detail) in enumerate(pillars):
        x = start_x + i * (pillar_width + gap)

        # Pillar box
        box = FancyBboxPatch((x, pillar_y), pillar_width, pillar_h,
                             boxstyle="round,pad=0.12",
                             facecolor=bg_dark, edgecolor=color, linewidth=2,
                             alpha=0.95)
        ax.add_patch(box)

        # Number badge
        badge_y = pillar_y + pillar_h - 0.5
        circle = plt.Circle((x + pillar_width/2, badge_y), 0.32,
                           facecolor=color, edgecolor='none', alpha=0.25)
        ax.add_patch(circle)
        ax.text(x + pillar_width/2, badge_y, str(i+1),
                ha='center', va='center', fontsize=14, fontweight='bold',
                color=color, family='monospace')

        # Title
        ax.text(x + pillar_width/2, pillar_y + pillar_h - 1.4, title,
                ha='center', va='center', fontsize=10.5, fontweight='bold',
                color=color, family='monospace', linespacing=1.3)

        # Description
        ax.text(x + pillar_width/2, pillar_y + pillar_h - 2.9, desc,
                ha='center', va='center', fontsize=9, color=text_primary,
                family='monospace', linespacing=1.6)

        # Divider
        div_y = pillar_y + 1.9
        ax.plot([x + 0.15, x + pillar_width - 0.15], [div_y, div_y],
                color=border, linewidth=0.8)

        # Detail/example
        ax.text(x + pillar_width/2, pillar_y + 1.0, detail,
                ha='center', va='center', fontsize=8, color=text_secondary,
                family='monospace', linespacing=1.5, fontstyle='italic')

    # Tagline
    ax.text(8, 0.3, 'Rules are suggestions.  Infrastructure is law.',
            ha='center', fontsize=13, color=text_secondary, family='monospace',
            fontstyle='italic')

    plt.tight_layout(pad=0.3)
    plt.savefig('assets/pact-pillars.png', dpi=180,
                facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close()
    print("Saved: assets/pact-pillars.png")


if __name__ == '__main__':
    draw_compound_intelligence()
    draw_pillars()
