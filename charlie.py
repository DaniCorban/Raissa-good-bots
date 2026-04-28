#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bot Charlie — standalone VM version. No Windows dependency.

Usage:
    python3 charlie.py              # run until limits
    python3 charlie.py --cycles 1   # single cycle
"""
import uiautomator2 as u2
import time, random, subprocess, socket, re
import xml.etree.ElementTree as ET
import sys, io
import os, json, hashlib

# Tee stdout to /tmp/charlie.log so we can read progress
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

_logf = open("/tmp/charlie.log", "w", buffering=1)
sys.stdout = Tee(sys.stdout, _logf)

PHONE = "192.168.68.50"
PKG = "com.zhiliaoapp.musically"
MAX_FOLLOWS = 45
MAX_COMMENTS = 55

SEARCH_QUERY_GROUPS = [
    "women backpacking europe",
    "girl travel alone",
    "digital nomad woman",
    "hostel life europe",
    "budget travel tips",
    "first solo trip",
    "europe train travel",
    "road trip balkan",
    "van life europe",
    "coastal town travel",
    "mountain cabin vlog",
    "sunrise hike vlog",
    "sunset travel diary",
    "airport day in life",
    "carry on only travel",
    "weekend city break",
    "hidden gems europe",
    "romanian travel vlog",
    "bucharest travel",
    "greece island hopping",
    "portugal road trip",
    "italy solo travel",
    "spain budget trip",
    "croatia travel vlog",
    "albania beaches trip",
    "montenegro bay travel",
    "turkey cappadocia travel",
    "georgia tbilisi travel",
    "czech prague travel",
    "vienna coffee travel",
    "budapest thermal trip",
    "berlin hostel vlog",
    "paris budget itinerary",
    "amsterdam canal travel",
    "lisbon solo female",
    "remote work cafe",
    "coworking travel day",
    "laptop lifestyle travel",
    "work from hotel",
    "travel routine morning",
    "travel routine night",
    "packing tips backpack",
    "travel journal ideas",
    "gap year adventures",
    "hiking trails europe",
    "adventure travel story",
    "slow travel lifestyle",
    "women travel photography",
    "girls trip europe vlog",
    "female travel creator",
    "city break packing tips",
    "europe hidden cafe",
    "boutique hotel travel",
    "europe weekend getaway",
    "backpacking train journey",
    "solo travel itinerary",
    "travel couple alternatives",
]
ALFA_QUERIES = SEARCH_QUERY_GROUPS
BRAVO_QUERIES = SEARCH_QUERY_GROUPS
QUERY_STATE_FILE = "/home/corban/charlie/charlie_query_state.json"
COMMENT_HISTORY_FILE = "/home/corban/charlie/tt_comment_history.json"
COMMENT_CREATOR_COOLDOWN_SECS = 12 * 3600

def load_query_state():
    # If we don't have saved state yet, don't restart from the exact same query.
    default = {
        "alfa_start": random.SystemRandom().randrange(len(ALFA_QUERIES)),
        "bravo_start": random.SystemRandom().randrange(len(BRAVO_QUERIES)),
    }
    try:
        if not os.path.exists(QUERY_STATE_FILE):
            return default
        with open(QUERY_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default
        return {
            "alfa_start": int(data.get("alfa_start", 0)),
            "bravo_start": int(data.get("bravo_start", 0)),
        }
    except Exception:
        return default

def save_query_state(alfa_idx, bravo_idx):
    try:
        data = {
            "alfa_start": int(alfa_idx % len(ALFA_QUERIES)),
            "bravo_start": int(bravo_idx % len(BRAVO_QUERIES)),
        }
        with open(QUERY_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[state] failed to save query state: {e}")

def load_comment_history():
    default = {"keys": [], "creator_last": {}}
    try:
        if not os.path.exists(COMMENT_HISTORY_FILE):
            return {"keys": set(), "creator_last": {}}
        with open(COMMENT_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"keys": set(), "creator_last": {}}
        keys = data.get("keys", [])
        creator_last = data.get("creator_last", {})
        if not isinstance(keys, list):
            keys = []
        if not isinstance(creator_last, dict):
            creator_last = {}
        return {
            "keys": set(str(k) for k in keys if str(k).strip()),
            "creator_last": {str(k): int(v) for k, v in creator_last.items() if str(k).strip()},
        }
    except Exception as e:
        print(f"[state] failed to load comment history: {e}")
        return {"keys": set(), "creator_last": {}}

def save_comment_history(state):
    try:
        data = {
            "keys": sorted(state.get("keys", set())),
            "creator_last": {k: int(v) for k, v in state.get("creator_last", {}).items()},
        }
        with open(COMMENT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[state] failed to save comment history: {e}")

def norm_comment_piece(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())

def make_comment_key(creator, username, caption):
    base = "|".join([
        norm_comment_piece(creator),
        norm_comment_piece(username),
        norm_comment_piece(caption),
    ])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

# ── OpenAI setup ──
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
MY_USERNAME = "i.live.in.hotels"
MY_DISPLAY_NAME = "Raissa"

RELEVANT_KEYWORDS = [
    "travel", "trip", "backpack", "nomad", "hotel", "hostel", "airbnb",
    "flight", "airport", "passport", "visa", "luggage", "suitcase",
    "europe", "asia", "africa", "south america", "latin america",
    "romania", "bucharest",
    "solo", "adventure", "explore", "wander", "roam",
    "remote work", "digital nomad", "work from", "laptop lifestyle",
    "cafe", "coffee shop", "cowork",
    "beach", "mountain", "island", "city", "village", "countryside",
    "sunset", "sunrise", "view", "landscape", "scenery",
    "culture", "local", "street food", "cuisine", "market",
    "hiking", "trek", "road trip", "van life", "camping",
    "vlog", "diary", "journal",
]

RAISSA_SYSTEM = """You are Raissa, 27, Romanian, nomadic. You live in hotels across Europe, rarely the same city twice in a month.

When commenting on someone's TikTok post:
- Write 1-2 SHORT sentences. Maximum. Never more.
- Be specific to what's actually in their post. Generic = instant skip.
- No hashtags. No emojis unless one is genuinely earned.
- Sound like a real person who paused mid-scroll because something caught them.
- Don't start with "Love this", "So beautiful", "Amazing" or similar filler.
- Subtle warmth. Not performative enthusiasm.
- If the content is NOT about travel, nomad life, remote work, exploring places, or living abroad, reply: SKIP
- If the content is commercial, promotional, or you can't write something specific, reply: SKIP
- Write in English unless the original post is clearly Romanian.
- NEVER use dashes or em-dashes as separators between clauses. No " - ", no " — ", no " – ". Use periods or commas instead. Hyphens are only allowed inside compound words like "well-known".
"""

def is_relevant(caption):
    if not caption or len(caption) < 5: return False
    low = caption.lower()
    return any(kw in low for kw in RELEVANT_KEYWORDS)

def generate_comment(caption):
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_KEY)
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": RAISSA_SYSTEM},
            {"role": "user", "content": f"TikTok video caption:\n\n{caption}\n\nWrite your comment:"}
        ],
        max_tokens=80, temperature=0.9,
    )
    return resp.choices[0].message.content.strip().strip('"')

# ── ADB connection ──
def find_port():
    """Find phone ADB port: first check existing devices, then scan."""
    # 1. Check already-connected devices
    try:
        out = subprocess.check_output(["adb","devices","-l"], timeout=5).decode()
        for line in out.strip().split("\n"):
            if PHONE in line and "device" in line:
                serial = line.split()[0]
                print(f"  [adb] Already connected: {serial}")
                return serial
    except Exception:
        pass

    # 2. Disconnect stale entries
    subprocess.run(["adb","disconnect"], capture_output=True, timeout=5)
    time.sleep(1)

    # 3. Scan for wireless debugging port
    print(f"  [adb] Scanning ports 30000-49999 on {PHONE}...")
    for port in range(30000, 50000):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.03)
        if s.connect_ex((PHONE, port)) == 0:
            s.close()
            print(f"  [adb] Port {port} open — trying adb connect...")
            r = subprocess.run(["adb","connect",f"{PHONE}:{port}"],
                               capture_output=True, text=True, timeout=5)
            if "connected" in r.stdout.lower():
                serial = f"{PHONE}:{port}"
                print(f"  [adb] Connected: {serial}")
                return serial
            else:
                print(f"  [adb] Port {port}: {r.stdout.strip()} {r.stderr.strip()}")
        else:
            s.close()
    return None

def connect():
    """Connect to phone with retries."""
    for attempt in range(3):
        print(f"[connect] Attempt {attempt+1}/3...")
        serial = find_port()
        if serial:
            try:
                d = u2.connect(serial)
                print(f"Connected: {serial} - {d.info.get('productName','?')}")
                return d
            except Exception as e:
                print(f"  [connect] u2.connect failed: {e}")
        print(f"  [connect] Waiting 10s before retry...")
        time.sleep(10)
    raise RuntimeError(f"Cannot connect to phone {PHONE} after 3 attempts")

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
    """Best-effort click for volatile selectors (avoids run-killing races)."""
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
                print(f"[overlay] TikTok LIVE probe failed: {e}")
            break

        if safe_click_selector(d(resourceId=f"{PKG}:id/giz"), label="close popup giz"):
            time.sleep(0.5)

        try:
            if d(resourceId=f"{PKG}:id/j_k").exists(timeout=0.5):
                safe_press(d, "back")
                time.sleep(0.5)
        except Exception as e:
            print(f"[overlay] j_k probe failed: {e}")
    except Exception as e:
        print(f"[overlay] dismiss_overlays non-fatal error: {e}")

def bounds_center(bounds_str):
    b = bounds_str.replace("[","").replace("]"," ").split()
    x1,y1 = int(b[0].split(",")[0]), int(b[0].split(",")[1])
    x2,y2 = int(b[1].split(",")[0]), int(b[1].split(",")[1])
    return (x1+x2)//2, (y1+y2)//2

def ensure_home(d):
    """Force TikTok to a clean Home state. Returns device."""
    cur = d.app_current()
    if cur.get("package","") != PKG:
        d.app_stop(PKG); time.sleep(1)
        d.app_start(PKG); time.sleep(10)
        dismiss_overlays(d)
    # Press back until Home tab is visible
    for _ in range(6):
        if d(description="Home", packageName=PKG).exists(timeout=1):
            break
        d.press("back"); time.sleep(0.5)
    # If still not on Home, force restart
    if not d(description="Home", packageName=PKG).exists(timeout=1):
        print("  [recovery] Home not found, restarting TikTok...")
        d.app_stop(PKG); time.sleep(1)
        d.app_start(PKG); time.sleep(10)
        dismiss_overlays(d)
    d(description="Home", packageName=PKG).click_exists(timeout=3); time.sleep(1)
    return d

# ═══════════════════════════════════════════════════════════
# ALFA FUNCTIONS (Like + Follow)
# ═══════════════════════════════════════════════════════════

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
            num = float(raw_num.replace(",", "."))
            return int(num * 1000)
        if suffix == "M":
            num = float(raw_num.replace(",", "."))
            return int(num * 1000000)
        digits = re.sub(r"\D", "", raw_num)
        return int(digits) if digits else -1
    except Exception:
        return -1

def parse_bounds_safe(bounds_str):
    try:
        b = bounds_str.replace("[", "").replace("]", " ").split()
        x1, y1 = int(b[0].split(",")[0]), int(b[0].split(",")[1])
        x2, y2 = int(b[1].split(",")[0]), int(b[1].split(",")[1])
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        return x1, y1, x2, y2, cx, cy
    except Exception:
        return None

def go_search_users(d, query):
    """Home -> Friends -> Search -> type query -> Users tab."""
    ensure_home(d)
    fr = d(description="Friends", packageName=PKG)
    if fr.exists(timeout=3):
        fr.click(); time.sleep(1.5)
    else:
        print("  [nav] Friends NOT FOUND"); return False
    xml = d.dump_hierarchy()
    root = ET.fromstring(xml)
    search_found = False
    for n in root.iter("node"):
        if n.get("package","") != PKG: continue
        desc = n.get("content-desc","")
        rid = n.get("resource-id","").replace(PKG+":id/","")
        if "search" in desc.lower() or rid in ("h_9","fv0"):
            cx, cy = bounds_center(n.get("bounds",""))
            d.click(cx, cy); time.sleep(1)
            print(f"  [nav] Search clicked: rid={rid}")
            search_found = True
            break
    if not search_found:
        print("  [nav] Search icon NOT FOUND"); return False
    for _retry in range(2):
        ea5 = d(resourceId=f"{PKG}:id/ea5")
        if ea5.exists(timeout=5):
            try:
                ea5.click(); time.sleep(0.25)
                ea5.clear_text(); time.sleep(0.25)
                d.send_keys(query); time.sleep(0.5)
                print(f"  [nav] Typed: {query}")
                break
            except Exception as e:
                print(f"  [nav] Search box error (attempt {_retry+1}): {e}")
                time.sleep(2)
                if _retry == 1: return False
        else:
            print("  [nav] Search box NOT FOUND"); return False
    sub = d(resourceId=f"{PKG}:id/qh_")
    if sub.exists(timeout=2):
        sub.click(); time.sleep(1.5)
    else:
        d.press("enter"); time.sleep(1.5)
    for _ in range(3):
        if d(text="Users").exists(timeout=2):
            d(text="Users").click(); time.sleep(1.5)
            print("  [nav] Users tab OK")
            return True
        d.swipe(900, 320, 300, 320, duration=0.15); time.sleep(0.5)
    print("  [nav] Users tab NOT FOUND")
    return False

def parse_user_stats_from_info(info_text):
    """Parse '123 Following · 4,5K Followers' style text."""
    followers = -1
    following = -1
    if not info_text:
        return followers, following
    for part in info_text.split("\u00b7"):
        p = part.strip()
        low = p.lower()
        token = p.split()[0] if p.split() else p
        if "follower" in low:
            followers = parse_followers(token)
        elif "following" in low:
            following = parse_followers(token)
    return followers, following

def get_users(d):
    xml = d.dump_hierarchy()
    root = ET.fromstring(xml)

    qow = []
    pyo = []
    lu1 = []
    for n in root.iter("node"):
        rid = n.get("resource-id", "")
        if rid == f"{PKG}:id/qow":
            qow.append(n)
        elif rid == f"{PKG}:id/pyo":
            pyo.append(n)
        elif rid == f"{PKG}:id/lu1":
            lu1.append(n)

    info_rows = []
    for n in pyo:
        bnd = n.get("bounds", "")
        parsed = parse_bounds_safe(bnd)
        if not parsed:
            continue
        _, _, _, _, _, cy = parsed
        info = n.get("text", "")
        fol, following = parse_user_stats_from_info(info)
        info_rows.append({"cy": cy, "fol": fol, "following": following})

    btn_rows = []
    for n in lu1:
        bnd = n.get("bounds", "")
        parsed = parse_bounds_safe(bnd)
        if not parsed:
            continue
        x1, y1, x2, y2, cx, cy = parsed
        btn_text = n.get("text", "").strip()
        btn_rows.append({
            "cy": cy,
            "cx": cx,
            "bounds": bnd,
            "text": btn_text,
            "w": x2 - x1,
            "h": y2 - y1,
        })

    users = []
    for un in qow:
        uname = un.get("text","").replace("\u200e","").replace("\u2068","").replace("\u2069","").strip()
        ubnd = un.get("bounds","")
        parsed = parse_bounds_safe(ubnd)
        if not parsed or not uname:
            continue
        _, _, _, _, ucx, ucy = parsed

        best_info = None
        for info in info_rows:
            dy = abs(info["cy"] - ucy)
            if dy > 140:
                continue
            if best_info is None or dy < best_info["dy"]:
                best_info = {"dy": dy, "fol": info["fol"], "following": info["following"]}
        fol = best_info["fol"] if best_info else -1
        following = best_info["following"] if best_info else -1

        best_btn = None
        for br in btn_rows:
            if br["text"] != "Follow":
                continue
            dy = abs(br["cy"] - ucy)
            if dy > 140:
                continue
            if br["cx"] <= ucx:
                continue
            score = dy + max(0, br["cx"] - ucx) * 0.01
            if best_btn is None or score < best_btn["score"]:
                best_btn = {"score": score, "bounds": br["bounds"]}

        if best_btn:
            users.append((uname, fol, following, best_btn["bounds"]))
    return users

def get_profile_stats(d):
    """Read followers/following from opened profile. Returns tuple (-1,-1) if unknown."""
    xml = d.dump_hierarchy()
    root = ET.fromstring(xml)
    followers_candidates = []
    following_candidates = []
    numeric_nodes = []
    screen_h = d.info.get("displayHeight", 2400)
    for n in root.iter("node"):
        if n.get("package", "") != PKG:
            continue
        bnd = n.get("bounds", "")
        parsed = parse_bounds_safe(bnd)
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
        # Keep numeric-only nodes so we can pair them with a nearby label node.
        for raw in texts:
            cleaned = raw.strip().replace("\u00a0", "").replace(" ", "")
            if re.fullmatch(r"\d+(?:[.,]\d+)?[KM]?\+?", cleaned, re.IGNORECASE):
                numeric_nodes.append((parse_followers(cleaned), cx, cy, raw))

    def pair_label_with_number(label_kind, label_candidates, dx_limit=220, dy_min=-140, dy_max=260):
        if label_candidates:
            return
        # Fallback: labels often appear as a separate node from the number.
        # Match a nearby numeric node in the same column.
        label_words = ("followers",) if label_kind == "followers" else ("following",)
        label_nodes = []
        for n in root.iter("node"):
            if n.get("package", "") != PKG:
                continue
            bnd = n.get("bounds", "")
            parsed = parse_bounds_safe(bnd)
            if not parsed:
                continue
            _, _, _, _, lx, ly = parsed
            if ly > int(screen_h * 0.70):
                continue
            txt = (n.get("text", "") or "").strip()
            desc = (n.get("content-desc", "") or "").strip()
            combined = f"{txt} {desc}".lower()
            if any(word in combined for word in label_words):
                label_nodes.append((lx, ly, combined))

        for lx, ly, _ in label_nodes:
            best = None
            for num, nx, ny, raw in numeric_nodes:
                if num < 0:
                    continue
                # The number is usually above the label and in the same column.
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
    # Wider fallback for the following stat because TikTok often renders it
    # later or with a slightly different layout than followers.
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

def follow_from_profile(d):
    """On a TikTok profile page: tap Follow using shell (bypasses video overlay issues).
    Returns True if tapped Follow, False if already Following/Requested or not found."""
    xml = d.dump_hierarchy()
    root = ET.fromstring(xml)
    screen_h = d.info.get("displayHeight", 2400)
    # Pass 1: find by resource-id containing "follow" (TikTok uses various ids)
    for n in root.iter("node"):
        if n.get("package","") != PKG: continue
        rid = n.get("resource-id","").replace(PKG+":id/","").lower()
        if "follow" not in rid: continue
        txt = n.get("text","").strip()
        desc = n.get("content-desc","").strip()
        label = txt or desc
        if label in ("Following", "Requested", "Friends"):
            print(f"    already {label} (profile)")
            return False
        if label in ("Follow", "Follow back"):
            bnd = n.get("bounds","")
            if bnd:
                cx, cy = bounds_center(bnd)
                if cy > int(screen_h * 0.60):
                    continue
                d.shell(f"input tap {cx} {cy}")
                time.sleep(random.uniform(1.2, 1.8))
                print(f"    FOLLOW (profile, rid={rid}) \u2713")
                return True
    # Pass 2: fallback — search by exact text "Follow"/"Following"
    # Exclude the "Following" tab in profile stats (shows follower count area)
    follow_btn = None
    already_status = None
    for n in root.iter("node"):
        if n.get("package","") != PKG: continue
        txt = n.get("text","").strip()
        desc = n.get("content-desc","").strip()
        label = txt or desc
        if label not in ("Follow", "Follow back", "Following", "Requested", "Friends"):
            continue
        bnd = n.get("bounds","")
        if not bnd: continue
        cx, cy = bounds_center(bnd)
        # Parse bounds to get width of element
        import re as _re
        nums = list(map(int, _re.findall(r'\d+', bnd)))
        el_w = nums[2] - nums[0] if len(nums)==4 else 0
        el_h = nums[3] - nums[1] if len(nums)==4 else 0
        cls = n.get("class","")
        print(f"    [dbg] label='{label}' pos=({cx},{cy}) size={el_w}x{el_h} cls={cls}")
        # Skip nav bar (bottom 20%)
        if cy > int(screen_h * 0.85): continue
        # Skip "Following" that is a small stats label (follower count tab)
        # The real Follow/Following button is wide (>200px) and tall (>60px)
        if label in ("Following",) and (el_w < 200 or el_h < 50):
            print(f"    [dbg] skipping stats tab Following ({el_w}x{el_h})")
            continue
        if label in ("Following", "Requested", "Friends"):
            already_status = label
        if label in ("Follow", "Follow back") and follow_btn is None:
            # Prefer the main profile button near the top half of the page.
            if cy <= int(screen_h * 0.60):
                follow_btn = (cx, cy, label)
    if already_status:
        print(f"    already {already_status} (profile fallback)")
        return False
    if follow_btn:
        cx, cy, label = follow_btn
        d.shell(f"input tap {cx} {cy}")
        time.sleep(random.uniform(1.2, 1.8))
        print(f"    FOLLOW (profile text fallback) \u2713")
        return True
    print("    Follow button NOT FOUND on profile")
    return False

def get_profile_stats_with_retry(d, tries=3, delay=0.8):
    """Read profile stats with a few retries because TikTok can paint the labels lazily."""
    last = (-1, -1)
    for attempt in range(tries):
        last = get_profile_stats(d)
        if last[0] != -1 and last[1] != -1:
            return last
        time.sleep(delay)
    return last

def engage_user(d, uname, fol, following, follow_btn_bounds):
    """New flow: open profile -> follow via shell tap -> open video -> like via shell tap.
    Shell tap bypasses the video overlay event capture issue."""
    t0 = time.time()
    total_time = random.uniform(4, 7)
    print(f"  -> @{uname} ({fol} followers, {following} following)")

    # 1. Open user profile — click on username text node (rid=qow) matching uname
    xml = d.dump_hierarchy()
    root = ET.fromstring(xml)
    opened_profile = False
    for n in root.iter("node"):
        if n.get("package","") != PKG: continue
        rid = n.get("resource-id","").replace(PKG+":id/","")
        if rid == "qow" and n.get("text","").replace("\u200e","").replace("\u2068","").replace("\u2069","").strip() == uname:
            bnd = n.get("bounds","")
            cx, cy = bounds_center(bnd)
            d.click(cx, cy)
            opened_profile = True
            break
    if not opened_profile:
        # Fallback: click at left of follow button (profile picture area)
        _, by = bounds_center(follow_btn_bounds)
        d.click(120, by)
        opened_profile = True

    time.sleep(random.uniform(3, 4))

    # Safety guards: profile-level check before Follow.
    profile_fol, profile_following = get_profile_stats_with_retry(d, tries=8, delay=1.25)
    if profile_fol == -1 or profile_following == -1:
        print("    [guard] profile stats unavailable after retry -> skip")
        d.press("back"); time.sleep(0.5)
        return False
    print(f"    [guard] profile stats: {profile_fol} followers, {profile_following} following")
    if profile_fol > 5000:
        print(f"    [guard] profile followers too high ({profile_fol}) -> skip")
        d.press("back"); time.sleep(0.5)
        return False
    if profile_following * 3 <= profile_fol:
        print(f"    [guard] low reciprocity profile ({profile_following} following vs {profile_fol} followers) -> skip")
        d.press("back"); time.sleep(0.5)
        return False

    # 2. Follow from profile using shell tap (NOT on video overlay)
    followed = follow_from_profile(d)

    # 3. Find and open a non-pinned video post to like it
    xml2 = d.dump_hierarchy()
    root2 = ET.fromstring(xml2)
    target_post = None
    for n in root2.iter("node"):
        if n.get("package","") != PKG: continue
        rid = n.get("resource-id","").replace(PKG+":id/","")
        if rid != "cna": continue
        bounds = n.get("bounds","")
        if bounds.startswith("[0,") and ",2274]" in bounds: continue
        pinned = any(c.get("resource-id","").endswith("qn9") for c in n.iter("node"))
        if pinned: continue
        target_post = bounds
        break

    if target_post:
        cx, cy = bounds_center(target_post)
        d.click(cx, cy)
        time.sleep(random.uniform(1.5, 2.5))

        # 4. Like the video via shell tap (also bypasses overlay capture)
        xml3 = d.dump_hierarchy()
        root3 = ET.fromstring(xml3)
        for n in root3.iter("node"):
            if n.get("package","") != PKG: continue
            rid = n.get("resource-id","").replace(PKG+":id/","")
            desc = n.get("content-desc","")
            if rid == "dcc":
                if "Like video" in desc:
                    cx2, cy2 = bounds_center(n.get("bounds",""))
                    d.shell(f"input tap {cx2} {cy2}")
                    time.sleep(0.5)
                    print(f"    LIKE (shell) \u2713")
                elif "Video liked" in desc or "Liked" in desc:
                    print(f"    already liked")
                break
        # Back out of video
        d.press("back"); time.sleep(0.5)
    else:
        print("    No non-pinned post found on profile")

    # 5. Back to search results
    d.press("back"); time.sleep(0.5)

    elapsed = time.time() - t0
    if elapsed < total_time:
        time.sleep(total_time - elapsed)

    return followed

# ═══════════════════════════════════════════════════════════
# BRAVO FUNCTIONS (AI Comment)
# ═══════════════════════════════════════════════════════════

def parse_count(text):
    if not text: return 0
    text = text.strip().replace(",", "")
    try:
        if text.upper().endswith("K"): return int(float(text[:-1]) * 1000)
        elif text.upper().endswith("M"): return int(float(text[:-1]) * 1000000)
        else: return int(text)
    except: return 0

def go_search_videos(d, query):
    ensure_home(d)
    fr = d(description="Friends", packageName=PKG)
    if fr.exists(timeout=3):
        fr.click(); time.sleep(1.5)
    else:
        print("  [nav] Friends NOT FOUND"); return False
    xml = d.dump_hierarchy()
    root = ET.fromstring(xml)
    search_found = False
    for n in root.iter("node"):
        if n.get("package","") != PKG: continue
        desc = n.get("content-desc","")
        rid = n.get("resource-id","").replace(PKG+":id/","")
        if "search" in desc.lower() or rid in ("h_9","fv0"):
            cx, cy = bounds_center(n.get("bounds",""))
            d.click(cx, cy); time.sleep(1)
            print(f"  [nav] Search clicked: rid={rid}")
            search_found = True; break
    if not search_found:
        print("  [nav] Search icon NOT FOUND"); return False
    for _retry in range(2):
        ea5 = d(resourceId=f"{PKG}:id/ea5")
        if ea5.exists(timeout=5):
            try:
                ea5.click(); time.sleep(0.25)
                ea5.clear_text(); time.sleep(0.25)
                d.send_keys(query); time.sleep(0.5)
                print(f"  [nav] Typed: {query}")
                break
            except Exception as e:
                print(f"  [nav] Search box error (attempt {_retry+1}): {e}")
                time.sleep(2)
                if _retry == 1: return False
        else:
            print("  [nav] Search box NOT FOUND"); return False
    sub = d(resourceId=f"{PKG}:id/qh_")
    if sub.exists(timeout=2):
        sub.click(); time.sleep(1.5)
    else:
        d.press("enter"); time.sleep(1.5)
    vt = d(text="Videos")
    if vt.exists(timeout=5):
        vt.click(); time.sleep(1.5)
        print("  [nav] Videos tab OK")
    else:
        print("  [nav] Videos tab NOT FOUND"); return False
    for label in ("Date posted", "Recently uploaded"):
        btn = d(textContains=label)
        if btn.exists(timeout=2):
            btn.click(); time.sleep(1)
            recent = d(text="Recently uploaded")
            if recent.exists(timeout=2):
                recent.click(); time.sleep(1)
            break
    time.sleep(1)
    w, h = d.info["displayWidth"], d.info["displayHeight"]
    d.click(w // 4, h // 2)
    time.sleep(2)
    print("  [nav] In video feed")
    return True

def get_caption(d):
    xml = d.dump_hierarchy()
    root = ET.fromstring(xml)
    for n in root.iter("node"):
        if n.get("package","") != PKG: continue
        rid = n.get("resource-id","").replace(PKG+":id/","")
        if rid == "desc": return n.get("text","")
    best = ""
    for n in root.iter("node"):
        if n.get("package","") != PKG: continue
        t = n.get("text","")
        if len(t) > len(best) and len(t) > 15: best = t
    return best

def get_video_info(d):
    xml = d.dump_hierarchy()
    root = ET.fromstring(xml)
    username = ""; age = ""; likes = 0; comments = 0
    for n in root.iter("node"):
        if n.get("package","") != PKG: continue
        rid = n.get("resource-id","").replace(PKG+":id/","")
        if rid == "title": username = n.get("text","")
        elif rid == "qc3": age = n.get("text","").strip()
        elif rid == "dc_": likes = parse_count(n.get("text",""))
        elif rid == "cch": comments = parse_count(n.get("text",""))
    return username, age, likes, comments

def already_commented(d):
    """Legacy stub kept for compatibility. Use the history-based checker below."""
    return False

def should_skip_comment(creator, username, caption):
    """Smarter duplicate guard: exact video signature + creator cooldown, no scroll guessing."""
    now = int(time.time())
    key = make_comment_key(creator, username, caption)
    creator_key = norm_comment_piece(creator or username)
    if key in COMMENT_STATE["keys"]:
        print("    [dup] exact post signature already commented")
        return True
    last_seen = COMMENT_STATE["creator_last"].get(creator_key)
    if last_seen is not None and now - int(last_seen) < COMMENT_CREATOR_COOLDOWN_SECS:
        age_min = int((now - int(last_seen)) / 60)
        print(f"    [dup] same creator commented {age_min} min ago -> skip")
        return True
    return False

def record_comment(creator, username, caption):
    key = make_comment_key(creator, username, caption)
    creator_key = norm_comment_piece(creator or username)
    now = int(time.time())
    COMMENT_STATE["keys"].add(key)
    if creator_key:
        COMMENT_STATE["creator_last"][creator_key] = now
    save_comment_history(COMMENT_STATE)

MIN_LIKES = 500
MIN_COMMENTS = 1

def get_video_creator(d):
    """Citește numele creatorului video-ului din rid=title (stabil, nu se schimbă cu overlay)."""
    title = d(resourceId=f"{PKG}:id/title")
    if title.exists(timeout=2):
        return title.get_text().strip()
    return ""

def close_comments_panel(d):
    """Închide panoul de comentarii și verifică că s-a închis."""
    # Metoda 1: butonul Close comments (aqw)
    close_btn = d(resourceId=f"{PKG}:id/aqw")
    if close_btn.exists(timeout=1):
        close_btn.click()
        time.sleep(1)
        return
    # Metoda 2: press back
    d.press("back")
    time.sleep(1)
    # Verifică că panoul s-a închis (cfx trebuie să fie vizibil din nou)
    if not d(resourceId=f"{PKG}:id/cfx").exists(timeout=2):
        d.press("back")
        time.sleep(1)

def comment_on_video(d, idx):
    """Flow corect de comentare:
    1. Citește creator + caption de pe video (FĂRĂ a deschide comentariile)
    2. Verifică likes/comments minime
    3. Generează comentariu AI
    4. Deschide panoul de comentarii (cfx)
    5. Verifică istoricul de comentarii înainte de a deschide panoul
    6. Click pe input (ccr), tastează, postează (bgi)
    7. ÎNCHIDE panoul de comentarii
    """
    # Citește info de pe video (fără panou deschis)
    creator = get_video_creator(d)
    caption = get_caption(d)
    username, age, likes, comments = get_video_info(d)
    print(f"\n  [{idx}] @{creator} ({username}) {age} | {likes} likes, {comments} comments")
    print(f"    Caption: {caption[:120]}{'...' if len(caption)>120 else ''}")

    if likes < MIN_LIKES:
        print(f"    -> TOO FEW LIKES ({likes} < {MIN_LIKES}), skip"); return False
    if comments < MIN_COMMENTS:
        print(f"    -> NO COMMENTS ({comments} < {MIN_COMMENTS}), skip"); return False
    if not caption or len(caption) < 5:
        caption = f"Travel video by {creator or username}"

    if should_skip_comment(creator, username, caption):
        print(f"    -> ALREADY COMMENTED RECENTLY, skip")
        return False

    # Generează comentariu ÎNAINTE de a deschide panoul
    comment = generate_comment(caption)
    print(f"    AI: {comment}")
    if not comment or comment.strip().upper() == "SKIP":
        print(f"    -> AI decided SKIP"); return False

    # Deschide panoul de comentarii
    cfx = d(resourceId=f"{PKG}:id/cfx")
    if not cfx.exists(timeout=3):
        print(f"    -> Comment button NOT FOUND, skip"); return False
    cfx.click()
    time.sleep(5)  # Așteptare generoasă pentru panoul de comentarii

    # Click pe input-ul de comentarii
    ccr = d(resourceId=f"{PKG}:id/ccr")
    if not ccr.exists(timeout=3):
        print(f"    -> Comment input NOT FOUND, skip")
        close_comments_panel(d)
        return False
    ccr.click()
    time.sleep(2)

    # Tastează comentariul
    d.send_keys(comment)
    time.sleep(random.uniform(0.5, 1))

    # Postează
    bgi = d(resourceId=f"{PKG}:id/bgi")
    if bgi.exists(timeout=3):
        bgi.click()
        time.sleep(2)
        print(f"    COMMENT POSTED \u2713")
    else:
        d.press("enter")
        time.sleep(2)
        print(f"    COMMENT POSTED (enter) \u2713")

    record_comment(creator, username, caption)

    # ÎNCHIDE panoul de comentarii
    close_comments_panel(d)
    return True

# ═══════════════════════════════════════════════════════════
# MAIN LOOP — alternating cycles
# ═══════════════════════════════════════════════════════════
d = connect()
d.app_stop(PKG); time.sleep(2)
d.app_start(PKG); time.sleep(12)
d = connect()

if d(text="Cancel", packageName=PKG).exists(timeout=3):
    safe_click_selector(d(text="Cancel", packageName=PKG), label="startup cancel")
    time.sleep(1)
dismiss_overlays(d)
time.sleep(1)

total_follows = 0
total_comments = 0
cycle = 0
_qstate = load_query_state()
COMMENT_STATE = load_comment_history()
alfa_qi = _qstate.get("alfa_start", 0) % len(ALFA_QUERIES)
bravo_qi = _qstate.get("bravo_start", 0) % len(BRAVO_QUERIES)
print(f"[state] query start indices: ALFA={alfa_qi}, BRAVO={bravo_qi}")

# Parse --cycles argument
MAX_CYCLES_VM = None
if "--cycles" in sys.argv:
    _ci = sys.argv.index("--cycles")
    MAX_CYCLES_VM = int(sys.argv[_ci + 1])
    print(f"[Charlie] Running {MAX_CYCLES_VM} cycle(s)")

while total_follows < MAX_FOLLOWS or total_comments < MAX_COMMENTS:
    if MAX_CYCLES_VM and cycle >= MAX_CYCLES_VM:
        print(f"\\nMax cycles ({MAX_CYCLES_VM}) reached. Stopping.")
        break
    cycle += 1
    cycle_start = time.time()

    # ── ALFA PHASE: Like + Follow ──
    if total_follows < MAX_FOLLOWS:
        batch = random.randint(10, 22)
        batch = min(batch, MAX_FOLLOWS - total_follows)
        print(f"\n{'='*60}")
        print(f"CYCLE {cycle} — ALFA PHASE: {batch} like+follow (total so far: {total_follows})")
        print(f"{'='*60}")
        done_this = 0
        alfa_tries = 0
        while done_this < batch and alfa_tries < len(ALFA_QUERIES):
            q = ALFA_QUERIES[alfa_qi % len(ALFA_QUERIES)]
            alfa_qi += 1
            alfa_tries += 1
            save_query_state(alfa_qi, bravo_qi)
            print(f"\n=== Search (users): {q} ===")
            if not go_search_users(d, q):
                print("  skip query"); continue
            for scroll in range(5):
                if done_this >= batch: break
                users = get_users(d)
                error_occurred = False
                for uname, fol, following, fb in users:
                    if done_this >= batch: break
                    try:
                        ok = engage_user(d, uname, fol, following, fb)
                        if ok:
                            done_this += 1
                            total_follows += 1
                            print(f"  === [follow {done_this}/{batch} | total {total_follows}/{MAX_FOLLOWS}] ===")
                    except Exception as e:
                        print(f"  Error: {uname}: {e}")
                        ensure_home(d)
                        error_occurred = True
                        break  # restart query search
                if error_occurred:
                    break
                if done_this < batch:
                    d.swipe(540, 1800, 540, 600, duration=0.25); time.sleep(1)
        print(f"\nALFA PHASE done: {done_this} follows this batch, {total_follows} total")
        ensure_home(d)

    # ── BRAVO PHASE: AI Comments ──
    if total_comments < MAX_COMMENTS:
        batch = random.randint(13, 24)
        batch = min(batch, MAX_COMMENTS - total_comments)
        print(f"\n{'='*60}")
        print(f"CYCLE {cycle} — BRAVO PHASE: {batch} comments (total so far: {total_comments})")
        print(f"{'='*60}")
        done_this = 0
        bravo_tries = 0
        while done_this < batch and bravo_tries < len(BRAVO_QUERIES):
            q = BRAVO_QUERIES[bravo_qi % len(BRAVO_QUERIES)]
            bravo_qi += 1
            bravo_tries += 1
            save_query_state(alfa_qi, bravo_qi)
            print(f"\n=== Search (videos): {q} ===")
            if not go_search_videos(d, q):
                print("  skip query"); continue
            videos_to_browse = 10
            w, h = d.info["displayWidth"], d.info["displayHeight"]
            last_creator = None
            stuck_count = 0
            for swipe_i in range(videos_to_browse):
                if done_this >= batch: break

                # Identifică video-ul curent prin CREATOR (stabil, nu se schimbă)
                cur_creator = get_video_creator(d)
                if cur_creator and cur_creator == last_creator:
                    stuck_count += 1
                    print(f"  [stuck] Same video ({cur_creator}), extra swipe #{stuck_count}")
                    d.swipe(w // 2, int(h * 0.8), w // 2, int(h * 0.15), duration=0.2)
                    time.sleep(random.uniform(2, 3))
                    if stuck_count >= 3:
                        print(f"  [stuck] Giving up after {stuck_count} retries")
                        break
                    continue
                last_creator = cur_creator
                stuck_count = 0

                try:
                    ok = comment_on_video(d, total_comments + 1)
                    if ok:
                        done_this += 1
                        total_comments += 1
                        print(f"  === [comment {done_this}/{batch} | total {total_comments}/{MAX_COMMENTS}] ===")
                        pause = random.uniform(0.5, 1.7)
                        print(f"  Waiting {pause:.1f}s...")
                        time.sleep(pause)
                except Exception as e:
                    print(f"  Error: {e}")
                    ensure_home(d)
                    break

                # Swipe la video-ul următor (panoul de comentarii e ÎNCHIS de comment_on_video)
                if swipe_i < videos_to_browse - 1 and done_this < batch:
                    d.swipe(w // 2, int(h * 0.75), w // 2, int(h * 0.25), duration=0.15)
                    time.sleep(random.uniform(1.5, 2.5))
        print(f"\nBRAVO PHASE done: {done_this} comments this batch, {total_comments} total")
        ensure_home(d)

    # Persist rotating query state after each cycle
    save_query_state(alfa_qi, bravo_qi)

    # Check if both limits hit
    if total_follows >= MAX_FOLLOWS and total_comments >= MAX_COMMENTS:
        break

    # Close TikTok after each cycle
    print(f"\n[cycle-end] Closing TikTok after cycle {cycle}...")
    d.app_stop(PKG); time.sleep(1)
    d.press("home"); time.sleep(1)
    print("[cycle-end] TikTok closed, phone on home screen.")

    # Ensure at least 1 hour between cycle starts (skip if single cycle)
    if MAX_CYCLES_VM != 1:
        elapsed = time.time() - cycle_start
        min_cycle = 3600  # 1 hour in seconds
        if elapsed < min_cycle:
            wait_secs = min_cycle - elapsed
            wait_mins = wait_secs / 60
            print(f"\n⏳ Cycle {cycle} finished in {elapsed/60:.1f} min. Waiting {wait_mins:.1f} min until next cycle...")
            time.sleep(wait_secs)

    # Reopen TikTok for next cycle
    print(f"⏳ Reopening TikTok for cycle {cycle + 1}...")
    d.app_start(PKG); time.sleep(12)
    dismiss_overlays(d)
    if d(text="Cancel", packageName=PKG).exists(timeout=3):
        safe_click_selector(d(text="Cancel", packageName=PKG), label="cycle cancel")
        time.sleep(1)

# Exit TikTok and go to phone home screen
print("\n[cleanup] Closing TikTok...")
d.app_stop(PKG)
time.sleep(1)
d.press("home")
time.sleep(1)
print("[cleanup] TikTok closed, phone on home screen.")

print(f"\n{'='*60}")
print(f"CHARLIE FINISHED: {total_follows} follows, {total_comments} comments")
print(f"{'='*60}")
