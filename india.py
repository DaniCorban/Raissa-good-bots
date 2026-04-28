#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bot India - standalone VM version."""
import io
import json
import os
import random
import re
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import uiautomator2 as u2


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()

    def flush(self):
        for s in self.streams:
            s.flush()


_logf = open("/tmp/india.log", "w", buffering=1)
sys.stdout = Tee(sys.stdout, _logf)

PHONE = "192.168.68.50"
PKG = "com.zhiliaoapp.musically"
TARGET_MIN = 22
TARGET_MAX = 31

FIRST_GLANCE_SKIP_WORDS = [
    "sponsored",
    "promoted",
    "paid partnership",
    "tiktok shop",
    "shop now",
    "buy now",
    "use code",
    "discount",
    "sale",
    "promo",
    "link in bio",
    "order now",
    "book now",
    "dm for",
    "whatsapp",
    "telegram",
]

FIRST_GLANCE_BRAND_WORDS = [
    "official",
    "magazine",
    "news",
    "radio",
    "records",
    "brand",
    "store",
    "shop",
    "agency",
    "airline",
    "airlines",
    "booking",
    "resort",
    "fanpage",
]


def find_port():
    try:
        out = subprocess.check_output(["adb", "devices", "-l"], timeout=5).decode()
        for line in out.strip().split("\n"):
            if PHONE in line and "device" in line:
                serial = line.split()[0]
                print(f"  [adb] already connected: {serial}")
                return serial
    except Exception:
        pass

    subprocess.run(["adb", "disconnect"], capture_output=True, timeout=5)
    time.sleep(1)
    print(f"  [adb] scanning ports 30000-49999 on {PHONE}...")
    for port in range(30000, 50000):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.03)
        if s.connect_ex((PHONE, port)) == 0:
            s.close()
            r = subprocess.run(
                ["adb", "connect", f"{PHONE}:{port}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "connected" in r.stdout.lower():
                serial = f"{PHONE}:{port}"
                print(f"  [adb] connected: {serial}")
                return serial
        else:
            s.close()
    return None


def connect():
    for attempt in range(3):
        print(f"[connect] attempt {attempt + 1}/3")
        serial = find_port()
        if serial:
            try:
                d = u2.connect(serial)
                print(f"[connect] connected: {serial} - {d.info.get('productName', '?')}")
                return d
            except Exception as e:
                print(f"[connect] u2.connect failed: {e}")
        time.sleep(10)
    raise RuntimeError(f"Cannot connect to phone {PHONE}")


def safe_press(d, key, retries=2, delay=0.25):
    for attempt in range(retries + 1):
        try:
            d.press(key)
            return True
        except Exception as e:
            if attempt >= retries:
                print(f"[ui] press({key}) failed: {e}")
                return False
            time.sleep(delay)
    return False


def safe_click_selector(sel, label="", retries=2, exists_timeout=0.4, delay=0.25):
    for attempt in range(retries + 1):
        try:
            if not sel.exists(timeout=exists_timeout):
                return False
            sel.click()
            return True
        except Exception as e:
            if attempt >= retries:
                if label:
                    print(f"[ui] click failed ({label}): {e}")
                else:
                    print(f"[ui] click failed: {e}")
                return False
            time.sleep(delay)
    return False


def dismiss_overlays(d):
    try:
        for _ in range(3):
            try:
                if d(textContains="TikTok LIVE").exists(timeout=0.5):
                    safe_press(d, "back")
                    time.sleep(1)
                    continue
            except Exception as e:
                print(f"[overlay] live probe failed: {e}")
            break

        if safe_click_selector(d(resourceId=f"{PKG}:id/giz"), label="close popup giz"):
            time.sleep(0.5)

        try:
            if d(resourceId=f"{PKG}:id/j_k").exists(timeout=0.5):
                safe_press(d, "back")
                time.sleep(0.5)
        except Exception as e:
            print(f"[overlay] j_k probe failed: {e}")

        if d(text="Cancel", packageName=PKG).exists(timeout=0.4):
            safe_click_selector(d(text="Cancel", packageName=PKG), label="cancel dialog")
            time.sleep(0.5)
    except Exception as e:
        print(f"[overlay] non-fatal dismiss error: {e}")


def bounds_center(bounds_str):
    b = bounds_str.replace("[", "").replace("]", " ").split()
    x1, y1 = int(b[0].split(",")[0]), int(b[0].split(",")[1])
    x2, y2 = int(b[1].split(",")[0]), int(b[1].split(",")[1])
    return (x1 + x2) // 2, (y1 + y2) // 2


def parse_bounds_safe(bounds_str):
    try:
        b = bounds_str.replace("[", "").replace("]", " ").split()
        x1, y1 = int(b[0].split(",")[0]), int(b[0].split(",")[1])
        x2, y2 = int(b[1].split(",")[0]), int(b[1].split(",")[1])
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        return x1, y1, x2, y2, cx, cy
    except Exception:
        return None


def normalize_handle(text):
    value = (text or "").strip()
    if value.startswith("@"):
        value = value[1:]
    return re.sub(r"\s+", "", value).lower()


def preview(text, limit=80):
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def dump_root(d):
    return ET.fromstring(d.dump_hierarchy())


def ensure_home(d):
    cur = d.app_current()
    if cur.get("package", "") != PKG:
        d.app_stop(PKG)
        time.sleep(1)
        d.app_start(PKG)
        time.sleep(10)
        dismiss_overlays(d)
    for _ in range(6):
        if d(description="Home", packageName=PKG).exists(timeout=1):
            break
        safe_press(d, "back")
        time.sleep(0.5)
    if not d(description="Home", packageName=PKG).exists(timeout=1):
        print("[recovery] Home not found, restarting TikTok")
        d.app_stop(PKG)
        time.sleep(1)
        d.app_start(PKG)
        time.sleep(10)
        dismiss_overlays(d)
    d(description="Home", packageName=PKG).click_exists(timeout=3)
    time.sleep(1)
    return d


def ensure_for_you(d):
    ensure_home(d)
    dismiss_overlays(d)
    for label in ("For You", "For you"):
        tab = d(text=label, packageName=PKG)
        if tab.exists(timeout=1):
            safe_click_selector(tab, label="for you tab", exists_timeout=0.3)
            time.sleep(1)
            return True
    print("[nav] For You tab not explicitly found, staying on Home feed")
    return True


def parse_followers(text):
    if not text:
        return -1
    t = text.strip().upper()
    t = t.replace("FOLLOWERS", "").replace("FOLLOWER", "").strip()
    t = t.replace("FOLLOWING", "").strip()
    t = t.replace("\u00a0", "").replace(" ", "")
    t = t.rstrip("+")
    try:
        m = re.search(r"(\d+(?:[.,]\d+)?)([KM]?)", t)
        if not m:
            return -1
        raw_num = m.group(1)
        suffix = m.group(2)
        if suffix == "K":
            return int(float(raw_num.replace(",", ".")) * 1000)
        if suffix == "M":
            return int(float(raw_num.replace(",", ".")) * 1000000)
        digits = re.sub(r"\D", "", raw_num)
        return int(digits) if digits else -1
    except Exception:
        return -1


def get_profile_stats(d):
    xml = d.dump_hierarchy()
    root = ET.fromstring(xml)
    followers_candidates = []
    following_candidates = []
    numeric_nodes = []
    screen_h = d.info.get("displayHeight", 2400)
    for n in root.iter("node"):
        if n.get("package", "") != PKG:
            continue
        parsed = parse_bounds_safe(n.get("bounds", ""))
        if not parsed:
            continue
        _, _, _, _, cx, cy = parsed
        if cy > int(screen_h * 0.70):
            continue
        texts = []
        txt = (n.get("text", "") or "").strip()
        desc = (n.get("content-desc", "") or "").strip()
        if txt:
            texts.append(txt)
        if desc and desc != txt:
            texts.append(desc)
        for raw in texts:
            low = raw.lower()
            if "follower" in low:
                m = re.search(r"(\d+(?:[.,]\d+)?\s*[KM]?\+?)\s*followers?", raw, re.IGNORECASE)
                parsed_val = parse_followers(m.group(1) if m else raw)
                if parsed_val >= 0:
                    followers_candidates.append((parsed_val, cy, raw))
            if "following" in low:
                m = re.search(r"(\d+(?:[.,]\d+)?\s*[KM]?\+?)\s*following", raw, re.IGNORECASE)
                parsed_val = parse_followers(m.group(1) if m else raw)
                if parsed_val >= 0:
                    following_candidates.append((parsed_val, cy, raw))
        for raw in texts:
            cleaned = raw.strip().replace("\u00a0", "").replace(" ", "")
            if re.fullmatch(r"\d+(?:[.,]\d+)?[KM]?\+?", cleaned, re.IGNORECASE):
                numeric_nodes.append((parse_followers(cleaned), cx, cy, raw))

    def pair_label_with_number(label_kind, label_candidates, dx_limit=220, dy_min=-140, dy_max=260):
        if label_candidates:
            return
        label_words = ("followers",) if label_kind == "followers" else ("following",)
        label_nodes = []
        for n in root.iter("node"):
            if n.get("package", "") != PKG:
                continue
            parsed = parse_bounds_safe(n.get("bounds", ""))
            if not parsed:
                continue
            _, _, _, _, lx, ly = parsed
            if ly > int(screen_h * 0.70):
                continue
            txt = (n.get("text", "") or "").strip()
            desc = (n.get("content-desc", "") or "").strip()
            combined = f"{txt} {desc}".lower()
            if any(word in combined for word in label_words):
                label_nodes.append((lx, ly))

        for lx, ly in label_nodes:
            best = None
            for num, nx, ny, raw in numeric_nodes:
                if num < 0:
                    continue
                if abs(nx - lx) > dx_limit:
                    continue
                if not (dy_min <= ny - ly <= dy_max):
                    continue
                score = abs(nx - lx) + max(0, ly - ny)
                if best is None or score < best[0]:
                    best = (score, num, raw)
            if best:
                label_candidates.append((best[1], ly, best[2]))

    pair_label_with_number("followers", followers_candidates)
    pair_label_with_number("following", following_candidates)
    pair_label_with_number("followers", followers_candidates, dx_limit=320, dy_min=-220, dy_max=420)
    pair_label_with_number("following", following_candidates, dx_limit=320, dy_min=-120, dy_max=420)

    followers = -1
    following = -1
    if followers_candidates:
        followers_candidates.sort(key=lambda x: x[1])
        followers = followers_candidates[0][0]
    if following_candidates:
        following_candidates.sort(key=lambda x: x[1])
        following = following_candidates[0][0]
    return followers, following


def get_profile_stats_with_retry(d, tries=8, delay=1.25):
    last = (-1, -1)
    for _ in range(tries):
        last = get_profile_stats(d)
        if last[0] != -1 and last[1] != -1:
            return last
        time.sleep(delay)
    return last


def _profile_follow_scan(d):
    xml = d.dump_hierarchy()
    root = ET.fromstring(xml)
    screen_h = d.info.get("displayHeight", 2400)
    action = None
    status = None
    for n in root.iter("node"):
        if n.get("package", "") != PKG:
            continue
        txt = (n.get("text", "") or "").strip()
        desc = (n.get("content-desc", "") or "").strip()
        label = txt or desc
        if label not in ("Follow", "Follow back", "Following", "Requested", "Friends"):
            continue
        bnd = n.get("bounds", "")
        parsed = parse_bounds_safe(bnd)
        if not parsed:
            continue
        x1, y1, x2, y2, cx, cy = parsed
        el_w = x2 - x1
        el_h = y2 - y1
        if cy > int(screen_h * 0.85):
            continue
        if label == "Following" and (el_w < 200 or el_h < 50):
            continue
        if cy > int(screen_h * 0.60):
            continue
        if label in ("Following", "Requested", "Friends"):
            status = label.lower()
        if label in ("Follow", "Follow back") and action is None:
            action = (cx, cy, label)
    return action, status


def follow_from_profile_confirmed(d):
    action, status = _profile_follow_scan(d)
    if status in ("following", "requested", "friends"):
        print(f"    already {status}")
        return "already"
    if not action:
        print("    follow button not found on profile")
        return "not_found"

    cx, cy, label = action
    d.shell(f"input tap {cx} {cy}")
    time.sleep(random.uniform(1.8, 2.6))

    for _ in range(4):
        next_action, next_status = _profile_follow_scan(d)
        if next_status in ("following", "requested", "friends"):
            print(f"    FOLLOW confirmed ({next_status})")
            return "followed"
        if not next_action:
            print("    FOLLOW confirmed (button disappeared)")
            return "followed"
        time.sleep(0.9)

    print(f"    FOLLOW rollback/unconfirmed ({label} still present)")
    return "failed"


def get_foryou_snapshot(d):
    root = dump_root(d)
    creator = ""
    caption = ""
    follow_overlay = ""
    like_desc = ""
    visible_text = []
    screen_h = d.info.get("displayHeight", 2400)
    for n in root.iter("node"):
        if n.get("package", "") != PKG:
            continue
        parsed = parse_bounds_safe(n.get("bounds", ""))
        if parsed:
            _, _, _, _, _, cy = parsed
            if cy > int(screen_h * 0.93):
                continue
        txt = (n.get("text", "") or "").strip()
        desc = (n.get("content-desc", "") or "").strip()
        rid = n.get("resource-id", "").replace(PKG + ":id/", "")
        if txt:
            visible_text.append(txt)
        if desc:
            visible_text.append(desc)
        if rid == "title" and not creator:
            creator = txt or desc
        elif rid == "desc" and not caption:
            caption = txt or desc
        elif rid == "f03" and not follow_overlay:
            follow_overlay = desc or txt
        elif rid == "dcc" and not like_desc:
            like_desc = desc or txt
    combined = " ".join(visible_text).lower()
    return {
        "creator": creator,
        "caption": caption,
        "follow_overlay": follow_overlay,
        "like_desc": like_desc,
        "combined": combined,
    }


def looks_ok_at_first_glance(snapshot):
    creator = normalize_handle(snapshot.get("creator", ""))
    caption = (snapshot.get("caption", "") or "").strip()
    combined = f"{creator} {caption} {snapshot.get('follow_overlay', '')} {snapshot.get('combined', '')}".lower()

    if not creator:
        return False, "missing_creator"
    if "live" in combined:
        return False, "live_content"
    for word in FIRST_GLANCE_SKIP_WORDS:
        if word in combined:
            return False, "commercial"
    for word in FIRST_GLANCE_BRAND_WORDS:
        if word in creator:
            return False, "brandish_creator"
    return True, "ok"


def open_profile_from_foryou(d):
    root = dump_root(d)
    for preferred_rid in ("qza", "title"):
        for n in root.iter("node"):
            if n.get("package", "") != PKG:
                continue
            rid = n.get("resource-id", "").replace(PKG + ":id/", "")
            if rid != preferred_rid:
                continue
            bounds = n.get("bounds", "")
            if not bounds:
                continue
            cx, cy = bounds_center(bounds)
            d.shell(f"input tap {cx} {cy}")
            time.sleep(random.uniform(2.2, 3.0))
            return True
    return False


def current_like_state(d):
    root = dump_root(d)
    for n in root.iter("node"):
        if n.get("package", "") != PKG:
            continue
        rid = n.get("resource-id", "").replace(PKG + ":id/", "")
        if rid != "dcc":
            continue
        desc = (n.get("content-desc", "") or "").strip()
        bounds = n.get("bounds", "")
        if "Video liked" in desc or desc.startswith("Liked"):
            return "liked", bounds
        if "Like video" in desc or desc.startswith("Like"):
            return "unliked", bounds
        return "unknown", bounds
    return "missing", ""


def like_current_foryou_video(d):
    state, bounds = current_like_state(d)
    if state == "liked":
        print("    like already present on current video")
        return "already"
    if state == "missing" or not bounds:
        print("    like button not found on current video")
        return "failed"

    cx, cy = bounds_center(bounds)
    d.shell(f"input tap {cx} {cy}")
    time.sleep(random.uniform(0.8, 1.2))

    for _ in range(4):
        next_state, _ = current_like_state(d)
        if next_state == "liked":
            print("    LIKE confirmed")
            return "liked"
        time.sleep(0.6)

    print("    like did not confirm")
    return "failed"


def swipe_next_foryou(d, previous_creator=None):
    w = d.info["displayWidth"]
    h = d.info["displayHeight"]
    baseline = normalize_handle(previous_creator)
    last_snapshot = None
    for _ in range(3):
        x = (w // 2) + random.randint(-35, 35)
        start_y = int(h * 0.78) + random.randint(-20, 20)
        end_y = int(h * 0.24) + random.randint(-20, 20)
        d.swipe(x, start_y, x, end_y, duration=0.16)
        time.sleep(random.uniform(1.8, 2.6))
        dismiss_overlays(d)
        last_snapshot = get_foryou_snapshot(d)
        new_creator = normalize_handle(last_snapshot.get("creator", ""))
        if not baseline or not new_creator or new_creator != baseline:
            return last_snapshot
    return last_snapshot or get_foryou_snapshot(d)


def close_tiktok(d):
    print("[cleanup] closing TikTok")
    d.app_stop(PKG)
    time.sleep(1)
    safe_press(d, "home")
    time.sleep(1)
    print("[cleanup] TikTok closed")


MAX_CYCLES_VM = 1
if "--cycles" in sys.argv:
    _ci = sys.argv.index("--cycles")
    MAX_CYCLES_VM = int(sys.argv[_ci + 1])
    print(f"[India] Running {MAX_CYCLES_VM} cycle(s)")
GOAL_OVERRIDE_VM = None
if "--goal" in sys.argv:
    _gi = sys.argv.index("--goal")
    GOAL_OVERRIDE_VM = int(sys.argv[_gi + 1])
    print(f"[India] Goal override: {GOAL_OVERRIDE_VM}")

cycle = 0
total_follows = 0
total_likes = 0
all_successes = []

d = connect()
dismiss_overlays(d)
ensure_for_you(d)

while cycle < MAX_CYCLES_VM:
    cycle += 1
    cycle_start = time.time()
    target = GOAL_OVERRIDE_VM if GOAL_OVERRIDE_VM else random.randint(TARGET_MIN, TARGET_MAX)
    successes = []
    partials = []
    skip_counts = {}
    seen_creators = set()
    inspected = 0
    no_progress = 0
    max_inspected = max(target * 20, 400)

    print("\n" + "=" * 60)
    print(f"INDIA CYCLE {cycle}: target {target} confirmed like+follow")
    print("=" * 60)

    ensure_for_you(d)
    snapshot = get_foryou_snapshot(d)
    while len(successes) < target and inspected < max_inspected:
        dismiss_overlays(d)
        creator = snapshot.get("creator", "")
        creator_key = normalize_handle(creator)
        if not creator_key:
            skip_counts["missing_creator"] = skip_counts.get("missing_creator", 0) + 1
            print("[skip] missing creator on For You card")
            snapshot = swipe_next_foryou(d, creator)
            continue
        if creator_key in seen_creators:
            skip_counts["duplicate_creator"] = skip_counts.get("duplicate_creator", 0) + 1
            print(f"[skip] duplicate creator @{creator_key}")
            snapshot = swipe_next_foryou(d, creator)
            continue

        seen_creators.add(creator_key)
        inspected += 1
        print(f"\n[candidate {inspected}] @{creator_key}")
        print(f"  caption: {preview(snapshot.get('caption', ''))}")

        looks_ok, first_reason = looks_ok_at_first_glance(snapshot)
        if not looks_ok:
            skip_counts[first_reason] = skip_counts.get(first_reason, 0) + 1
            print(f"  [first-glance] skip -> {first_reason}")
            no_progress += 1
            snapshot = swipe_next_foryou(d, creator)
            continue

        if not open_profile_from_foryou(d):
            skip_counts["open_profile_failed"] = skip_counts.get("open_profile_failed", 0) + 1
            print("  [profile] failed to open from For You")
            no_progress += 1
            ensure_for_you(d)
            snapshot = get_foryou_snapshot(d)
            continue

        dismiss_overlays(d)
        profile_followers, profile_following = get_profile_stats_with_retry(d, tries=8, delay=1.1)
        if profile_followers == -1 or profile_following == -1:
            skip_counts["profile_stats_unavailable"] = skip_counts.get("profile_stats_unavailable", 0) + 1
            print("  [guard] profile stats unavailable -> skip")
            safe_press(d, "back")
            time.sleep(0.8)
            no_progress += 1
            snapshot = swipe_next_foryou(d, creator)
            continue

        print(f"  [guard] {profile_followers} followers, {profile_following} following")
        if profile_followers > 5000:
            skip_counts["followers_too_high"] = skip_counts.get("followers_too_high", 0) + 1
            print("  [guard] followers too high -> skip")
            safe_press(d, "back")
            time.sleep(0.8)
            no_progress += 1
            snapshot = swipe_next_foryou(d, creator)
            continue
        if profile_following * 3 <= profile_followers:
            skip_counts["low_reciprocity"] = skip_counts.get("low_reciprocity", 0) + 1
            print("  [guard] reciprocity rule failed -> skip")
            safe_press(d, "back")
            time.sleep(0.8)
            no_progress += 1
            snapshot = swipe_next_foryou(d, creator)
            continue

        follow_result = follow_from_profile_confirmed(d)
        safe_press(d, "back")
        time.sleep(random.uniform(0.9, 1.3))

        if follow_result != "followed":
            skip_counts[f"follow_{follow_result}"] = skip_counts.get(f"follow_{follow_result}", 0) + 1
            partials.append({"creator": creator_key, "follow": follow_result, "like": "not_attempted"})
            print(f"  [result] follow did not confirm -> {follow_result}")
            no_progress += 1
            snapshot = swipe_next_foryou(d, creator)
            continue

        like_result = like_current_foryou_video(d)
        if like_result == "liked":
            total_follows += 1
            total_likes += 1
            all_successes.append(creator_key)
            successes.append(creator_key)
            no_progress = 0
            print(f"  [success] @{creator_key} ({len(successes)}/{target})")
            time.sleep(random.uniform(1.0, 1.8))
        else:
            skip_counts[f"like_{like_result}"] = skip_counts.get(f"like_{like_result}", 0) + 1
            partials.append({"creator": creator_key, "follow": "followed", "like": like_result})
            no_progress += 1
            print(f"  [partial] follow confirmed but like={like_result}")

        if len(successes) < target:
            snapshot = swipe_next_foryou(d, creator)

        if no_progress and no_progress % 40 == 0:
            print(f"[recovery] {no_progress} consecutive non-successes, refreshing Home")
            ensure_for_you(d)
            snapshot = get_foryou_snapshot(d)

    elapsed = time.time() - cycle_start
    print("\n" + "-" * 60)
    print(f"INDIA CYCLE {cycle} DONE")
    print(f"target: {target}")
    print(f"confirmed follows: {len(successes)}")
    print(f"inspected creators: {inspected}")
    print(f"elapsed min: {elapsed / 60:.1f}")
    print(f"skip counts: {json.dumps(skip_counts, sort_keys=True)}")
    if successes:
        print("success handles:")
        for handle in successes:
            print(f"  - {handle}")
    if partials:
        print("partials:")
        for item in partials[:40]:
            print(f"  - @{item['creator']}: follow={item['follow']} like={item['like']}")
    print("-" * 60)

close_tiktok(d)

print("\n" + "=" * 60)
print(f"INDIA FINISHED: {total_follows} follows, {total_likes} likes")
print("=" * 60)
