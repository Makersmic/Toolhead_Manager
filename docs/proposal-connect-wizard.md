# Proposal: a connecting and access wizard

Nov 23 2026. **For Mike's review: nothing is built.** Written because Mike said networking is the part he is least comfortable with, and
that people after him will be too. Follows `docs/wizard-rules.md`.

## Why

Three separate jobs that a newcomer meets as one problem ("Studio can't reach my Rhino"):

1. **Finding it.** Which address or name opens Studio from this device (`rhino.local` doesn't resolve on some Android phones), and
   whether it is on Ethernet or Wi-Fi.
2. **Letting a screen in.** Moonraker has no login: `trusted_clients` decides who can control the machine. Today the "doesn't trust this
   screen" card shows an address and a `/24` to copy, and Settings > Trusted addresses edits the list. Right, but a person has to know
   what a range is, and that "trusted" means "can press Stop and start jobs".
3. **From outside the house.** Tailscale works today (the trust page knows its range) but nothing explains it, and trusting its range
   trusts every device on the tailnet, including any shared in.

Studio already has the pieces: Settings > Network (the Rhino's name, address, Wi-Fi, with a two-minute automatic undo), Settings >
Trusted addresses (`/api/moonraker-trust`), Settings > Connection and the "doesn't trust this screen" card. What is missing is the
order, the plain words, and a check at the end.

## The wizard (five steps)

Reached from the "doesn't trust this screen" card, from Settings > Network, and from a **Connect** entry on Settings.

1. **Where am I?** Read only. Shows the address this screen used to reach the Rhino, whether it is a name or a number, whether it came
   through Tailscale, and what the Rhino says its own addresses and name are. *What this does:* the three addresses and the host name.
2. **How is the Rhino connected?** Ethernet is the sturdy choice for a machine left alone; Wi-Fi is fine if the signal is good (shows the
   level). Offers the existing name change (`rhino`) and the advice to **reserve the address in your router** rather than set a fixed one
   on the Rhino (a mistake there is the one thing that can lose the machine). Uses the existing network changes, each with the automatic
   undo. *What this does:* the exact `nmcli` setting.
3. **Who may connect?** Explains in two sentences what trusted means. Shows the current list with what each entry covers ("your home
   network, 254 addresses"). Offers **Add this screen's network** (the suggested `/24`, as the card does today). Refuses what the Portal
   already refuses (wider than `/8`, "everyone", removing the entry that lets this screen in). *What this does:* the `trusted_clients`
   lines it will write and the Moonraker restart that follows (refused during a job).
4. **From outside your home (optional).** Explains Tailscale in plain words: a private network between your own devices, no router
   changes, never port forwarding. Says whether the Rhino has it (the interface is there). The Rhino doesn't install it: a link to
   Tailscale's own steps for the host. When it is there: offers trusting the tailnet **with the warning** that every device on it,
   including shared ones, gets control, and says to restrict that in Tailscale's access rules (or only trust the devices' own
   addresses, which the wizard lists). Default is not to add anything.
5. **Check it.** From this screen: Moonraker's live link, the Portal, a camera frame, and the trust list. One line each, Good or what to do,
   ending with a link to the Health check page.

It never opens the Rhino to the internet, never suggests port forwarding, and never touches the router.

## What it needs

- **No new write routes.** It uses the existing network and trust writes (`net-*`, `trust-add`, `trust-remove`), each unchanged and each
  still refusing what it refuses today.
- **One new read route**, `GET /api/connect/check`: what the Portal sees: the address the request came from, the host's addresses and
  name, whether `tailscale0` exists, the interface in use (Ethernet or Wi-Fi) and its signal. Read only, no token.
- Studio: `src/views/ConnectWizardView.vue` on the shared wizard shell, `src/connect/steps.ts` (plain logic with tests: explain a
  range, classify an address, build the check lines), mascot poses for the five steps.
- Not a G-code wizard: the editable-text rule applies to the one block it writes (the `trusted_clients` lines), shown in step 3 with
  **Edit**, checked by the same code (`rhino/trust.py`) before it is written.

## Tests and checks

- Unit tests for the plain logic; Portal test for `GET /api/connect/check` (including a request through a Tailscale-range address);
  headless run against the mock: each step, light and dark, desktop, phone and 760 px, one screenshot round.
- On the machine (`docs/testing.md`, new section): CW1 the wizard opens from the card; CW2 step 1 matches `ip addr` over SSH; CW3 adding
  this screen's network from a screen that is not yet trusted is impossible (the Portal only answers trusted screens) and says so;
  CW4 the final check is Good on a healthy machine and names the right thing with Moonraker stopped (`sudo systemctl stop moonraker`,
  machine idle, then start it again); each with a pass condition and a *Stop if*.

## Decided Nov 23 (Mike: "whatever you recommend")

Step 4 only explains Tailscale and adds nothing unless chosen; router wording is generic; the wizard is shown only from its entry points,
not at first start. Question 1 below is kept as the record.

## Open questions for Mike

1. Should step 4 offer to trust a tailnet at all, or only explain and point to the access rules? (Mike, Nov 23: Tailscale is fine
   as it is today. The wizard would keep today's behaviour: nothing added unless chosen.)
2. Router wording: generic ("find DHCP reservation or address reservation in your router") or a page per common router? Generic is
   proposed: router menus change too often to keep right.
3. Show it once on first start? Proposed: no, only the entry points above.

## Order and size

Smaller than the Add a toolhead wizard: one read route and one view. Suggested order across wizards: this one, then updating safely
(with the health check inside it), then the park spot wizard (its own proposal: `positions.cfg` is never written by the Portal).
