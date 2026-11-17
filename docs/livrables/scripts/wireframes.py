"""Draws the low-fidelity wireframes (sketch style, grayscale) used in part 1 of the report.

Usage: python wireframes.py <out_dir>
"""
import math
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen  # noqa: E402

app = QGuiApplication(sys.argv)
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
rng = random.Random(3)
INK = QColor("#222222")
GREY = QColor("#d9d9d9")
LIGHT = QColor("#f1f1f1")
SCALE = 2


def jitter(v: float, a: float = 1.6) -> float:
    return v + rng.uniform(-a, a)


def sketch_line(p: QPainter, x1, y1, x2, y2, width=2.0):
    """A slightly wobbly line drawn twice, like a pen sketch."""
    for _ in range(2):
        path = QPainterPath(QPointF(jitter(x1), jitter(y1)))
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        path.quadTo(QPointF(jitter(mx, 2.5), jitter(my, 2.5)), QPointF(jitter(x2), jitter(y2)))
        pen = QPen(INK, width * rng.uniform(0.7, 1.0))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawPath(path)


def box(p, x, y, w, h, fill=None, width=2.0):
    if fill:
        p.fillRect(QRectF(x + 3, y + 3, w - 6, h - 6), fill)
    sketch_line(p, x, y, x + w, y, width)
    sketch_line(p, x + w, y, x + w, y + h, width)
    sketch_line(p, x + w, y + h, x, y + h, width)
    sketch_line(p, x, y + h, x, y, width)


def text(p, x, y, s, size=13, bold=False, align=Qt.AlignmentFlag.AlignLeft, w=400):
    f = QFont("Noto Sans")
    f.setPixelSize(size)
    f.setBold(bold)
    p.setFont(f)
    p.setPen(INK)
    p.drawText(QRectF(x, y, w, size * 1.6), align | Qt.AlignmentFlag.AlignVCenter, s)


def scribble(p, x, y, w, lines=2, gap=12):
    """Placeholder text lines."""
    for i in range(lines):
        length = w * rng.uniform(0.55, 0.95)
        sketch_line(p, x, y + i * gap, x + length, y + i * gap, 1.2)


def graph(p, x, y, w, h, threshold=True):
    sketch_line(p, x, y, x, y + h, 1.5)
    sketch_line(p, x, y + h, x + w, y + h, 1.5)
    pts = [QPointF(x + i * w / 24, y + h * (0.3 + 0.18 * math.sin(i * 1.3) + rng.uniform(-0.06, 0.06)))
           for i in range(25)]
    pts[18] = QPointF(pts[18].x(), y + h * 0.88)
    path = QPainterPath(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    p.setPen(QPen(INK, 1.8))
    p.drawPath(path)
    if threshold:
        p.setPen(QPen(INK, 1.4, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(x, y + h * 0.78), QPointF(x + w, y + h * 0.78))
        text(p, x + w - 70, y + h * 0.78 - 20, "seuil 30 cm", 11)


def gauge(p, cx, cy, r, label):
    p.setPen(QPen(INK, 2))
    p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 160 * 16, -140 * 16)
    p.setPen(QPen(INK, 5))
    p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 160 * 16, -70 * 16)
    text(p, cx - 60, cy - 8, label, 11, align=Qt.AlignmentFlag.AlignHCenter, w=120)


def button(p, x, y, w, h, label, filled=False):
    box(p, x, y, w, h, GREY if filled else None, 1.6)
    text(p, x, y + (h - 20) / 2, label, 12, bold=True, align=Qt.AlignmentFlag.AlignHCenter, w=w)


def note(p, x, y, n, s):
    """Numbered annotation bubble."""
    p.setPen(QPen(INK, 1.6))
    p.setBrush(QColor("white"))
    p.drawEllipse(QPointF(x, y), 11, 11)
    p.setBrush(Qt.BrushStyle.NoBrush)
    text(p, x - 11, y - 10, str(n), 12, True, Qt.AlignmentFlag.AlignHCenter, 22)
    if s:
        text(p, x + 16, y - 10, s, 12, w=380)


def canvas(w, h):
    img = QImage(w * SCALE, h * SCALE, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(SCALE, SCALE)
    return img, p


# ------------------------------------------------ 1. main screen (Qt / web desktop)
img, p = canvas(820, 500)
box(p, 10, 10, 800, 480, width=2.6)
box(p, 25, 25, 140, 270, LIGHT)
text(p, 25, 35, "10:42:15", 20, True, Qt.AlignmentFlag.AlignHCenter, 140)
text(p, 25, 120, "STATUT :", 16, True, Qt.AlignmentFlag.AlignHCenter, 140)
text(p, 25, 150, "ARMÉ", 22, True, Qt.AlignmentFlag.AlignHCenter, 140)
text(p, 25, 250, "◇ SÉCURISÉ", 14, True, Qt.AlignmentFlag.AlignHCenter, 140)
box(p, 175, 25, 135, 175)
text(p, 185, 30, "Détecteur PIR", 12, True)
text(p, 175, 75, "● RAS", 20, True, Qt.AlignmentFlag.AlignHCenter, 135)
scribble(p, 195, 130, 95, 2)
box(p, 320, 25, 295, 175)
text(p, 330, 30, "Distance ultrason", 12, True)
text(p, 520, 30, "142 cm", 16, True)
graph(p, 340, 65, 255, 115)
box(p, 175, 210, 260, 85)
text(p, 185, 215, "Ambiance (DHT)", 12, True)
gauge(p, 245, 275, 35, "22 °C")
gauge(p, 365, 275, 35, "45 %")
box(p, 445, 210, 170, 85)
text(p, 455, 215, "Commandes", 12, True)
button(p, 455, 250, 70, 28, "Relais")
button(p, 535, 250, 70, 28, "Buzzer")
box(p, 625, 25, 170, 270, LIGHT)
text(p, 635, 30, "Authentification", 12, True)
text(p, 635, 75, "Mot de passe :", 12)
box(p, 635, 100, 150, 30)
text(p, 645, 105, "••••", 14)
button(p, 635, 145, 150, 36, "ARMER", True)
scribble(p, 640, 255, 140, 2, 10)
box(p, 25, 305, 770, 170)
text(p, 35, 310, "Journal de sécurité (SQLite)", 12, True)
button(p, 560, 312, 105, 26, "Rafraîchir")
button(p, 675, 312, 110, 26, "Export CSV")
for i, row in enumerate(["Horodatage", "", "", "", ""]):
    y = 350 + i * 24
    sketch_line(p, 35, y + 22, 785, y + 22, 1.0)
    if i == 0:
        text(p, 40, y, "Horodatage      Événement        Détails                      Gravité", 12, True, w=740)
    else:
        scribble(p, 45, y + 10, 680, 1)
for x, y, n in ((160, 22, 1), (305, 22, 2), (610, 22, 3), (430, 207, 4), (610, 207, 5), (790, 22, 6), (790, 302, 7)):
    note(p, x, y, n, "")
p.end()
img.save(str(out / "wf_principal.png"))

# ------------------------------------------------ 2. expanded tile
img, p = canvas(820, 440)
box(p, 10, 10, 800, 420, width=2.6)
button(p, 25, 25, 100, 34, "← Retour")
text(p, 140, 28, "Distance ultrason", 18, True)
for i, label in enumerate(["Actuel", "Min", "Moy.", "Max", "Seuil"]):
    box(p, 25 + i * 156, 75, 146, 55, LIGHT)
    text(p, 35 + i * 156, 80, label, 11)
    scribble(p, 35 + i * 156, 115, 70, 1)
box(p, 25, 140, 770, 275)
graph(p, 55, 160, 715, 225)
note(p, 128, 26, 1, "")
note(p, 795, 72, 2, "")
p.end()
img.save(str(out / "wf_agrandie.png"))

# ------------------------------------------------ 3. phone
img, p = canvas(300, 600)
box(p, 20, 10, 260, 580, width=2.8)
sketch_line(p, 120, 25, 180, 25, 3)
y = 45
for title, h, extra in (("Statut : ARMÉ", 60, None), ("Authentification", 95, "auth"),
                        ("Détecteur PIR", 70, None), ("Distance ultrason", 120, "graph"),
                        ("Journal", 120, "log")):
    box(p, 35, y, 230, h, LIGHT if title.startswith("Statut") else None)
    text(p, 45, y + 4, title, 12, True)
    if extra == "auth":
        box(p, 45, y + 30, 210, 24)
        button(p, 45, y + 60, 210, 26, "ARMER", True)
    elif extra == "graph":
        graph(p, 50, y + 30, 200, 75, threshold=False)
    elif extra == "log":
        for i in range(4):
            scribble(p, 45, y + 35 + i * 20, 200, 1)
    else:
        scribble(p, 50, y + 35, 180, 2)
    y += h + 10
box(p, 70, 565, 160, 18)
text(p, 70, 563, "● en direct / ⚠ hors ligne", 10, align=Qt.AlignmentFlag.AlignHCenter, w=160)
p.end()
img.save(str(out / "wf_mobile.png"))
print("wireframes written to", out)
