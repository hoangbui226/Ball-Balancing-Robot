"""Show the ESP32-CAM picture from USB serial, with RGB and camera sliders.

Close the Arduino Serial Monitor first, or the port is busy.

    python vision/calibration/view.py --port COM7

Move the sliders until the mask is white only on the ball.
Click Save under the sliders. It changes to saved.
q closes the camera window.
"""

from __future__ import annotations

import argparse
import time
import tkinter as tk
from pathlib import Path

import cv2
import numpy as np
import serial


MAGIC = b"##FRAME "
SETTINGS = Path(__file__).with_name("ball_settings.txt")

PALE_ORANGE = {
    "H min": 5,
    "H max": 25,
    "S min": 40,
    "S max": 255,
    "V min": 60,
    "V max": 255,
    "min radius": 6,
    "max radius": 60,
}

BLACK_BALL = {
    "H min": 0,
    "H max": 179,
    "S min": 0,
    "S max": 255,
    "V min": 0,
    "V max": 50,
    "min radius": 6,
    "max radius": 60,
}

DEFAULTS = {
    "h_min": 5,
    "h_max": 25,
    "s_min": 40,
    "s_max": 255,
    "v_min": 60,
    "v_max": 255,
    "brightness": 0,
    "contrast": 0,
    "saturation": 0,
    "exposure": 200,
    "gain": 0,
    "whitebal": 1,
    "auto_exposure": 1,
    "light": 0,
    "min_radius": 6,
    "max_radius": 60,
}


def parse_args():
    p = argparse.ArgumentParser(description="ESP32-CAM calibration: picture and HSV sliders")
    p.add_argument("--port", required=True, help="COM port from Arduino Tools, Port")
    p.add_argument("--baud", type=int, default=1500000)
    return p.parse_args()


def load_settings():
    values = dict(DEFAULTS)
    if not SETTINGS.exists():
        return values
    for line in SETTINGS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, raw = line.partition(" ")
        if key in values:
            values[key] = int(raw)
    return values


def save_settings(values):
    lines = ["# locked ball color and camera settings", ""]
    for key in DEFAULTS:
        lines.append(f"{key} {values[key]}")
    SETTINGS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_windows():
    cv2.namedWindow("ball rgb")
    cv2.namedWindow("mask")


def make_controls(settings, ui):
    root = tk.Tk()
    root.title("controls")
    root.resizable(False, False)
    bars = [
        ("H min", settings["h_min"], 179),
        ("H max", settings["h_max"], 179),
        ("S min", settings["s_min"], 255),
        ("S max", settings["s_max"], 255),
        ("V min", settings["v_min"], 255),
        ("V max", settings["v_max"], 255),
        ("brightness", settings["brightness"] + 2, 4),
        ("contrast", settings["contrast"] + 2, 4),
        ("saturation", settings["saturation"] + 2, 4),
        ("exposure", settings["exposure"], 1200),
        ("gain", settings["gain"], 30),
        ("white balance", settings["whitebal"], 1),
        ("light", settings["light"], 4),
        ("auto exposure", settings["auto_exposure"], 1),
        ("min radius", settings["min_radius"], 160),
        ("max radius", settings["max_radius"], 160),
    ]
    variables = {}
    for index, (name, value, limit) in enumerate(bars):
        row, column = divmod(index, 2)
        cell = tk.Frame(root)
        cell.grid(row=row, column=column, padx=4, pady=0, sticky="w")
        tk.Label(cell, text=name, width=14, anchor="w").pack(side="left")
        variable = tk.IntVar(value=int(np.clip(value, 0, limit)))
        tk.Scale(
            cell,
            from_=0,
            to=limit,
            orient=tk.HORIZONTAL,
            variable=variable,
            length=120,
            sliderlength=12,
            showvalue=True,
        ).pack(side="left")
        variables[name] = variable

    def use(preset):
        for name, value in preset.items():
            variables[name].set(value)

    actions = tk.Frame(root)
    actions.grid(row=(len(bars) + 1) // 2, column=0, columnspan=2, pady=4)
    tk.Button(actions, text="Orange", width=8, command=lambda: use(PALE_ORANGE)).pack(side="left", padx=4)
    tk.Button(actions, text="Black", width=8, command=lambda: use(BLACK_BALL)).pack(side="left", padx=4)
    button = tk.Button(actions, text="Save", width=8, command=lambda: ui.__setitem__("save", True))
    button.pack(side="left", padx=4)
    return root, variables, button


def read_bars(variables):
    def pos(name):
        return variables[name].get()

    h_min, h_max = sorted((pos("H min"), pos("H max")))
    s_min, s_max = sorted((pos("S min"), pos("S max")))
    v_min, v_max = sorted((pos("V min"), pos("V max")))
    return {
        "h_min": h_min,
        "h_max": h_max,
        "s_min": s_min,
        "s_max": s_max,
        "v_min": v_min,
        "v_max": v_max,
        "brightness": pos("brightness") - 2,
        "contrast": pos("contrast") - 2,
        "saturation": pos("saturation") - 2,
        "exposure": pos("exposure"),
        "gain": pos("gain"),
        "whitebal": pos("white balance"),
        "auto_exposure": pos("auto exposure"),
        "light": pos("light"),
        "min_radius": max(1, pos("min radius")),
        "max_radius": max(pos("min radius") + 1, pos("max radius")),
    }


def camera_command(values):
    return (
        f"S {values['brightness']} {values['contrast']} {values['saturation']} "
        f"{values['exposure']} {values['gain']} {values['whitebal']} "
        f"{values['auto_exposure']} {values['light']}\n"
    ).encode()


def take_frame(buf: bytearray):
    while True:
        start = buf.find(MAGIC)
        if start < 0:
            if len(buf) > 32:
                del buf[:-32]
            return None
        if start > 0:
            del buf[:start]

        nl = buf.find(b"\n", len(MAGIC))
        if nl < 0:
            return None

        try:
            length, crc = [int(x) for x in buf[len(MAGIC) : nl].split()]
        except ValueError:
            del buf[: len(MAGIC)]
            continue

        if not 500 <= length <= 80000:
            del buf[: len(MAGIC)]
            continue

        payload = nl + 1
        if len(buf) < payload + length:
            return None

        jpg = bytes(buf[payload : payload + length])
        del buf[: payload + length]
        if jpg[:2] != b"\xff\xd8" or jpg[-2:] != b"\xff\xd9":
            continue
        if sum(jpg) & 0xFFFFFFFF != crc:
            continue

        img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        return img


def find_ball(mask, min_r, max_r):
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.erode(mask, kernel, iterations=1)
    mask = cv2.dilate(mask, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 20:
            continue
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        if radius < min_r or radius > max_r:
            continue
        peri = cv2.arcLength(contour, True)
        if peri == 0:
            continue
        circularity = (4 * np.pi * area) / (peri * peri)
        if circularity < 0.25:
            continue
        if area > best_area:
            best_area = area
            best = (int(cx), int(cy), int(radius))
    return best, mask


def center_stats(img):
    height, width = img.shape[:2]
    box = 40 if width >= 320 else 20
    x0 = width // 2 - box // 2
    y0 = height // 2 - box // 2
    patch = img[y0 : y0 + box, x0 : x0 + box]
    blue = patch[:, :, 0]
    green = patch[:, :, 1]
    red = patch[:, :, 2]
    stats = (
        int(red.mean()),
        int(green.mean()),
        int(blue.mean()),
        int(red.min()),
        int(red.max()),
        int(green.min()),
        int(green.max()),
        int(blue.min()),
        int(blue.max()),
    )
    return stats, x0, y0, box


def main():
    args = parse_args()
    settings = load_settings()
    ser = serial.Serial(args.port, args.baud, timeout=0)
    ser.reset_input_buffer()
    ui = {"save": False, "saved_until": 0.0}
    make_windows()
    controls, variables, save_button = make_controls(settings, ui)
    ser.write(camera_command(read_bars(variables)))

    buf = bytearray()
    sent = None
    frame_count = 0
    fps_mark = time.perf_counter()
    fps_text = "0 fps"
    waiting = np.zeros((480, 640, 3), np.uint8)
    cv2.putText(waiting, "waiting for camera", (40, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imshow("ball rgb", waiting)

    try:
        while True:
            values = read_bars(variables)
            command = camera_command(values)
            if command != sent:
                ser.write(command)
                sent = command

            waiting_bytes = ser.in_waiting
            if waiting_bytes:
                buf.extend(ser.read(waiting_bytes))
            latest = None
            while True:
                got = take_frame(buf)
                if got is None:
                    break
                latest = got
            if latest is not None:
                img = latest
                (r, g, b, r0, r1, g0, g1, b0, b1), box_x, box_y, box = center_stats(img)
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                lower = np.array([values["h_min"], values["s_min"], values["v_min"]], np.uint8)
                upper = np.array([values["h_max"], values["s_max"], values["v_max"]], np.uint8)
                mask = cv2.inRange(hsv, lower, upper)
                hit, mask = find_ball(mask, values["min_radius"], values["max_radius"])
                show = cv2.resize(img, (img.shape[1] * 2, img.shape[0] * 2), interpolation=cv2.INTER_LINEAR)
                cv2.rectangle(
                    show,
                    (box_x * 2, box_y * 2),
                    ((box_x + box) * 2, (box_y + box) * 2),
                    (255, 0, 255),
                    1,
                )
                if hit:
                    x, y, radius = hit
                    center = (int(x * show.shape[1] / img.shape[1]), int(y * show.shape[0] / img.shape[0]))
                    cv2.circle(show, center, max(1, int(radius * show.shape[1] / img.shape[1])), (0, 255, 0), 2)
                    cv2.drawMarker(show, center, (0, 0, 255), cv2.MARKER_CROSS, 16, 2)
                    found = f"ball {x} {y}"
                else:
                    found = "no ball"
                frame_count += 1
                now = time.perf_counter()
                if now - fps_mark >= 0.5:
                    fps_text = f"{frame_count / (now - fps_mark):.0f} fps"
                    frame_count = 0
                    fps_mark = now
                label = f"avg {r} {g} {b}   red {r0}-{r1}  green {g0}-{g1}  blue {b0}-{b1}"
                cv2.putText(show, found, (8, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(show, label, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(show, fps_text, (show.shape[1] - 90, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(show, "q quit", (8, show.shape[0] - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.imshow("ball rgb", show)
                cv2.imshow("mask", cv2.resize(mask, (640, 480), interpolation=cv2.INTER_NEAREST))

            save_button.config(text="saved" if time.time() < ui["saved_until"] else "Save")
            try:
                controls.update()
            except tk.TclError:
                break

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("s") or ui["save"]:
                ui["save"] = False
                values = read_bars(variables)
                save_settings(values)
                ui["saved_until"] = time.time() + 2.0
                print("saved", SETTINGS)
                print(values)
    finally:
        ser.close()
        cv2.destroyAllWindows()
        try:
            controls.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    main()
