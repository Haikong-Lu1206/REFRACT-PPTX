"""Rebuild the original README diagrams. Standard library only; no external assets."""

from __future__ import annotations

from html import escape
from pathlib import Path

INK = "#14243C"
MUTED = "#60718A"
TEAL = "#087F8C"
BLUE = "#3466CF"
ORANGE = "#BA651D"
ROOT = Path(__file__).resolve().parents[1]


class Diagram:
    def __init__(self, title: str, subtitle: str, height: int = 820):
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="{height}" '
            f'viewBox="0 0 1400 {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title><desc id="desc">{escape(subtitle)}</desc>',
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            '<path d="M 0 0 L 10 5 L 0 10 z" fill="#91A3BB"/></marker></defs>',
            '<rect width="1400" height="100%" rx="24" fill="#F5F8FC"/>',
        ]
        self.text(48, 52, "REFRACT / FIELD GUIDE", 16, TEAL, 700, spacing="2")
        self.text(48, 105, title, 38, INK, 700)
        self.text(48, 143, subtitle, 21, MUTED)
        self.line(48, 170, 1352, 170, "#DAE2EE")

    def text(self, x, y, content, size=23, color=INK, weight=400, spacing="0"):
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'letter-spacing="{spacing}">{escape(content)}</text>'
        )

    def rect(self, x, y, w, h, fill="#FFFFFF", stroke="#DFE6F0", radius=16):
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
            f'rx="{radius}" fill="{fill}" stroke="{stroke}"/>'
        )

    def line(self, x1, y1, x2, y2, color="#91A3BB", arrow=False):
        marker = ' marker-end="url(#arrow)"' if arrow else ""
        self.parts.append(
            f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" '
            f'stroke-width="2" fill="none"{marker}/>'
        )

    def card(self, x, y, w, h, number, title, lines, color=TEAL):
        self.rect(x, y, w, h)
        self.rect(x + 20, y + 20, 42, 34, color, color, 8)
        self.text(x + 29, y + 44, number, 18, "#FFFFFF", 700)
        self.text(x + 20, y + 94, title, 25, INK, 700)
        for index, content in enumerate(lines):
            self.text(x + 20, y + 132 + 29 * index, content, 19, MUTED)

    def save(self, name):
        folder = ROOT / "docs" / "images"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text("\n".join(self.parts + ["</svg>"]) + "\n", encoding="utf-8")


def workflow():
    d = Diagram(
        "From a presentation to a task batch",
        "Your agent makes the design decisions. REFRACT turns them into testable artifacts.",
        900,
    )
    steps = [
        (
            "01",
            "Prepare",
            ["PPTX + reference PDF", "Record source and license", "Export PDF if needed"],
            TEAL,
        ),
        (
            "02",
            "Design with an agent",
            ["Read the actual slides", "Choose meaningful repairs", "Write proposal.json"],
            BLUE,
        ),
        (
            "03",
            "Build + test",
            ["Compile, mutate, evaluate", "Check init and oracle", "Run built-in red-team"],
            TEAL,
        ),
        (
            "04",
            "Review + release",
            ["Blind review + editor test", "Export public / hidden files", "Canary, then scale"],
            ORANGE,
        ),
    ]
    for index, (number, title, lines, color) in enumerate(steps):
        x = 48 + index * 332
        d.card(x, 210, 308, 237, number, title, lines, color)
        if index < 3:
            d.line(x + 312, 325, x + 328, 325, arrow=True)
    d.rect(48, 482, 1304, 145, "#EAF1FD", "#CDDCF8")
    d.text(72, 519, "A WORKSPACE YOU CAN RESUME", 16, BLUE, 700, spacing="1.5")
    for x, label, detail in [
        (72, "designs/", "Inputs, inventory, prompt, proposal"),
        (525, "runs/batch/", "Bundles, state, stable task IDs"),
        (986, "configs/", "Runner and release policy"),
    ]:
        d.text(x, 557, label, 25, INK, 700)
        d.text(x, 591, detail, 18, MUTED)
    d.rect(48, 661, 1304, 173)
    d.text(72, 702, "START SMALL. INSPECT REAL OUTPUTS. THEN ADD WORKERS.", 19, TEAL, 700)
    d.text(72, 744, "init-workspace  →  prepare-task  →  workspace-status  →  build-workspace", 23)
    d.text(
        72, 788, "Model access and target-editor validation stay in your own workflow.", 21, MUTED
    )
    d.save("workflow.svg")


def architecture():
    d = Diagram(
        "Creative design. Deterministic execution.",
        "A declarative contract connects the design agent, factory and independent verifier.",
        880,
    )
    d.card(
        48,
        207,
        382,
        244,
        "A",
        "Design agent",
        ["Inspects each deck", "Chooses recoverable mutations", "States evidence and equivalents"],
        BLUE,
    )
    d.card(
        507,
        207,
        382,
        244,
        "B",
        "REFRACT factory",
        ["Validates the proposal", "Applies registered OOXML edits", "Freezes evaluator contracts"],
        TEAL,
    )
    d.card(
        966,
        207,
        386,
        244,
        "C",
        "Quality checks",
        [
            "Init / oracle / isolated repair",
            "Blind review + editor roundtrip",
            "Production gate before export",
        ],
        ORANGE,
    )
    d.line(439, 315, 494, 315, arrow=True)
    d.line(898, 315, 953, 315, arrow=True)
    d.text(438, 293, "JSON", 15, BLUE, 700)
    d.text(896, 293, "TASK", 15, TEAL, 700)
    d.line(700, 451, 700, 489)
    d.line(366, 489, 1030, 489)
    d.line(366, 489, 366, 516, arrow=True)
    d.line(1030, 489, 1030, 516, arrow=True)
    d.rect(48, 526, 636, 213, "#EAF6F4", "#C5E5E1")
    d.text(74, 569, "SOLVER-VISIBLE INPUTS", 18, TEAL, 700, spacing="1")
    d.text(74, 612, "Instruction · Init PPTX · Reference PDF", 25, INK, 700)
    d.text(74, 650, "Materials needed to reconstruct the editable deck", 21, MUTED)
    d.text(74, 699, "Published to the agent environment", 18, TEAL)
    d.rect(716, 526, 636, 213, "#EEF1F9", "#D2D9EA")
    d.text(742, 569, "VERIFIER-ONLY STATE", 18, BLUE, 700, spacing="1")
    d.text(742, 612, "Plan · Init inventory · Pinned runtime", 25, INK, 700)
    d.text(742, 650, "Collected final file is evaluated independently", 21, MUTED)
    d.text(742, 699, "Kept outside public materials", 18, BLUE)
    d.text(
        48,
        804,
        "Task content, runner configuration and review evidence remain separate.",
        23,
        MUTED,
    )
    d.save("design-boundaries.svg")


def evaluation():
    d = Diagram(
        "Reward real repairs, not an unchanged baseline",
        "An actual synthetic example: two equally weighted title-position repairs.",
        890,
    )
    for i, (label, title_pos, score, color) in enumerate(
        [
            ("Untouched init", (False, False), "0.00", MUTED),
            ("One title repaired", (True, False), "0.50", BLUE),
            ("Both titles repaired", (True, True), "1.00", TEAL),
        ]
    ):
        x = 48 + i * 444
        d.rect(x, 209, 416, 303)
        d.text(x + 22, 252, label, 25, INK, 700)
        for j, correct in enumerate(title_pos):
            sx, sy = x + 22 + j * 190, 278
            d.rect(sx, sy, 178, 118, "#F7F9FD", "#D7DFEA", 6)
            tx, ty = (sx + 17, sy + 26) if correct else (sx + 50, sy + 47)
            d.rect(tx, ty, 92, 10, TEAL if correct else "#B3BECD", "none", 3)
            for row in range(3):
                d.rect(sx + 17, sy + 68 + 11 * row, 133 - row * 15, 4, "#CFD8E6", "none", 2)
        d.text(x + 22, 477, score, 49, color, 700)
        d.text(x + 178, 472, "measured score", 19, MUTED)
    d.text(
        48,
        551,
        "Slide drawings are schematic. Scores come from real generated PPTX candidates.",
        18,
        MUTED,
    )
    d.rect(48, 581, 1304, 116, "#EAF1FD", "#CDDCF8")
    d.text(74, 623, "NORMALIZED COMPONENT PROGRESS", 16, BLUE, 700, spacing="1")
    d.text(
        74, 665, "clamp((candidate similarity − init similarity) / (1 − init similarity), 0, 1)", 27
    )
    d.text(48, 748, "Equivalent editable objects", 23, TEAL, 700)
    d.text(48, 783, "Semantic matching, not original IDs", 19, MUTED)
    d.text(505, 748, "Graded preservation", 23, TEAL, 700)
    d.text(505, 783, "Unrelated damage reduces credit", 19, MUTED)
    d.text(953, 748, "Catastrophic gates", 23, ORANGE, 700)
    d.text(953, 783, "Slide count, order, size, full-page paste", 18, MUTED)
    d.text(
        48,
        840,
        "This smoke test proves the example, not difficulty or compatibility with every editor.",
        18,
        MUTED,
    )
    d.save("evaluation.svg")


if __name__ == "__main__":
    workflow()
    architecture()
    evaluation()
