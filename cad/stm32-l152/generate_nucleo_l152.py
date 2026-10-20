"""Generate a NUCLEO-L152RE (Nucleo-64 / MB1136) mock-up STL for Fusion 360."""

from __future__ import annotations

import math
import struct
from pathlib import Path

# ST UM1724 Fig. 5: Nucleo-64 outline. Same PCB as NUCLEO-F411RE / L152RE.
BOARD_X = 82.5
BOARD_Y = 70.0
BOARD_Z = 1.6

# Arduino Uno R3 board, used for the compatible hole pattern.
ARDUINO_X = 68.58
ARDUINO_Y = 53.34
HOLE_R = 3.2 / 2.0

# ST-LINK strip on the USB (X=0) side; Arduino area on the right, centered in Y.
AX = BOARD_X - ARDUINO_X
AY = (BOARD_Y - ARDUINO_Y) / 2.0

# Hole centres relative to Arduino origin (USB-left, bottom-left).
ARDUINO_HOLES = (
    (15.24, 50.80),
    (66.04, 35.56),
    (66.04, 7.62),
    (13.97, 2.54),
)


def _n(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return (nx / length, ny / length, nz / length)


def add_tri(tris, a, b, c):
    tris.append((_n(a, b, c), a, b, c))


def add_quad(tris, a, b, c, d):
    add_tri(tris, a, b, c)
    add_tri(tris, a, c, d)


def add_box(tris, x, y, z, dx, dy, dz):
    x0, y0, z0 = x, y, z
    x1, y1, z1 = x + dx, y + dy, z + dz
    p = {
        0: (x0, y0, z0),
        1: (x1, y0, z0),
        2: (x1, y1, z0),
        3: (x0, y1, z0),
        4: (x0, y0, z1),
        5: (x1, y0, z1),
        6: (x1, y1, z1),
        7: (x0, y1, z1),
    }
    add_quad(tris, p[4], p[5], p[6], p[7])  # top
    add_quad(tris, p[0], p[3], p[2], p[1])  # bottom
    add_quad(tris, p[0], p[1], p[5], p[4])  # front
    add_quad(tris, p[3], p[7], p[6], p[2])  # back
    add_quad(tris, p[0], p[4], p[7], p[3])  # left
    add_quad(tris, p[1], p[2], p[6], p[5])  # right


def add_cyl_shell(tris, cx, cy, z0, z1, radius, segs=24, inward=False):
    for i in range(segs):
        a0 = 2 * math.pi * i / segs
        a1 = 2 * math.pi * (i + 1) / segs
        p0 = (cx + radius * math.cos(a0), cy + radius * math.sin(a0), z0)
        p1 = (cx + radius * math.cos(a1), cy + radius * math.sin(a1), z0)
        p2 = (cx + radius * math.cos(a1), cy + radius * math.sin(a1), z1)
        p3 = (cx + radius * math.cos(a0), cy + radius * math.sin(a0), z1)
        if inward:
            add_quad(tris, p0, p3, p2, p1)
        else:
            add_quad(tris, p0, p1, p2, p3)


def in_hole(x, y, holes, radius):
    r2 = radius * radius
    return any((x - hx) ** 2 + (y - hy) ** 2 <= r2 for hx, hy in holes)


def add_pcb(tris, holes):
    nx, ny = 83, 70
    dx, dy = BOARD_X / nx, BOARD_Y / ny
    z0, z1 = 0.0, BOARD_Z
    skip_r = HOLE_R + 0.15
    for i in range(nx):
        for j in range(ny):
            x0, y0 = i * dx, j * dy
            x1, y1 = x0 + dx, y0 + dy
            if in_hole((x0 + x1) / 2.0, (y0 + y1) / 2.0, holes, skip_r):
                continue
            add_quad(
                tris,
                (x0, y0, z1),
                (x1, y0, z1),
                (x1, y1, z1),
                (x0, y1, z1),
            )
            add_quad(
                tris,
                (x0, y0, z0),
                (x0, y1, z0),
                (x1, y1, z0),
                (x1, y0, z0),
            )
    add_quad(
        tris,
        (0, 0, z0),
        (BOARD_X, 0, z0),
        (BOARD_X, 0, z1),
        (0, 0, z1),
    )
    add_quad(
        tris,
        (BOARD_X, 0, z0),
        (BOARD_X, BOARD_Y, z0),
        (BOARD_X, BOARD_Y, z1),
        (BOARD_X, 0, z1),
    )
    add_quad(
        tris,
        (BOARD_X, BOARD_Y, z0),
        (0, BOARD_Y, z0),
        (0, BOARD_Y, z1),
        (BOARD_X, BOARD_Y, z1),
    )
    add_quad(
        tris,
        (0, BOARD_Y, z0),
        (0, 0, z0),
        (0, 0, z1),
        (0, BOARD_Y, z1),
    )
    for hx, hy in holes:
        add_cyl_shell(tris, hx, hy, z0, z1, HOLE_R, segs=28, inward=True)


def add_header_block(tris, x, y, nx, ny, height=8.5, pitch=2.54):
    add_box(tris, x, y, BOARD_Z, nx * pitch, ny * pitch, height)


def add_parts(tris):
    # Mini-USB (older Nucleo-64 / L152RE), overhangs the left edge.
    add_box(tris, -1.2, 40.5, BOARD_Z, 9.9, 7.7, 4.0)
    # ST-LINK MCU
    add_box(tris, 8.0, 44.0, BOARD_Z, 7.0, 7.0, 1.2)
    # Reset + user buttons
    add_box(tris, 6.5, 18.0, BOARD_Z, 6.0, 6.0, 3.0)
    add_box(tris, 6.5, 28.0, BOARD_Z, 6.0, 6.0, 3.0)
    # SWD header CN4
    add_header_block(tris, 16.0, 48.0, 2, 3, height=6.0)
    # STM32L152RET6 LQFP64
    add_box(tris, 43.0, 30.0, BOARD_Z, 10.0, 10.0, 1.4)
    # 8 MHz crystal
    add_box(tris, 38.0, 26.0, BOARD_Z, 5.0, 3.2, 1.0)
    # LD2 user LED
    add_box(tris, 55.0, 22.0, BOARD_Z, 1.6, 0.8, 0.8)
    # ST morpho CN7 (bottom) and CN10 (top), 2x19
    add_header_block(tris, 24.0, 1.1, 19, 2)
    add_header_block(tris, 24.0, BOARD_Y - 1.1 - 2 * 2.54, 19, 2)
    # Arduino headers relative to Arduino origin
    add_header_block(tris, AX + 7.62, AY + 50.8 - 2.54, 8, 1)  # power CN6
    add_header_block(tris, AX + 35.56, AY + 50.8 - 2.54, 10, 1)  # digital CN5
    add_header_block(tris, AX + 62.25, AY + 7.62, 1, 8)  # digital CN9
    add_header_block(tris, AX + 62.25, AY + 30.48, 1, 6)  # analog CN8


def write_stl(path: Path, tris):
    header = b"NUCLEO-L152RE Nucleo-64 MB1136 mock-up"[:80].ljust(80, b"\0")
    body = [header, struct.pack("<I", len(tris))]
    for n, a, b, c in tris:
        body.append(
            struct.pack(
                "<12fH",
                n[0], n[1], n[2],
                a[0], a[1], a[2],
                b[0], b[1], b[2],
                c[0], c[1], c[2],
                0,
            )
        )
    path.write_bytes(b"".join(body))


def main():
    holes = [(AX + hx, AY + hy) for hx, hy in ARDUINO_HOLES]
    tris = []
    add_pcb(tris, holes)
    add_parts(tris)
    out = Path(__file__).with_name("NUCLEO-L152RE.stl")
    write_stl(out, tris)
    print(f"Wrote {out} ({len(tris)} triangles)")


if __name__ == "__main__":
    main()
