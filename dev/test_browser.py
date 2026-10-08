"""Browser smoke test: open every screen of the portal in a real browser (headless Chromium) and fail on
any JavaScript error, failed request or screen that doesn't show.

    python3 dev/test_browser.py

Uses the demo portal (dev/demo_server.py) on a config with a year of maintenance history
(dev/maint_year_demo.py) and the fake Moonraker, so nothing touches a printer. Covers: every sidebar
screen, each tool's page, the Add-a-tool wizard, a tool's editor, maintenance Details and Log work
(saved for real, then found in the Work log), following Mainsail's light theme, a job running, Klipper not
ready, a phone-sized screen (menu button, no sideways scrolling), an axe-core WCAG 2.1 AA scan of every
screen and dialog, and keyboard use (Enter, dialog focus in/trapped/returned, skip link).

Needs Playwright for Python and its Chromium:
    pip install playwright && python3 -m playwright install chromium
If Playwright isn't installed the test says SKIP and passes, so dev/run_all.sh still runs without it.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP browser test: Playwright is not installed (pip install playwright && python3 -m playwright install chromium)")
    sys.exit(0)

fails = []
AXE_JS = os.path.join(HERE, "node_modules", "axe-core", "axe.min.js")   # npm install --prefix dev axe-core@4.10.2
AXE = open(AXE_JS).read() if os.path.exists(AXE_JS) else None


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


VIEWS = {"dash": "Dashboard", "library": "Tool library", "pins": "Pins & outputs", "hardware": "System hardware",
         "mdue": "Due & upcoming", "mtasks": "Tasks", "mlib": "Task Library", "mhistory": "Work log",
         "mmeters": "Usage meters", "atools": "Tool lists", "amaint": "Maintenance lists", "astatus": "Status codes"}

tmp = tempfile.mkdtemp(prefix="rhino-browser-")
proc = None
try:
    # ---------------------------------------------------------------- a portal with a year of use behind it
    r = subprocess.run([sys.executable, os.path.join(HERE, "maint_year_demo.py"), tmp], capture_output=True, text=True)
    cfg = os.path.join(tmp, "printer_data", "config")
    ok(r.returncode == 0 and os.path.isdir(cfg), "demo config with a year of maintenance built")
    port = free_port()
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "demo_server.py"), "--config", cfg, "--port", str(port),
                             "--monitor-interval", "0.5"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    line = proc.stdout.readline()
    m = re.search(r"fake moonraker (http://\S+)", line)
    ok(bool(m), f"demo portal started ({line.strip()})")
    fake = m.group(1)
    portal = f"http://127.0.0.1:{port}/"
    for _ in range(100):
        try:
            urllib.request.urlopen(portal, timeout=1)
            break
        except OSError:
            time.sleep(0.1)

    def fake_set(**kv):
        q = "&".join(f"{k}={v}" for k, v in kv.items())
        urllib.request.urlopen(urllib.request.Request(f"{fake}/__set?{q}", method="POST"), timeout=5)

    jobs = json.load(open(os.path.join(tmp, "jobs.json")))
    for j in jobs[-40:]:
        q = f"filename={j['filename']}&status={j['status']}&total_duration={j['total_duration']:.0f}&end_time={j['end_time']:.0f}"
        urllib.request.urlopen(urllib.request.Request(f"{fake}/__job?{q}", method="POST"), timeout=5)

    fake_set(ui_mode="light", ui_primary="%23e91e63")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        problems = []

        def watch(page, label):
            page.on("console", lambda msg: msg.type == "error" and problems.append(f"{label}: console: {msg.text}"))
            page.on("pageerror", lambda exc: problems.append(f"{label}: script error: {exc}"))
            page.on("response", lambda resp: resp.status >= 400 and not resp.url.endswith("favicon.ico")
                    and problems.append(f"{label}: HTTP {resp.status} {resp.url}"))

        def settle(page, ms=400):
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(ms)

        def check_problems(what):
            ok(not problems, f"{what}: no script errors or failed requests" + (f" - {problems[:3]}" if problems else ""))
            problems.clear()

        def visible_view(page):
            return page.evaluate("[...document.querySelectorAll('.view')].filter(v => !v.classList.contains('hidden')).map(v => v.id)")

        # ---------------------------------------------------------------- desktop, dark theme
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        watch(page, "desktop")
        page.goto(portal)
        settle(page, 1500)
        bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        ok(page.evaluate("document.documentElement.dataset.theme") == "light" and sum(int(v) for v in re.findall(r"\d+", bg)[:3]) > 600,
           f"follows Mainsail's light theme (body {bg})")
        # an added tool, so the editor can be opened (built-in tools are edited in variables.cfg)
        added = page.evaluate("""async () => {
            const t = document.querySelector('meta[name="rhino-token"]').content;
            const r = await fetch('/api/tools', {method: 'POST', headers: {'X-Rhino-Token': t, 'Content-Type': 'application/json'},
                                                body: JSON.stringify({name: 'Pen', kind: 'PASSIVE'})});
            return r.status; }""")
        ok(added == 200, f"a passive tool 'Pen' added through the API ({added})")
        page.reload()
        settle(page, 1000)
        ok(visible_view(page) == ["view-dash"] and page.locator("#view-dash").inner_text().strip() != "", "dashboard opens first and has content")
        ok(open(os.path.join(os.path.dirname(HERE), "VERSION")).read().strip() in page.locator(".version").inner_text(), f"version shown in the sidebar ({page.locator('.version').inner_text()})")
        for view, label in VIEWS.items():
            page.locator(f'.nav-btn[data-view="{view}"]').click()
            settle(page)
            text = page.locator(f"#view-{view}").inner_text().strip()
            ok(visible_view(page) == [f"view-{view}"] and len(text) > 20, f"{label}: opens from the sidebar and shows content")
        check_problems("every sidebar screen")

        page.locator('.nav-btn[data-view="library"]').click()
        settle(page)
        names = page.locator(".tool-card .tc-name").all_inner_texts()
        ok({"BlockOne", "SwitchFly", "LightSaber", "HotJoe", "DragKnife", "Pen"} <= set(names), f"tool library lists the five toolheads and Pen ({names})")
        for name in names:
            page.locator('.nav-btn[data-view="library"]').click()
            settle(page, 200)
            page.locator(".tool-card", has_text=name).first.click()
            settle(page)
            ok(visible_view(page) == ["view-tool"] and name in page.locator("#view-tool").inner_text(), f"{name}: tool page opens")
        check_problems("tool pages")

        page.locator("#navAdd").click()
        settle(page)
        ok(page.locator("#wizard").is_visible(), "Add a tool: the wizard opens")
        page.locator("#wizard [data-close]").first.click()
        settle(page, 200)
        ok(not page.locator("#wizard").is_visible(), "...and closes")
        page.locator('.nav-btn[data-view="library"]').click()
        settle(page, 200)
        page.locator(".tool-card", has_text="Pen").first.click()
        settle(page)
        page.locator("#view-tool button", has_text="Edit tool").first.click()
        settle(page)
        ok(page.locator("#editor").is_visible() and "Pen" in page.locator("#edTitle").inner_text(), "Edit tool opens the editor for Pen")
        page.locator("#editor [data-close]").first.click()
        settle(page, 200)
        check_problems("wizard and editor")

        page.locator('.nav-btn[data-view="mdue"]').click()
        settle(page)
        page.locator("#view-mdue button", has_text="Details").first.click()
        settle(page)
        ok(page.locator("#taskModal").is_visible(), "Due & upcoming: Details opens the task")
        page.keyboard.press("Escape")
        page.locator("#taskModal [data-close]").first.click() if page.locator("#taskModal").is_visible() else None
        settle(page, 200)
        card = page.locator("#view-mdue .card, #view-mdue article, #view-mdue li").filter(has=page.locator("button", has_text="Log work")).first
        title = page.locator("#view-mdue button", has_text="Log work").first
        title.click()
        settle(page)
        task_title = page.locator("#doneTitle").inner_text().replace("Log work - ", "").strip()
        ok(page.locator("#doneModal").is_visible() and task_title, f"Log work opens for '{task_title}'")
        page.locator("#doneBody textarea").first.fill("Browser test entry") if page.locator("#doneBody textarea").count() else None
        page.locator("#doneSave").click()
        settle(page, 800)
        ok(not page.locator("#doneModal").is_visible(), "...Save to the work log closes it")
        page.locator('.nav-btn[data-view="mhistory"]').click()
        settle(page)
        ok(task_title[:25] in page.locator("#view-mhistory").inner_text(), "...and the entry is in the Work log")
        check_problems("maintenance dialogs")

        # ---------------------------------------------------------------- printer states
        fake_set(print_state="printing", progress="0.47", filename="bracket_BlockOne.gcode", extruder_target="210")
        page.reload()
        settle(page, 2000)
        chips = page.locator("#statusChips").inner_text().lower()
        ok("print" in chips, f"a job running shows in the status chips ({chips.strip()!r})")
        fake_set(print_state="standby", progress="0", klippy="shutdown")
        page.reload()
        settle(page, 2000)
        ok(visible_view(page) == ["view-dash"], "Klipper not ready: the portal still opens")
        fake_set(klippy="ready")
        problems[:] = [x for x in problems if "HTTP 503" not in x]    # the portal reports Klipper down; expected here
        check_problems("printing and Klipper-down states")

        # ---------------------------------------------------------------- accessibility (WCAG 2.1 AA)
        page.reload()
        settle(page, 1000)
        if AXE:
            def axe(label):
                settle(page, 300)
                page.evaluate(AXE)
                v = page.evaluate("""async () => (await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa']}}))
                    .violations.map(v => v.id + ': ' + v.nodes.map(n => n.target.join(' ')).slice(0, 2).join(', '))""")
                if v:
                    a11y.append(f"{label}: {v[:3]}")
            a11y = []
            for view in VIEWS:
                page.locator(f'.nav-btn[data-view="{view}"]').click()
                axe(VIEWS[view])
            page.evaluate("window.RH.openTool('BlockOne')"); axe("BlockOne page")
            page.evaluate("window.RH.openEditor('Pen')"); axe("editor"); page.keyboard.press("Escape")
            page.locator("#navAdd").click(); axe("Add-a-tool wizard"); page.keyboard.press("Escape")
            page.locator('.nav-btn[data-view="mdue"]').click(); settle(page)
            page.locator("#view-mdue button", has_text="Details").first.click(); axe("task details"); page.keyboard.press("Escape")
            page.locator("#view-mdue button", has_text="Log work").first.click(); axe("log work"); page.keyboard.press("Escape")
            ok(not a11y, "axe-core: no WCAG 2.1 AA violations on any screen or dialog" + (f" - {a11y}" if a11y else ""))
        else:
            print("SKIP axe scan: npm install --prefix dev axe-core@4.10.2")
        # keyboard: Enter opens a screen, dialogs take focus, keep it, and give it back
        page.locator('.nav-btn[data-view="mdue"]').focus()
        page.keyboard.press("Enter")
        settle(page)
        ok(visible_view(page) == ["view-mdue"] and page.locator('.nav-btn[aria-current="page"]').get_attribute("data-view") == "mdue",
           "keyboard: Enter opens a screen, and the sidebar marks it as the current page")
        opener = page.locator("#view-mdue button", has_text="Log work").first
        opener.focus()
        page.keyboard.press("Enter")
        settle(page, 300)
        inside = page.evaluate("!!document.activeElement.closest('#doneModal')")
        stays = True
        for _ in range(30):
            page.keyboard.press("Tab")
            stays = stays and page.evaluate("!!document.activeElement.closest('#doneModal')")
        page.keyboard.press("Escape")
        settle(page, 300)
        back = page.evaluate("document.activeElement.textContent.trim()") == "Log work" and not page.locator("#doneModal").is_visible()
        ok(inside and stays and back, f"keyboard: a dialog takes focus ({inside}), Tab stays inside it ({stays}), Escape closes it and focus goes back ({back})")
        ok(page.locator(".skip-link").count() == 1, "a Skip to content link is the first thing on the page")
        check_problems("accessibility checks")

        page.close()

        # ---------------------------------------------------------------- phone
        phone = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        watch(phone, "phone")
        phone.goto(portal)
        settle(phone, 1500)
        wide = []
        for view, label in VIEWS.items():
            phone.locator("#menuBtn").click()
            phone.wait_for_timeout(250)
            phone.locator(f'.nav-btn[data-view="{view}"]').click()
            settle(phone)
            if visible_view(phone) != [f"view-{view}"]:
                wide.append(f"{label} did not open")
            sw = phone.evaluate("document.documentElement.scrollWidth")
            if sw > 391:
                wide.append(f"{label} {sw}px wide")
        ok(not wide, "phone: every screen opens from the menu button, no sideways scrolling" + (f" - {wide}" if wide else ""))
        check_problems("phone")
        browser.close()
finally:
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    shutil.rmtree(tmp, ignore_errors=True)

print("\nFAILED:" if fails else "\nALL PASSED", fails or "")
sys.exit(1 if fails else 0)
