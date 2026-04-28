#!/usr/bin/env python3
"""Kill bot processes + reset phone. Safe VM version."""
import subprocess, time

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
    if r.stdout.strip():
        print(f"  >> {r.stdout.strip()}")
    if r.stderr.strip() and "warning" not in r.stderr.lower():
        print(f"  ERR: {r.stderr.strip()}")

print("=== 1. Kill bot python processes ===")
run("ps aux | grep -E '/home/corban/charlie/(charlie|india|delta|echo|foxtrot)(_vm)?\\.py' | grep -v grep || echo 'NO_BOT_PY'")
run("ps -eo pid,args | grep -E '/home/corban/charlie/charlie_vm.py|/home/corban/charlie/india.py|/home/corban/charlie/charlie.py|/home/corban/charlie/delta_vm.py|/home/corban/charlie/echo_vm.py|/home/corban/charlie/foxtrot.py|/home/corban/charlie/delta.py|/home/corban/charlie/echo.py' | grep -v grep | grep -v 'bash -lc' | awk '{print $1}' | xargs -r kill -9 2>/dev/null || true")
run("echo ok")
time.sleep(2)
run("ps aux | grep -E '/home/corban/charlie/(charlie|india|delta|echo|foxtrot)(_vm)?\\.py' | grep -v grep || echo 'CLEAN'")

print("\n=== 2. Stop uiautomator ===")
run("adb shell am force-stop com.github.uiautomator")
run("adb shell am force-stop com.github.uiautomator.test")
run("adb shell pkill -9 -f atx-agent 2>/dev/null; echo ok")

print("\n=== 3. Stop apps ===")
run("adb shell am force-stop com.zhiliaoapp.musically")
run("adb shell am force-stop com.instagram.android")

print("\n=== 4. Phone -> Home ===")
run("adb shell input keyevent KEYCODE_HOME")
time.sleep(1)
run("adb shell input keyevent KEYCODE_HOME")

print("\n=== DONE ===")
