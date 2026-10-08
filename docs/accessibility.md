# Accessibility audit: Tool Manager portal

**Standard:** WCAG 2.1 AA | **Date:** 8 October 2026 | **Version:** 1.3.9

How it was checked: axe-core 4.10 on every screen and dialog (12 sidebar screens, a tool page, the editor, the
Add-a-tool wizard, task Details and Log work: 30 page states), in Mainsail's dark and light themes, desktop and phone,
on the demo portal with a year of data. Then keyboard-only use, focus order and visibility, dialogs, touch targets,
reflow at 320 px wide, text at 200 % and reduced motion, scripted in headless Chromium. Not done: a real screen reader
(VoiceOver/NVDA); worth a pass on a phone with VoiceOver.

The scan and the keyboard checks now run in `dev/test_browser.py` on every push, so these can't come back unnoticed.

## Summary

**Found:** 13 issues - 2 critical, 7 major, 4 minor. **All fixed in 1.3.9.** axe-core: 97 violations before, 0 after,
in both themes.

### Perceivable

| # | Issue | WCAG | Severity | Fix |
|---|---|---|---|---|
| 1 | Text below 4.5:1 contrast: Built-in/Starter badges (dark), the red photo note on tool pages (dark), Delete buttons, the maintenance chip and pin warnings (light), fold-out links (light) | 1.4.3 | 🟡 Major | Colours changed (table below) - same hues, darker or lighter shade |
| 2 | Dashboard charts were `role="img"` with no name, and the bars inside them carried labels the role hides | 1.1.1, 4.1.2 | 🟡 Major | Each chart is a named group ("Hours by toolhead - press Table for the numbers"); each bar is an image with its value |
| 3 | Task Library cards were 340 px wide on a 320 px screen (sideways scrolling) | 1.4.10 | 🟢 Minor | Cards shrink to the screen width |

### Operable

| # | Issue | WCAG | Severity | Fix |
|---|---|---|---|---|
| 4 | Dialogs: focus stayed on the page behind when a dialog opened, Tab walked out of it, and after closing focus was lost | 2.4.3 | 🔴 Critical | Every dialog moves focus to its first field, keeps Tab inside, and gives focus back to the button that opened it (Escape still closes the top one) |
| 5 | No way to skip the 18 sidebar buttons | 2.4.1 | 🟡 Major | "Skip to content" link, shown when it gets focus |
| 6 | Scrolling tables (pins, work log, tool pages) could not be scrolled with the keyboard | 2.1.1 | 🟡 Major | Each is a focusable, named region |
| 7 | Maintenance chip (23 px) and Admin fold-out links (20 px) were small touch targets | 2.5.8 (2.2) | 🟢 Minor | 24 px minimum |
| 8 | No reduced-motion setting | 2.3.3 (AAA) | 🟢 Minor | Transitions off when the system asks for less motion |

### Understandable

| # | Issue | WCAG | Severity | Fix |
|---|---|---|---|---|
| 9 | 46 form fields had a visible label that wasn't tied to the field (one shared cause: the `field()` builder) | 3.3.2, 1.3.1 | 🔴 Critical | `field()` links label and field, and the hint below it is read as the field's description |
| 10 | Log work's "What happened?" drop-down had no name | 4.1.2 | 🟡 Major | Fixed by #9 |

### Robust

| # | Issue | WCAG | Severity | Fix |
|---|---|---|---|---|
| 11 | Status-code name fields and the photo upload had no name | 4.1.2 | 🟡 Major | Named ("Name shown for overdue", "Add photos") |
| 12 | The sidebar showed the current screen only by colour | 4.1.2, 1.4.1 | 🟢 Minor | `aria-current="page"` on the current screen |
| 13 | - | - | - | Already good: `lang`, landmarks (header, nav, main), one heading per screen, error boxes `role="alert"`, toasts `role="status"`, status chips `aria-live`, icon buttons named, tool cards are buttons, chart bars reachable by Tab with a visible focus outline and a Table view for every chart |

## Colour contrast

| Element | Before | Ratio | After | Ratio | Background | Required |
|---|---|---|---|---|---|---|
| Built-in/Starter badge (dark) | #9a9ca6 | 4.06 ❌ | #e3e4e6 | 8.72 ✅ | #3a3b46 | 4.5 |
| Tool page photo note (dark) | #d32f2f | 3.76 ❌ | #ef9a9a | 8.71 ✅ | #121212 | 4.5 |
| Delete button text | #000000 | 4.22 ❌ | #ffffff | 4.98 ✅ | #d32f2f | 4.5 |
| Delete button, hover (dark) | #ffffff on #f44336 | 3.68 ❌ | #ffffff on #b52424 | 6.48 ✅ | - | 4.5 |
| Maintenance chip (light) | #c88400 | 3.11 ❌ | #7a4f00 | 7.13 ✅ | #ffffff | 4.5 |
| Pin warning hint (light) | #c88400 | 2.93 ❌ | #7a4f00 | 6.73 ✅ | #fcf8f0 | 4.5 |
| Fold-out link (light) | #1b7bc7 | 4.46 ❌ | #1a78c2 | 4.66 ✅ | #ffffff | 4.5 |

The fold-out link follows Mainsail's primary colour (80 % of it, darkened). With the default blue it passes; a very
light primary colour chosen in Mainsail could bring it under 4.5:1 again.

## Keyboard

| Element | Tab | Enter/Space | Escape | Notes |
|---|---|---|---|---|
| Skip link | First stop | Jumps to the screen | - | Hidden until focused |
| Sidebar | In order | Opens the screen | - | Current screen announced |
| Group headings (Tools, Hardware...) | In order | Fold/unfold | - | `aria-expanded` |
| Chart bars | Each bar | - | - | Value shown and announced; Table button gives all numbers |
| Dialogs | Focus moves in; stays in | Buttons work | Closes the top dialog | Focus returns to the opener |
| Scrolling tables | Focusable | - | - | Arrow keys scroll |

## Priority fixes (all done in 1.3.9)

1. **Form labels (#9)** - every field in the editor, wizard, maintenance and Admin screens is now announced by name.
2. **Dialog focus (#4)** - keyboard and screen-reader users can use every dialog without losing their place.
3. **Contrast (#1)** - readable warnings and badges in both themes, in a bright shop.
