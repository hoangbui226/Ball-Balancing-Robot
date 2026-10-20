"""Practice ball tracking with a PC webcam (same idea as references/camera.py).

The ESP32 DOIT DevKit cannot run OpenCV and has no camera. Use this on the PC first.
Later the ESP32-CAM will send the same "x y" numbers over UART.

Keys:
  q  quit
  s  save current HSV / threshold to the console
  c  cycle camera index if the wrong webcam opens
"""

from __future__ import annotations

import argparse
import time

import cv2
import numpy as np


PROCESS_WIDTH = 320  # close to ESP32-CAM QVGA width; owner used 200 px


def parse_args():
    p = argparse.ArgumentParser(description="Track a ball with the PC webcam")
    p.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    p.add_argument(
        "--mode",
        choices=("color", "dark"),
        default="color",
        help="color = HSV (orange/pink ball). dark = owner's black-blob method",
    )
    return p.parse_args()


def make_windows(mode: str):
    cv2.namedWindow("frame")
    cv2.namedWindow("mask")
    cv2.namedWindow("controls")
    cv2.resizeWindow("controls", 420, 280)
    if mode == "color":
        # Orange ping-pong defaults; move sliders until only the ball is white on "mask"
        cv2.createTrackbar("H min", "controls", 5, 179, lambda _: None)
        cv2.createTrackbar("H max", "controls", 25, 179, lambda _: None)
        cv2.createTrackbar("S min", "controls", 80, 255, lambda _: None)
        cv2.createTrackbar("S max", "controls", 255, 255, lambda _: None)
        cv2.createTrackbar("V min", "controls", 80, 255, lambda _: None)
        cv2.createTrackbar("V max", "controls", 255, 255, lambda _: None)
    else:
        cv2.createTrackbar("gray max", "controls", 60, 255, lambda _: None)
        cv2.createTrackbar("H max", "controls", 180, 179, lambda _: None)
        cv2.createTrackbar("S max", "controls", 255, 255, lambda _: None)
        cv2.createTrackbar("V max", "controls", 50, 255, lambda _: None)
    cv2.createTrackbar("min radius", "controls", 8, 80, lambda _: None)
    cv2.createTrackbar("max radius", "controls", 80, 160, lambda _: None)


def read_bars(mode: str):
    min_r = max(1, cv2.getTrackbarPos("min radius", "controls"))
    max_r = max(min_r + 1, cv2.getTrackbarPos("max radius", "controls"))
    if mode == "color":
        lo = np.array(
            [
                cv2.getTrackbarPos("H min", "controls"),
                cv2.getTrackbarPos("S min", "controls"),
                cv2.getTrackbarPos("V min", "controls"),
            ]
        )
        hi = np.array(
            [
                cv2.getTrackbarPos("H max", "controls"),
                cv2.getTrackbarPos("S max", "controls"),
                cv2.getTrackbarPos("V max", "controls"),
            ]
        )
        return lo, hi, min_r, max_r
    gray_max = cv2.getTrackbarPos("gray max", "controls")
    lo = np.array([0, 0, 0])
    hi = np.array(
        [
            cv2.getTrackbarPos("H max", "controls"),
            cv2.getTrackbarPos("S max", "controls"),
            cv2.getTrackbarPos("V max", "controls"),
        ]
    )
    return lo, hi, min_r, max_r, gray_max


def ball_mask(bgr, mode: str):
    blurred = cv2.GaussianBlur(bgr, (5, 5), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    if mode == "color":
        lo, hi, min_r, max_r = read_bars(mode)
        mask = cv2.inRange(hsv, lo, hi)
    else:
        lo, hi, min_r, max_r, gray_max = read_bars(mode)
        gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
        mask_hsv = cv2.inRange(hsv, lo, hi)
        mask_gray = cv2.threshold(gray, gray_max, 255, cv2.THRESH_BINARY_INV)[1]
        mask = cv2.bitwise_or(mask_hsv, mask_gray)
        # dark mode returns extra; unify below
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.erode(mask, kernel, iterations=1)
    mask = cv2.dilate(mask, kernel, iterations=2)
    if mode == "color":
        return mask, min_r, max_r
    return mask, min_r, max_r


def find_ball(mask, min_r, max_r):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 20:
            continue
        (_x, _y), radius = cv2.minEnclosingCircle(contour)
        if radius < min_r or radius > max_r:
            continue
        peri = cv2.arcLength(contour, True)
        if peri == 0:
            continue
        circularity = (4 * np.pi * area) / (peri * peri)
        if circularity < 0.55:
            continue
        if area > best_area:
            best_area = area
            x, y, w, h = cv2.boundingRect(contour)
            best = (int(x + w / 2), int(y + h / 2), int(radius))
    return best


def main():
    args = parse_args()
    cam_id = args.camera
    cap = cv2.VideoCapture(cam_id, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(cam_id)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open camera {cam_id}. Try --camera 1")

    make_windows(args.mode)
    last = (PROCESS_WIDTH // 2, 90)
    t0 = time.perf_counter()
    frames = 0

    print("Hold a ball in front of the webcam.")
    print("Tune sliders until the MASK window is white on the ball and black everywhere else.")
    print("Printed line is the same 'x y' the robot PID will use later. q = quit.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("No frame")
                break

            h, w = frame.shape[:2]
            scale = PROCESS_WIDTH / w
            small = cv2.resize(frame, (PROCESS_WIDTH, int(h * scale)))

            mask, min_r, max_r = ball_mask(small, args.mode)
            hit = find_ball(mask, min_r, max_r)
            vis = small.copy()
            cx = PROCESS_WIDTH // 2
            cy = vis.shape[0] // 2
            cv2.drawMarker(vis, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 12, 1)

            if hit:
                x, y, r = hit
                last = (x, y)
                cv2.circle(vis, (x, y), r, (0, 255, 0), 2)
                cv2.drawMarker(vis, (x, y), (0, 0, 255), cv2.MARKER_CROSS, 16, 2)
                print(f"{x} {y}")
            else:
                x, y = last
                cv2.drawMarker(vis, (x, y), (0, 255, 255), cv2.MARKER_CROSS, 16, 2)

            frames += 1
            dt = time.perf_counter() - t0
            fps = frames / dt if dt > 0 else 0
            cv2.putText(
                vis,
                f"{args.mode}  {x},{y}  {fps:.0f} fps",
                (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            cv2.imshow("frame", vis)
            cv2.imshow("mask", mask)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("s"):
                print("sliders", read_bars(args.mode))
            if key == ord("c"):
                cap.release()
                cam_id += 1
                cap = cv2.VideoCapture(cam_id, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cam_id = 0
                    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                print("camera", cam_id)
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
