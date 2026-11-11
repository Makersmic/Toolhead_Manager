# Phase: Help in Rhino Studio (the manual as web pages)

Nov 11 2026. **Built Nov 11 (first batch, steps 1-4), not released yet.** Mike (Nov 11): add Help to Settings and turn the user guide's pages
into web pages, interactive where that applies. "Nothing sucks more than a lost user guide."

## Why

A printed manual gets lost. A PDF on GitHub needs the internet, and GitHub, to still be there. Help that ships inside
every release zip is on the Rhino itself, works with no internet, and always describes the version that's installed.
That is the durability goal in one feature: someone who comes back after months away finds the guide where the
machine is.

## What it is

- **Settings › Help**: the contents, then one page per chapter, readable on a phone. A search box over every page.
- **"?" on each screen**: a small link in the screen's title line that opens its own chapter (Bed › the Bed chapter,
  Tune › Tuning a print head). The most useful part: help where the question comes up.
- **Download PDF**: the printable manual stays, for the shop wall and for when Studio itself won't open.

## One source, two outputs

The manual is already HTML: chapter fragments in `manual/src/*.html`, plus pages `manual/build.py` generates in Python
(machine, wiring, tool sheets, Portal, maintenance) from `his_data.py`. Help is a second output of the same build, so a
chapter is edited once and both change.

- `python3 manual/build.py --web manual/web` writes one HTML fragment per chapter, an `index.json` (titles, order,
  section anchors, plain text for search) and web copies of the pictures.
- The pictures are 39 MB for print. Web copies: WebP, at most 1000 px wide, about 3-5 MB in all. The build fails if
  Help passes 6 MB, so the zip and the Pi's SD card don't grow quietly.
- Print-only parts (cover, page numbers, the contents page, blank-page fillers) are left out of the web output.
- `manual/web/` is committed, like the PDF, so a release doesn't need the manual's build tools in CI. `index.json`
  holds a fingerprint of the sources (chapters, build scripts, pictures); `dev/test_help.py` fails when they change
  without rebuilding Help.
- The release copies `manual/web/` into Studio's site as `help/`. Studio reads `./help/index.json` at runtime, so
  Help comes from the zip on the machine, never from the internet.

## Safety

- Help only reads and links. It never runs a command: the wizards already do that, and a second way to drive the
  machine would be a second path around the safety model.
- The chapter HTML is ours, but it's still cleaned at build time to a short list of tags (headings, paragraphs, lists,
  tables, images, links, `b`/`i`/`code`) with no scripts, styles or event attributes. Studio shows only what passed.
- Links inside Help either open a Studio screen (`#/...`) or another Help page. No outside links except the GitHub
  release page for the PDF.

## Interactive, where it helps

| Feature | What it does | When |
|---|---|---|
| Search | Finds words across every chapter, with the section to jump to | First batch |
| "Open this screen" | A step that names a screen links to it | First batch |
| "?" per screen | Opens that screen's chapter at the right section | First batch |
| Tick-off lists | Checklists (first start, a tool swap, a long idle) you can tick; kept only in that browser | Second batch |
| Your machine beside the text | The tools chapter lists your tools and versions; Care shows what's due, read from the Portal | Second batch |

Not planned: animations, videos inside the zip (size), or anything that moves the machine.

## How it's built (Studio)

- `src/help/` plain TypeScript: the index loader, search, and `HELP_FOR` (route → chapter and section), with tests.
  A test checks that every `HELP_FOR` target exists in `index.json`.
- `HelpView.vue` (contents, chapter page, search) and a small `HelpLink.vue` for the "?" in a screen's title line.
- The style rules stay the same: Archivo, ink and paper, light and dark, phone width.

## Order of work

1. `build.py --web`: fragments, index, WebP pictures, size check, staleness test. Check the output in a browser.
2. Studio Help: contents, chapter pages, search, Download PDF. Screenshots in light and dark, phone and desktop.
3. "?" links on the main screens (Control, Job setup, Bed, Files, Assets, Care, Settings, Tune).
4. Release wiring: copy `manual/web/` into Studio's site; check it on the machine (`docs/testing.md`).
5. Second batch: tick-off lists, your machine beside the text.

## Mike's answers (Nov 11 2026)

1. Download PDF: a link to the PDF on GitHub (the zip stays small). Help itself works offline.
2. One **?** in the top bar, opening the current screen's chapter; Settings › Help for the contents.

## Built (first batch)

- Tool Manager: `manual/web.py`, `manual/web/`, `dev/test_help.py`, `dev/make_zip.sh` copies Help into Studio,
  `service/rhino-studio.nginx` answers a missing Help page with 404 (checked in `dev/test_studio_site.py`).
- Studio: `src/help/help.ts` (+ tests, one against the real manual when the repos sit side by side), `HelpView.vue`,
  the top bar's **?**, the dev server serving `/help` from `../Toolhead_Manager/manual/web` (or `HELP_DIR`).
- On-machine checks: Studio `docs/testing.md` HP1-HP3.
- Not yet: the laser and knife tuning chapter (the manual itself doesn't have it yet: `notes/manual-notes.md`), tick-off
  lists and your machine beside the text (second batch).
