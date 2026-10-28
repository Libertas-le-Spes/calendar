# Security review

This review covers the repository at commit `1b1a4983bf617485fe223fab6a11f1eb5113d9e0` (release 0.7.0), read on 2026-10-22.
The code will keep changing, and this document with it. When you change something this document describes, update the
document in the same pull request. Every example below uses made-up names, addresses and times.

**Status, 2026-10-28.** Every finding is fixed on the branch `security-review-calendar`: F1 to F11 from this review, and
N1 to N8 from a second, independent review that looked for what this one missed. The table below says what was done
for each one. In four places the fix differs from what this review first recommended:

- **F1-B, lazy expansion.** `recurring-ical-events`' `after()` walks forward in steps that shrink to 15 minutes while
  any event is still going on. An event lasting a thousand years is going on in every step, so the open-ended walk
  never ends: it is a way to hang the sync, not a cure. Expansion stays a closed window (`between()`), and each repeat
  rule's cost is worked out from the rule before anything is expanded (`repeat_cost.py`).
- **F1-D, the contract ceiling.** Refusing the whole document over one oversized event would let that event stop every
  calendar from updating, which is N1. The ceiling is still in `contract.validate`, but the sync drops each row that
  breaks the contract before the check, so only a document too large as a whole is refused.
- **F1-B, the cost estimate.** It first trusted a rule's `COUNT`, which limits the dates kept, not the dates tried, so a
  rule that can never match ("every hour on 30 February") was costed at 1 and took seconds to expand. It also counted a
  yearly birthday from 1970 as one step a day, so a normal birthdays feed was skipped. The estimate now counts periods
  and ignores `COUNT`, and a 10-second budget per calendar stops whatever the estimate misses.
- **N4, duplicate events.** Preferring a copy from a calendar the user can write was considered and left out: anyone can
  share a calendar and grant write access. Only the primary calendar counts as the user's own.

## What this project is, in one paragraph

The plugin replaces the clock in the Omarchy bar. It has two halves. The **widget** (the QML and JavaScript files at the root)
draws the clock, the month panel and the reminders. The **sync** (the Python package under `sync/`) runs every five minutes
from a systemd user timer. It reads the user's calendars from one of three places: Google through the `gws` command, Evolution
Data Server, or iCal feed addresses. It then writes everything to one file, `~/.local/state/omarchy/calendar-events.json`,
which the widget watches. When writing is turned on, the panel also runs a small command (`sync/omarchy-calendar-event`) to
create, edit and delete events on Google.

The trust boundary that matters most is simple. **Everything in a calendar event can be written by someone other than the
user.** Anyone who sends an invitation, shares a calendar, or publishes a feed the user subscribes to chooses the title,
location, description, links, dates and repeat rule.

## Verdict

The code is careful, and it is clearly written by someone who thought about this boundary. No shell is used anywhere: every
process is started from an argument list. Event requests and secret feed addresses travel on stdin, not as arguments that
other users could see with `ps`. Every place that shows event text uses plain text, so nobody can inject markup into the panel.
Only `https` links are ever opened, and the sync and the widget agree on that rule. The events file is written atomically with
mode 600.

The one serious gap is **size**. Nothing limits how much work one calendar entry can cause. A single event with an absurdly
long span, or a repeat rule that fires every second, makes the sync write hundreds of megabytes, and the bar then has to load
all of it. Whoever can put an event in a synced calendar can do this, so it is rated **High** (F1). Everything else is Low or
Informational.

## Findings

| ID  | Severity | Title | Location |
|-----|----------|-------|----------|
| F1  | High     | One calendar entry can make the sync write hundreds of megabytes and stall the bar | `sync/omarchy_calendar_sync/normalize.py:203`, `ics.py:162`, `ics.py:350`, `contract.py:441`, `BarWidget.qml:59` |
| F2  | Low      | Plain `http://` feeds are accepted, so the secret address and the events travel unencrypted | `sync/omarchy_calendar_sync/ics.py:60`, `ics.py:87` |
| F3  | Low      | A failing feed can print its secret address into the journal | `sync/omarchy_calendar_sync/ics.py:314` |
| F4  | Low      | Secret feed addresses sit in a plain JSON file whose mode nobody checks | `sync/omarchy_calendar_sync/config.py:42`, `sync/setup:478`, `README.md` (by-hand config) |
| F5  | Low      | A reminder's text can carry formatting tags into the notification card | `Model.js:1075`, `Reminders.qml:148` |
| F6  | Low      | Calendar ids (email addresses) appear in process arguments every five minutes | `sync/omarchy_calendar_sync/gws.py:183`, `gws.py:194` |
| F7  | Low      | A long guest name from someone's invitation can push the real email address out of view | `GuestList.qml:117`, `sync/omarchy_calendar_sync/suggestions.py:256` |
| F8  | Info     | Join opens any `https` link the event carries, including the next meeting's on a middle click | `Model.js:456`, `BarWidget.qml:94` |
| F9  | Info     | No CI, and the safety rules the code follows are not enforced by any test | repository (no `.github/`) |
| F10 | Info     | No minimum version for `python-icalendar`, which has had denial-of-service fixes in 2026 | `sync/omarchy_calendar_sync/ics.py:47` |
| F11 | Info     | Setup leaves the client secret readable for a moment, and the profile folder open to others | `sync/setup:372` |

What was done, and what each fix still fails to stop:

| ID  | Fixed by | Still not stopped |
|-----|----------|-------------------|
| F1  | Rows stop at the window (at most 366 days each way). Each feed is parsed, costed, expanded and converted in a process of its own, limited to 768 MB of address space and 60 seconds (less when the run's four minutes are nearly used); it clips every text before answering, and the sync reads that answer only up to 64 MB and drops each feed body once answered, so a feed costs only itself. The sync's own process never parses a feed: it reads a feed's name and colour from its header lines, folded or not. Inside that process, each series is first costed from its rule (periods walked up to the window's end or its UNTIL, COUNT ignored) and from the dates it lands in the window; a series over 200,000, or one that cannot be read, is left out; plain events outside the window are dropped; a calendar estimated over 20,000 dates in the window is refused before expanding; series are expanded one at a time, so one that raises is left out alone; and the exact 2,000-event check follows. A feed over 16 MB is refused. The file holds at most 8,000 rows and 16 MB, every text field has a length limit, and a calendar whose rows would pass either ceiling is skipped as a whole. The widget refuses a file over those ceilings, counted in UTF-8 bytes, before parsing it. Measured under the unit's 1.5 GB: 130,000 alarm blocks in 3.4 MB leave that series out with the child at 703 MB; a 15 MB CATEGORIES line costs only its calendar; the sync's own process stays under 120 MB, and five 1 MB feeds that each answer 250 copies of a 1 MB description leave it at 60 MB. | A calendar flooded with events, or with events that last for months, is skipped as a whole, so its real events go too. EDS expansion runs in C in the sync's own process, so only the unit's 5-minute stop and 1.5 GB limit it. The journal names the calendar in each case. |
| F2  | One `https`-only opener (`web.py`): no handler for any other scheme, and a redirect is followed only to another `https` address. Setup and the sync share one address rule: `https`, a host, no user name or password, no spaces, control characters or backslashes. | Nothing found. |
| F3  | Every failure is caught per feed. Only the sync's own messages, or the error's kind, are printed. `redact()` keeps scheme and host only, and every printed line has the address's path and query removed as a last layer. | Nothing found. |
| F4  | `setup --ics` stores each address in the keyring; the config names it by id. When the keyring refuses, setup asks before writing the address into the config instead (default: no). Every config is created 600, fresh, never through a link. The sync refuses a config another user owns or can change, one in a folder others can change, and one others can read while it holds a plain address, each with its own remedy. Choosing the Google sync drops the feeds from the config and the keyring. | Programs running as the user can still ask the keyring while it is unlocked. |
| F5  | The reminder body is escaped. | Nothing found. |
| F6  | Reads go to the Calendar API over HTTPS, like writes. `gws` is asked only for its version and the sign-in. | The sign-in passes through the sync's memory on every run, not only on writes. |
| F7  | The address comes first in a suggestion; names are kept to 100 characters and addresses to 254. | Nothing found. |
| F8  | Join names the service only for known meeting hosts, else the host the link really opens if it is short enough to show whole (40 characters) and in plain letters, else nothing. A reminder names a known service, then the room, then the host. | A user who clicks through a link to a host they do not know. |
| F9  | `.github/workflows/tests.yml` runs both suites, read only, pinned by commit and digest. `tests/test_architecture.py` holds the plain-text rule, the no-shell rule and the workflow's own terms. | A rule nobody has written down as a test yet. |
| F10 | The sync refuses `python-icalendar` older than 7.2.2. | Nothing found. |
| F11 | The profile is created 700 under a private umask, and the client secret installed 600 in one step, from the newest download. | Nothing found. The README's install command still names tmn73's repository: deciding which repository installs track is left to the owner. |
| N1  | See below. Also: a series whose dates, rule or exceptions cannot be read is left out on its own, an event that cannot be converted costs only itself, and a feed that exhausts its process's memory or time costs only that feed. | Nothing found. |
| N2  | A feed has 60 seconds in all to arrive, timed by the process's interval timer, which also interrupts a read waiting on a server that sends a byte at a time; it is read in pieces of up to 64 KB. Reading it then has 60 seconds in its own process, less when there are many feeds, so all of them fit in the run. `gws` has 60 seconds; the unit stops a run after 5 minutes, 1.5 GB of memory with no swap to spill into, or 64 tasks. | An EDS call that hangs costs the whole run, until the unit stops it. |
| N3  | The link rule refuses a user name and a backslash; Jitsi means `meet.jit.si`. Both suites test the same list of cases (`tests/fixtures/link-cases.json`). | Nothing found. |
| N4  | A copy is dropped only when it says the same as the first one (title, end, link, location, description and reminders), or the first is in the primary calendar. | A copy in the primary calendar still wins over any other. |
| N5  | Every `python3` in setup runs with `-I`. | Nothing found. |
| N6  | At most 64 KB of a description is read. | Nothing found. |
| N7  | The unit runs with no new privileges, `/usr` and `/etc` read only, a private `/tmp`, a system-service syscall set and four socket families. `systemd-analyze security` goes from 9.2 to 5.8. | Reading the user's other files and sending them out; home stays writable because `gws` keeps its sign-in in whichever profile the config names. |
| N8  | Google requests carrying the token follow no redirect at all. | Nothing found. |

---

### F1 (High): one calendar entry can make the sync write hundreds of megabytes and stall the bar

**What it is.** The sync turns each event into one row per day it covers. That is how the month grid knows which days to mark.
It also expands repeating events into one row per occurrence inside the sync window (7 days back, 60 days ahead).

**The point.** None of these steps has a limit, and all of them are driven by data from outside:

- How many days an event covers is taken from the event itself, and the row loop is not clipped to the sync window
  (`normalize.py:203`, `_covered_days`). An event that starts this year and ends far in the future becomes one row for every
  day of that span.
- A repeat rule is expanded in full before anything can count it (`ics.py:350`, `rie.of(calendar).between(...)` returns a
  list). A rule that repeats every second yields 86,400 occurrences for each day of the window.
- The feed body is read whole, with no size cap (`ics.py:165`, `response.read()`).
- The contract check accepts any number of rows (`contract.py:441`), and the widget parses whatever file it finds
  (`BarWidget.qml:59`).

**Who can trigger it.** Anyone who can put one event into a calendar the sync reads: the person who publishes a subscribed
feed, anyone the user shares a calendar with, and anyone who sends an invitation that Google adds to the calendar
automatically. Whether an invitation from a stranger is added on its own depends on the Google account's "Add invitations to
my calendar" setting. Several universities have moved it to "Only if the sender is known", but that is set per account or
per organisation ([Mount Holyoke](https://lits.mtholyoke.edu/node/5209), [Brown](https://ithelp.brown.edu/kb/articles/2235)).

**What happens in practice.** Measured with a made-up feed and the real sync code (`cli.run`, a fake fetch, no network):

| The made-up event | Rows written | Events file | Sync time |
|---|---|---|---|
| A normal one-hour meeting | 1 | under 1 KB | instant |
| One all-day event spanning 1,000 years | 365,242 | 193.6 MB | 2.9 s |
| One event repeating every second, window shrunk to **1 day** | 86,400 | 47.3 MB | 3.7 s |

Extrapolated, not run: the longest span the date type allows gives about 3.65 million rows (around 1.9 GB). The every-second
repeat over the default 67-day window gives about 5.8 million rows (around 3 GB). The sync rewrites the file every five
minutes, so the problem comes back until the event is removed.

On the widget side, loading the 193.6 MB file in Node (much faster than the QML engine) took this long:

```
read + JSON.parse: 343 ms for 365242 rows
visibleEvents + indexEventsByDate: 158 ms
heap used: 309 MB
```

The widget does this inside the shell process that also draws the bar, the notifications and the launcher. It does it again
on every file change, and the reminder timer walks all rows every 20 seconds. **Not demonstrated:** the effect on a running
shell. The live shell was not touched for this review. It was not tested whether Google's API accepts such an event, or keeps
such a rule in an emailed invitation, either. Expect a desktop that freezes or a shell that runs out of memory. The user sees
a bar that stops responding, again after every restart, and has no hint that one calendar entry is the cause.

**Fix options**, each with what it fails to stop:

| Option | What it stops | What it fails to stop |
|---|---|---|
| A. Clip the days an event covers to the sync window | The long-span event | Repeats, many small events, a huge feed body |
| B. Expand repeats lazily with a cap per event and per feed (`rie.of(...).after(start)` is a generator in recurring-ical-events 3.9, so it can stop counting early) | Every-second repeats | The long-span event, a huge body, many separate events |
| C. Read at most N bytes from a feed and refuse anything larger | Huge bodies | A small feed that expands (a few hundred bytes are enough for A or B) |
| D. A hard ceiling in the contract: a maximum number of rows and a maximum length per text field, enforced in `contract.validate` | Everything reaching the widget from the bundled sync | Memory and time spent inside the sync before the check runs |
| E. The widget caps the rows it accepts and says the file is too large | Any writer, including third-party ones the README invites | Reading the file itself, since `FileView` has no size check |

**Recommendation: all five, layered, failing closed.** A, B and C keep the sync cheap. D is the boundary that guarantees the
widget never receives an oversized document. E protects against writers this repository does not control. When a limit is
hit, drop the offending event and log which calendar it came from without its text. Do not refuse the whole sync, because
then one hostile event would stop every other calendar from updating.

**How to seal it.**

- Tests with made-up hostile feeds: a long-span event, an every-second repeat, and a body larger than the cap. Each test
  checks that the row count stays under the ceiling and the run finishes within a time budget.
- A contract test showing that `validate` refuses a document one row over the ceiling, so the limit cannot be removed quietly.
- Move the parsing in `BarWidget.qml:59` into a `Model.js` function (`eventsFromDocument(raw)`) that applies the cap. The
  Node tests can then cover it.
- Keep the limits as named constants in `contract.py`, the single source of truth it already is, and have `Model.js` read the
  same numbers. A test that reads both files and compares the numbers keeps them in step. That would be stronger than
  `TestUrlGuardMatchesTheWidget` in `tests/test_normalize.py`, which keeps the URL rule in step by repeating the same cases
  on both sides.

---

### F2 (Low): plain `http://` feeds are accepted

**What it is.** `url_problem` is the check that setup runs on each pasted feed address. `parse_feeds` turns the config into
the list the sync fetches.

**The point.** The error message says "expected an https:// or webcal:// address", but plain `http://` passes both:

```
url_problem('http://feeds.example.invalid/made-up.ics') -> ''
parse_feeds keeps it as        -> http://feeds.example.invalid/made-up.ics
```

On an `http` feed, the secret address (the path is the credential) and every event travel unencrypted. Anyone on the same
network can read the calendar, or inject events with their own join links. Python's `urllib` also follows a redirect from
`https` to `http` ([urllib.request docs](https://docs.python.org/3/library/urllib.request.html)), so even an `https` feed can
be moved onto plain HTTP by its server.

**In practice:** Google's secret addresses are `https`, so this lands on someone using another provider who pastes an `http`
link. On café Wi-Fi, that person's calendar is readable and writable by the network.

**Fix options.** (a) Refuse `http` in `url_problem` and `parse_feeds`. This fails to stop a redirect to `http`. (b) Also install
a redirect handler that refuses any redirect that leaves `https`. **Recommend (a) and (b).** TLS certificates are already
verified, because the default context has `verify_mode=2` and `check_hostname=True` (checked on this machine, see
[PEP 476](https://peps.python.org/pep-0476/)).

**Seal it** with one small value type (`FeedUrl`) that can only be built from an `https` address, used by both setup and the
sync, plus tests for `http`, for `webcal` mapped to `https`, and for a refused downgrade redirect.

---

### F3 (Low): a failing feed can print its secret address into the journal

**What it is.** When a feed fails, the sync logs it with `redact()`, which keeps only the host. That is good. But only three
kinds of error are caught (`ics.py:314`). Anything else escapes as a Python traceback in the systemd journal, and some
of those messages quote the URL path. Measured with a made-up address containing a space (no request was sent; Python
refuses the URL before connecting):

```
uncaught http.client.InvalidURL: URL can't contain control characters. '/ical/made-up/private-SECRETMADEUP 1/basic.ics' (found at least ' ')
```

**In practice:** the secret lands in `journalctl --user`. Members of the `wheel` or `systemd-journal` groups can often read it
too, and it gets pasted into bug reports. An uncaught error from one malformed event also stops the whole sync, not just that
feed (CWE-532).

**Fix options.** (a) Catch every exception per feed and per event, and log only `redact(url)` plus the exception's type. This
fails to stop a future `print` that uses `str(error)`. (b) Also route every feed message through one function that scrubs the
feed's path from any text before it is printed. **Recommend (a) and (b).**

**Seal it** with a test that feeds a made-up secret path through each failure kind (bad URL, bad body, bad component, timeout)
and asserts the secret never appears on stdout or stderr.

---

### F4 (Low): secret feed addresses sit in a plain JSON file whose mode nobody checks

**What it is.** `~/.config/omarchy/calendar-sync.json` holds the settings. With the iCal backend, it also holds the secret
addresses, which work like passwords ([Google](https://support.google.com/calendar/answer/37648)).

**The point.** `setup --ics` writes the file with mode 600, which is right. But the README also shows how to write it by hand,
and an editor creates it with the user's umask, usually 644. The gws branch of setup creates a new file with
`Path.write_text`, which also gives 644:

```
setup's gws branch writes a new config with mode 0o644 under umask 022
```

Switching from `--ics` to the gws backend also keeps the old secret addresses in the file. The sync never checks the mode.
The addresses stay in plain text, which the OWASP
[Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) advises
against (CWE-732).

**In practice:** on Arch, home folders are usually 700, which hides the file. This machine's is. Where a home folder is 755,
which is common on other systems and after a manual `chmod`, every local user can read the calendar.

**Fix options.**

| Option | What it fails to stop |
|---|---|
| (a) Refuse to read secret addresses from a config that group or others can read, the way `ssh` refuses a loose key, and write every config with mode 600 | Backups and other same-user programs reading the plain file |
| (b) Store each address in the Secret Service through libsecret (`secret-tool` and the `Secret` GObject bindings are both present on Omarchy), with the config holding only a label | A sync that runs before the keyring unlocks (it fails, which is closed) |
| (c) Drop the `ics` key when setup switches to another backend | Nothing on its own, but it removes stale secrets |

**Recommend (a) and (c) now, then (b).** (a) fails closed today with a few lines of code. (b) removes the plain-text secret
altogether.

**Seal it** with a config test that a group-readable file holding `ics` raises `ConfigError`, and a setup test (a fake home,
no network) asserting mode 600 on every path that writes the config.

---

### F5 (Low): a reminder's text can carry formatting tags into the notification card

**What it is.** A reminder is a desktop notification. Its first line is the headline, and its second line is the time plus the
event's location. Omarchy's notification card draws that second line as Qt `StyledText`, which honours `<b>`, `<font>`,
`<a>` and more ([Qt Text docs](https://doc.qt.io/qt-6/qml-qtquick-text.html)). It strips only images.

**The point.** The location comes from the sender of the invitation and reaches the body unescaped:

```
summary: "Made-up sync in 10 min"
body   : "10:00–10:30 · <font color=\"#ff0000\">Moved: see email</font>"
```

**In practice:** a sender can style or hide parts of the reminder, for example to show a fake "Moved: see email" in red.
Links are not clickable in the card and images are stripped, so the risk is spoofing only. An honest location such as
`Room <3>` also comes out mangled.

**Fix.** Escape `&`, `<` and `>` in every piece of event text that goes into the body. The headline is already shown as plain
text. The [notification spec](https://specifications.freedesktop.org/notification/latest-single/) lets a server render body
markup, so a sender of untrusted text has to escape it. Nothing this fix fails to stop was found.

**Seal it** with a `Model.js` test: a location full of tags produces a body with no `<` from the event.

---

### F6 (Low): calendar ids appear in process arguments every five minutes

**What it is.** Reads go through `gws`, and `gws` takes its query as a `--params` argument:

```
['gws', 'calendar', 'events', 'list', '--params', '{"calendarId": "someone.else@example.com", ...}']
```

**In practice:** on a shared machine, another user running `ps` can see which calendars this user reads. Those are the user's
address and the addresses of colleagues who shared calendars. Writes already avoid this (`gws.py`, "send writes to the
Calendar API"). Event content is not exposed.

**Fix options.** (a) Do reads over HTTPS with the token the write path already makes, the same way writes work. This fails to
stop nothing extra. (b) Mount `/proc` with `hidepid=2`, which is outside this project. **Recommend (a)**, as a later step.

**Seal it** with a test that records the arguments of every process the sync starts and asserts that no calendar id appears
in them.

---

### F7 (Low): a long guest name can push the real email address out of view

**What it is.** The event form suggests guests from people in the user's existing events (`suggestions.py`). A suggestion
shows as `Name  <email>`, cut off at the right (`GuestList.qml:117`).

**In practice:** the name comes from another person's invitation. A very long name such as "Made-up Manager (Finance team)…"
hides the address. Someone who picks it invites a stranger to their meeting. The panel does ask before sending invitations,
which helps.

**Fix.** Show the address first, or on its own line, and never cut it off. Build the label in a `Model.js` function so it can
be tested. **Seal it** with that test.

---

### F8 (Info): Join opens any `https` link the event carries

Links found in an event's text only become a Join button for known meeting hosts. That is a good rule. Links from Google's
conference fields, and `X-GOOGLE-CONFERENCE` in a feed, accept any `https` host (`normalize.py:55`). A middle click on the bar
and the `m` key join the *next* meeting, whichever event that is. A sender can therefore make Join open a page of their
choice. The user would be clicking through to that page anyway, so this is noted rather than ranked. If wanted, show the
link's host on the button when it is not a known meeting service.

### F9 (Info): no CI, and the safety rules are kept by habit

The code follows clear rules: plain text for event data, argument lists and never a shell, stdin for secrets. The rules hold
today. A scan of every `Text`, `TextEdit` and `TextField` that does not set plain text found none that shows event data. But
no test enforces them, and nothing runs the 299 Python tests and 284 JavaScript tests on a pull request.

**Recommend** a GitHub Actions workflow with `permissions: contents: read`, actions pinned to a commit SHA, and the
`pull_request` trigger only (never `pull_request_target`). It should run both test suites and two architecture tests:

- Every QML `Text`, `TextEdit` and `TextField` either sets `textFormat` to plain text, or appears on a short allowlist that
  names the reason (today: the quick-add highlight, which escapes its input).
- No QML `Process` command and no Python `subprocess` call names `sh`, `bash` or `-c`, or passes `shell=True`.

### F10 (Info): no minimum version for `python-icalendar`

`python-icalendar` fixed two denial-of-service bugs in 2026: CVE-2026-55099, exponential equality checks, fixed in 7.1.3, and
CVE-2026-77399, unbounded `VALARM REPEAT` expansion, fixed in 7.2.2
([OSV](https://osv.dev/vulnerability/CVE-2026-77399)). This code reads alarm triggers directly rather than through the
affected API, and this machine has 7.3.0, so neither is reachable as far as this review found. **Recommend** that
`Ics.check` refuse versions older than 7.2.2, with a test, so an old system package fails loudly instead of quietly.

### F11 (Info): setup leaves the client secret readable for a moment

`sync/setup` creates the gws profile folder with the default mode (usually 755). It then copies or moves `client_secret.json`
into it and only afterwards runs `chmod 600`, so the file is briefly readable by others. Google treats a desktop client's
secret as not truly secret, so the impact is small. **Recommend** `mkdir -m 700` for the profile, and `install -m 600` for the
copy.

The README's install command points at `github.com/tmn73/omarchy-calendar`. Every install runs whatever that repository
serves, in the shell process and in the timer, so it is worth deciding deliberately which repository each install tracks.

## Findings from the second review

A second review, done without this document's conclusions, found these.

- **N1 (Medium): one bad feed or event stopped every calendar from updating.** One invalid row failed the whole document,
  and one feed whose repeats could not be expanded failed the whole run. An 8-digit `#RRGGBBAA` feed colour was enough.
  Now a row that breaks the contract is dropped and counted per calendar, a colour outside `#rrggbb` takes a palette
  colour, and a calendar that cannot be read on its own is skipped. When every calendar is skipped, nothing is written.
- **N2 (Low): a sync run had no overall time limit.** A feed sending one byte at a time kept each read inside its timeout,
  and a oneshot unit has no start timeout, so the timer never ran again until reboot.
- **N3 (Low): the Join label could name a different site from the one the link opened.** Browsers read `\` as `/`, so
  `https://evil.example\@meet.google.com/...` was labelled Google Meet, and the reminder opened `evil.example`. Any host
  with a `jitsi.` label was called Jitsi.
- **N4 (Low): an event from one calendar could replace the same event in another.** Copies matched on UID and start, which
  anyone invited knows, and the first calendar's copy won.
- **N5 (Low): setup ran Python code from the folder it was started in.** `python3 -c` and `python3 -` import from the
  current folder first, so a planted `json.py` ran.
- **N6 (Info): parsing a description with nested links took quadratic time.**
- **N7 (Info): the systemd unit had no hardening.**
- **N8 (Info): the token followed a redirect.** `urllib` keeps the `Authorization` header across a redirect, even to
  another host.

It also corrected this review in four places: F1 missed that EDS expands repeats without a cap and that `gws` fails the
whole sync past its page limit; F3 missed that a caught error's message could quote the address and that `redact()` kept
a user name and password; F4 missed that a config others can write means running their code, because it names
`gwsPath`; F11 missed that setup installed whichever client secret download it found first.

## What was checked and found sound

| Area | What the code does |
|---|---|
| Shell commands | None anywhere. QML `Process` and Python `subprocess.run` get argument lists. `Panel.qml:546` explains why `Qt.openUrlExternally` is used instead of the shell helper. |
| Notification command | Argument list. `--exec xdg-open <url>` comes last, and a headline starting with `-` gets a word joiner (`Model.js:1097`). Omarchy's helper hands the values to `busctl` as typed D-Bus values. |
| Opening links | Only `https`. The widget (`Model.safeUrl`) and the sync (`contract.is_https_url`) apply the same rule, which refuses spaces and quotes. No `file://` and no leading `-` can reach `xdg-open`. |
| Rich text | Every element that shows event data uses plain text. The quick-add highlight uses `StyledText` but escapes `&`, `<` and `>` first (`QuickAddParser.js:831`). |
| Descriptions | HTML is reduced to text and capped at 1,500 characters (`plaintext.py`). |
| Secrets in process arguments | Feed addresses go to Python on stdin and file descriptor 3 (`setup:103`, `setup:124`). Event requests go on stdin (`Panel.qml:749`). The Google refresh token is read from `gws` stdout and sent over HTTPS, never as an argument (`gws.py:238`). |
| TLS | Python's default context verifies certificates and host names (PEP 476). Nothing turns that off. |
| Feed address in logs and in the events file | `redact()` keeps only the host. Calendar ids for feeds are a hash, so the address never reaches the events file (`ics.py:76`). The gaps found in F3 are fixed. |
| Events file | Atomic temp file and rename. Mode 600 (measured: `0o600`). The folder belongs to the user, so no symlink race is possible. |
| Event command | Checks the calendar against the writable list, and `action`, `scope` and `sendUpdates` against fixed lists. Ids are URL-encoded (`writes.py`, `gws.py:94`). |
| Local ports and IPC | None. The only IPC is Quickshell's own `IpcHandler`, on the user's runtime folder (mode 700). Unlike the issue recently fixed in a sibling project, there is no localhost page or token another user could reach. |
| Reminder state | Lives under `XDG_RUNTIME_DIR` (mode 700), written atomically. |
| GitHub Actions | One workflow, read only, `pull_request` and `push` to main only, pinned by commit and digest. A test holds it to those terms. |
| Python dependencies | Standard library only, plus the optional `python-icalendar` and `python-recurring-ical-events`, and GObject bindings for EDS. |

## Step plan

Done, in this order of safety, on `security-review-calendar`: F1 (window, repeat cost, feed size, contract ceiling, the
widget's own cap), N1, F2, F3 and N8, N2 and N7, F4 with F10, F11 and N5, F5 with F8 and N3, F7, N4, F6, then F9.

## How this was checked

- Read every Python module, the setup script, the systemd units, `Model.js`, `QuickAddParser.js`, and the QML files that show
  event data or start processes.
- Ran both test suites with stubbed `xdg-open`, `notify-send`, `zenity`, `kdialog`, `systemctl` and the Omarchy notification
  command on `PATH`, and with a throwaway `HOME`. Python: 299 passed. Node: 284 passed.
- Measured F1 by running `cli.run` on made-up feeds through a fake fetch, and the widget cost with `Model.js` under Node.
  Nothing was sent to a calendar server, and the live shell was not touched.
- Read Omarchy's notification helper and card on this machine, to see how the reminder text is used.

## Sources

- OWASP, [OS Command Injection Defense Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html)
- OWASP, [Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html)
- OWASP, [Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- OWASP, [Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
- MITRE, [CWE-400 Uncontrolled Resource Consumption](https://cwe.mitre.org/data/definitions/400.html),
  [CWE-532 Sensitive Information in Log File](https://cwe.mitre.org/data/definitions/532.html),
  [CWE-732 Incorrect Permission Assignment](https://cwe.mitre.org/data/definitions/732.html)
- Qt, [Text QML type, `textFormat`](https://doc.qt.io/qt-6/qml-qtquick-text.html), and [QDesktopServices](https://doc.qt.io/qt-6/qdesktopservices.html)
- freedesktop.org, [Desktop Notifications Specification](https://specifications.freedesktop.org/notification/latest-single/)
- freedesktop.org, [Secret Service API](https://specifications.freedesktop.org/secret-service/latest/)
- Python, [urllib.request](https://docs.python.org/3/library/urllib.request.html), and [PEP 476](https://peps.python.org/pep-0476/)
- OSV, [CVE-2026-77399 (icalendar)](https://osv.dev/vulnerability/CVE-2026-77399), and [CVE-2026-55099 (icalendar)](https://www.mend.io/vulnerability-database/CVE-2026-55099/)
- Stalwart, [CVE-2025-59045](https://www.sentinelone.com/vulnerability-database/cve-2025-59045/), recurring-event expansion without an instance limit in a CalDAV server: the same class of bug as F1
- Google, [Sync your calendar with computer programs](https://support.google.com/calendar/answer/37648) (secret address and reset)
- Invitation auto-add setting: [Mount Holyoke LITS](https://lits.mtholyoke.edu/node/5209), [Brown IT](https://ithelp.brown.edu/kb/articles/2235), [9to5Google](https://9to5google.com/?p=554455)
