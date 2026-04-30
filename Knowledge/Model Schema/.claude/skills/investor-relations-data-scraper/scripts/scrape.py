"""Investor Relations Data Scraper — orchestrator + per-ticker backends.

Single-file script. Reuses `consumer_staples_earnings.py` as the source of truth
for TICKERS, IR_URLS, and source-presence logic.

Run:
    python scrape.py                      # all tickers with gaps
    python scrape.py --tickers PM,CELH    # subset
    python scrape.py --dry-run            # report, don't download
    python scrape.py --no-transcribe      # skip audio-transcription chain
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

# Windows console defaults to cp1252 which can't encode ✓ / ✅ / etc.
# `line_buffering=True` forces stdout to flush on every newline even when piped
# (default is block-buffered for pipes, which masks progress through `tee`).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

# Cap yfinance's underlying HTTP timeout so an unresponsive Yahoo Finance
# endpoint can't hang a ticker indefinitely (survey saw SYY/STZ stall with no
# log output, Python still alive — classic socket-level hang with no upper bound).
import socket as _socket
_socket.setdefaulttimeout(15)
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Make the sibling consumer_staples_earnings.py importable
CSE_DIR = Path(r"C:\Users\rodin\.claude\scripts\investor-relations-data-scraper")
sys.path.insert(0, str(CSE_DIR))
import consumer_staples_earnings as cse  # noqa: E402

import requests
import yfinance as yf
from curl_cffi import requests as cc_requests
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout
from playwright_stealth import Stealth


# --- Config -----------------------------------------------------------------

GAP_REPORT_PATH = Path(r"C:\Users\rodin\Desktop\Brain\Knowledge\IR Scraper Gap Report.md")
TRANSCRIBE_SCRIPT = Path(r"C:\Users\rodin\.claude\skills\audio-transcription\scripts\transcribe.py")

FAKE_REG_INFO = {
    "First Name": "Research",
    "Last Name": "Analyst",
    "Company": "Independent",
    "Email": "research@example.com",
}

EARNINGS_TITLE_KEYWORDS = ("earnings", "quarter", "results")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# --- Data classes -----------------------------------------------------------

@dataclass
class Artifact:
    kind: str  # "audio" | "press_release" | "presentation"
    path: Path
    source_url: str


@dataclass
class ScrapeResult:
    ticker: str
    event_date: str | None
    artifacts: list[Artifact] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    note: str | None = None
    quarter: str | None = None


# --- Utility helpers --------------------------------------------------------

def download_pdf(url: str, dest: Path, referer: str | None = None) -> None:
    """Download a PDF via curl_cffi with Chrome TLS fingerprint impersonation.

    Q4 Inc's gcs-web.com static-files host is fronted by Akamai Bot Manager,
    which RST_STREAMs Playwright's Chromium HTTP/2 requests regardless of
    headers. curl_cffi with impersonate='chrome131' sends real Chrome's TLS
    signature and passes cleanly."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Accept": "application/pdf,*/*"}
    if referer:
        headers["Referer"] = referer
    r = cc_requests.get(url, impersonate="chrome131", headers=headers, timeout=45)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} on {url}")
    body = r.content
    if not body.startswith(b"%PDF"):
        raise RuntimeError(f"Not a PDF response (got {body[:8]!r}) from {url}")
    dest.write_bytes(body)


def download_hls_to_m4a(m3u8_url: str, dest: Path) -> None:
    """ffmpeg -i playlist.m3u8 -c copy out.m4a. Preserves original encoding."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-user_agent", USER_AGENT,
        "-i", m3u8_url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def download_audio_file(url: str, dest: Path, referer: str | None = None) -> None:
    """Download a direct-download audio file (MP3/M4A/WAV) via curl_cffi.
    Used when an IR site hosts the raw audio on its events page — no vendor
    sniffer needed. KMB (Q4 Inc pre-recorded management discussion MP3s) is
    the reference case."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Accept": "audio/*,*/*"}
    if referer:
        headers["Referer"] = referer
    r = cc_requests.get(url, impersonate="chrome131", headers=headers, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} on {url}")
    dest.write_bytes(r.content)


def download_youtube_audio(url: str, dest: Path) -> None:
    """Extract audio from a YouTube URL (Live post-stream or regular VOD) via
    yt-dlp. WMT's earnings calls are on YouTube Live — post-broadcast, the
    recording is accessible as a normal video URL that yt-dlp handles."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # yt-dlp rewrites the output filename extension to match the extracted
    # audio format. Use `%(ext)s` placeholder and let it pick m4a.
    out_template = str(dest.with_suffix(".%(ext)s"))
    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "m4a",
        "--no-playlist",
        "-o", out_template,
        url,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=1800)


def is_earnings_event(blob: str) -> bool:
    blob = blob.lower()
    return any(k in blob for k in EARNINGS_TITLE_KEYWORDS)


# --- Webcast-vendor sniffers ------------------------------------------------
# Vendor-generic HLS-URL extractors. Called per-vendor by _scan_and_download_audio.

_PLACEHOLDER_OPTION_PHRASES = (
    "select", "choose", "please", "pick one", "- -",
)

def _is_placeholder_option(text: str, opt) -> bool:
    """Detect <option> placeholders that look like real values but aren't.
    Mediasite's Investor Type dropdown uses "...................." as its
    placeholder — our previous "first non-empty" logic picked it, leaving
    Angular's form validation unsatisfied so the submit button stayed disabled.

    Placeholder signatures:
      - HTML `disabled` attribute (standard)
      - empty value attribute (common placeholder pattern)
      - text is all non-alphanumeric padding (dots, dashes, spaces)
      - text starts with a known prompt phrase ("Select...", "Choose...")
    """
    try:
        if opt.get_attribute("disabled") is not None:
            return True
        val = opt.get_attribute("value") or ""
        if not val.strip():
            return True
    except Exception:
        pass
    stripped = text.strip()
    if not any(c.isalnum() for c in stripped):
        return True
    low = stripped.lower()
    return any(low.startswith(p) for p in _PLACEHOLDER_OPTION_PHRASES)


def _sniff_mediasite_hls(page: Page, webcast_url: str, timeout_s: int = 45,
                         semi_auto: bool = False) -> str | None:
    """Navigate to Mediasite (media-server.com) webcast, submit the guestbook
    registration form, and sniff the HLS playlist URL from subsequent media requests.

    Mediasite's "two_column/guestbook" layout gates the stream behind a form:
    firstname, lastname, email, institution (Company), and Investor Type dropdown.
    The stream URL is only requested AFTER successful submission."""
    captured: dict[str, str | None] = {"url": None}

    def on_request(req):
        u = req.url.lower()
        if captured["url"] is None and (".m3u8" in u or ".mpd" in u):
            captured["url"] = req.url

    page.on("request", on_request)

    try:
        page.goto(webcast_url, wait_until="domcontentloaded", timeout=45000)
    except PWTimeout:
        return None
    time.sleep(6)

    # Dismiss OneTrust cookie banner if present (blocks viewport / submit button)
    for sel in ("#onetrust-accept-btn-handler", "button:has-text('Accept All')"):
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1000):
                btn.click(timeout=2000)
                print(f"       [mediasite] dismissed cookies via {sel}")
                time.sleep(1)
                break
        except Exception:
            pass

    # Fill text fields. Angular reactive forms only mark a control as "touched"
    # (enabling the submit button) after a blur event — .fill() alone doesn't blur,
    # so we click into each input then Tab out.
    for sel, val in (
        ("input[name='firstname']", FAKE_REG_INFO["First Name"]),
        ("input[name='lastname']", FAKE_REG_INFO["Last Name"]),
        ("input[name='email']", FAKE_REG_INFO["Email"]),
        ("input[name='institution']", FAKE_REG_INFO["Company"]),
    ):
        try:
            loc = page.locator(sel).first
            loc.click(timeout=2000)
            loc.fill(val, timeout=2000)
            loc.press("Tab", timeout=2000)
            print(f"       [mediasite] filled {sel}")
        except Exception as e:
            print(f"       [mediasite] ✗ fill {sel}: {e}")

    # Handle any <select> (Investor Type etc.). Angular's reactive forms use ngValue
    # bindings that produce synthetic option values like "1: 1" — selecting by label
    # text is more reliable than by value. Fire change+blur after so Angular validates.
    # Skip placeholder options: dot-padding ("...................."), "Select...",
    # "Choose one", "--", etc. Picking those leaves the form control invalid and
    # Angular keeps the submit button aria-disabled=true.
    for s in page.locator("select").all():
        try:
            options = s.locator("option").all()
            for opt in options:
                text = (opt.inner_text() or "").strip()
                if not text or _is_placeholder_option(text, opt):
                    continue
                try:
                    s.select_option(label=text)
                except Exception:
                    val = opt.get_attribute("value") or ""
                    if val:
                        s.select_option(value=val)
                s.evaluate("el => { el.dispatchEvent(new Event('change', {bubbles:true})); "
                           "el.dispatchEvent(new Event('blur', {bubbles:true})); }")
                print(f"       [mediasite] selected {text!r}")
                break
        except Exception as e:
            print(f"       [mediasite] ✗ select: {e}")

    # Submit — semi-auto pauses for the user to solve CAPTCHA + click Submit.
    # Auto mode tries to click, though CAPTCHA-gated forms will fail here.
    if semi_auto:
        print("\n  ┌─────────────────────────────────────────────────────────────────┐")
        print("  │  MANUAL STEP REQUIRED                                           │")
        print("  │                                                                 │")
        print("  │  A browser window is open at the Mediasite registration form.   │")
        print("  │  Name/email/company/investor-type are pre-filled.               │")
        print("  │                                                                 │")
        print("  │  Please:                                                        │")
        print("  │    1. Solve the 'I'm not a robot' CAPTCHA                       │")
        print("  │    2. Click Submit                                              │")
        print("  │    3. Wait for the video player to load                         │")
        print("  │    4. Return to this terminal and press Enter                   │")
        print("  └─────────────────────────────────────────────────────────────────┘")
        try:
            input("  [waiting for Enter] > ")
        except EOFError:
            pass
        print("       [mediasite] resumed — watching network for stream URL")
    else:
        submitted = False
        for sel in ("button[type='submit']", "input[type='submit']",
                    "button.btn-primary", "button:has-text('Submit')"):
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=500):
                    loc.click(timeout=3000)
                    print(f"       [mediasite] clicked submit via {sel}")
                    submitted = True
                    break
            except Exception as e:
                print(f"       [mediasite] ✗ submit {sel}: {e}")
        if not submitted:
            print("       [mediasite] ✗ no submit button matched (CAPTCHA likely blocking — rerun with --semi-auto)")

    # Wait for HLS / DASH URL; click any play button that appears. Use
    # page.wait_for_timeout (not time.sleep) to pump Playwright's event queue
    # so on_request fires — see west_intrado sniffer for the full explanation.
    deadline = time.time() + timeout_s
    clicked_play = False
    while time.time() < deadline:
        if captured["url"]:
            break
        if not clicked_play:
            for sel in (".play-button", "button.play-button", "[class*='play-button']"):
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=300):
                        loc.click(timeout=1500)
                        clicked_play = True
                        break
                except Exception:
                    pass
        page.wait_for_timeout(500)
    return captured["url"]


def _sniff_west_intrado_hls(page: Page, webcast_url: str, timeout_s: int = 60) -> str | None:
    """Register on West/Intrado with fake info, sniff the HLS playlist URL from
    network. event.webcasts.com rotates field `name`/`id` values per event to
    defeat automated filling (values like `3b7cb838a74c9f5f96f84e81acc974b13...`
    instead of `firstname`/`lastname`). Two-phase fill:
      1. Try `<label>`-based fill via `get_by_label` (works on sites with
         semantic markup).
      2. Fall back to filling by input `type` + positional order for the
         obfuscated-name forms (text[0]=FirstName, text[1]=LastName,
         text[2]=Company, email=Email, tel=phone).

    Timeout note: archived-event replays consistently take ~30s from submit
    click to the first `.m3u8` request (registration POST → landing.jsp →
    event.jsp → Bitmovin player init → HLS manifest fetch). Keep `timeout_s`
    ≥ 60 so slow days don't miss the capture.
    """
    captured: dict[str, str | None] = {"url": None}

    def on_request(req):
        if ".m3u8" in req.url and captured["url"] is None:
            captured["url"] = req.url

    page.on("request", on_request)

    try:
        page.goto(webcast_url, wait_until="domcontentloaded", timeout=45000)
    except PWTimeout:
        return None
    time.sleep(2)  # give the full form time to render

    # Phase 1: label-based fill (best-case, keeps intent visible in logs).
    for label, value in FAKE_REG_INFO.items():
        try:
            page.get_by_label(label, exact=False).last.fill(value, timeout=3000)
        except Exception:
            pass

    # Phase 2: type-based fallback for obfuscated-name forms. Only fills
    # inputs that are still empty so Phase 1's fills aren't overwritten.
    def _fill_if_empty(loc, val):
        try:
            if not (loc.input_value(timeout=500) or "").strip():
                loc.fill(val, timeout=3000)
        except Exception:
            pass

    text_values = [FAKE_REG_INFO["First Name"], FAKE_REG_INFO["Last Name"],
                   FAKE_REG_INFO["Company"]]
    text_inputs = page.locator("input[type='text']:visible").all()
    for inp, val in zip(text_inputs, text_values):
        _fill_if_empty(inp, val)
    for inp in page.locator("input[type='email']:visible").all():
        _fill_if_empty(inp, FAKE_REG_INFO["Email"])
    # Phone field — West/Intrado's newer forms include a required tel input
    # that the old 4-field FAKE_REG_INFO doesn't cover.
    for inp in page.locator("input[type='tel']:visible").all():
        _fill_if_empty(inp, "5551234567")

    # Click the registration submit (not the "log in" submit on the returning-
    # visitor block at the top of the page).
    submits = page.locator("input[type='submit']").all()
    for btn in submits:
        try:
            val = (btn.get_attribute("value") or "").lower()
            if "log in" in val or "login" in val or "sign in" in val:
                continue
            if btn.is_visible(timeout=500):
                btn.click(timeout=3000)
                break
        except Exception:
            pass

    # CRITICAL: use page.wait_for_timeout (not time.sleep) — in Playwright's
    # sync API, time.sleep doesn't pump the event queue, so the `on_request`
    # callback never fires and `captured["url"]` stays None. wait_for_timeout
    # yields to Playwright to drain queued network events.
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if captured["url"]:
            break
        page.wait_for_timeout(500)
    return captured["url"]


def _sniff_choruscall_mp4(page: Page, webcast_url: str, timeout_s: int = 60) -> str | None:
    """Register on ChorusCall (event.choruscall.com/mediaframe/webcast.html) and
    capture the Akamai-hosted MP4 URL.

    Form: firstName / lastName / email / company inputs by id, #registrationSubmit
    button. No reCAPTCHA. Media arrives as a direct MP4 at
    `vodchoruscall.akamaized.net/.../{eventid}.mp4` once the player mounts.

    Reference: validated on STZ Q4 FY26 (webcastid=qgIohQED) and BG archive
    (webcastid=KC5oqyL9). Same IR pages that show this as `(unknown)` in older
    surveys — the vendor catalog now promotes `event.choruscall.com` to a
    named vendor.
    """
    captured: dict[str, str | None] = {"url": None}

    def on_request(req):
        u = req.url
        if ("vodchoruscall" in u or "choruscall.akamaized" in u
                or any(ext in u.lower() for ext in (".mp4", ".m4a", ".mp3"))
                and "choruscall" in u and captured["url"] is None):
            # Only take media hosts / extensions; avoid html/js/css on choruscall.com
            if any(marker in u.lower() for marker in (
                ".mp4", ".m4a", ".mp3", ".m3u8", "vodchoruscall",
            )):
                captured["url"] = u

    page.on("request", on_request)

    try:
        page.goto(webcast_url, wait_until="domcontentloaded", timeout=30000)
    except PWTimeout:
        return None
    page.wait_for_timeout(2500)

    for sel, val in (
        ("#firstName", "Research"),
        ("#lastName", "Analyst"),
        ("#email", "research@example.com"),
        ("#company", "Independent"),
    ):
        try:
            page.locator(sel).first.fill(val, timeout=2500)
        except Exception as e:
            print(f"       [choruscall] ✗ fill {sel}: {type(e).__name__}")

    # Some ChorusCall registrations add custom user-defined fields (`udef1`,
    # `udef2`, ...). CL's form has `select#udef1` for "Investor Type" with a
    # "-- Investor Type --" placeholder and real options. Pick first non-
    # placeholder option on every visible select.
    for select in page.locator("form#registrationForm select").all():
        try:
            options = select.locator("option").all()
            for opt in options:
                text = (opt.inner_text() or "").strip()
                if _is_placeholder_option(text, opt):
                    continue
                try:
                    select.select_option(label=text)
                    print(f"       [choruscall] selected {text!r}")
                except Exception:
                    val = opt.get_attribute("value") or ""
                    if val:
                        select.select_option(value=val)
                        print(f"       [choruscall] selected value={val!r}")
                break
        except Exception as e:
            print(f"       [choruscall] ✗ select: {type(e).__name__}")

    try:
        page.locator("#registrationSubmit").first.click(timeout=3000)
    except Exception as e:
        print(f"       [choruscall] ✗ submit: {type(e).__name__}")
        return None

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if captured["url"]:
            break
        page.wait_for_timeout(500)
    return captured["url"]


def _sniff_q4_inc_mp4(page: Page, webcast_url: str, timeout_s: int = 60) -> str | None:
    """Register on Q4 Inc's guest flow and capture the edited-recording MP4 URL.

    Q4 Inc (events.q4inc.com/attendee/{event_id}) is a React SPA with a three-
    step flow:
      1. Landing: 3 buttons (signup / create account / continue without).
         We click #registration-box_login-button ("Continue without a Q4 account").
      2. Guest registration form at /attendee/{id}/guest:
         - #GuestRegistrationFirstNameInput / LastNameInput / EmailInput (text)
         - #GuestRegistrationInvestorCheckboxInput ("I am an individual attendee")
           — custom component, click the label text. Setting this bypasses the
           Institution autocomplete field which we can't satisfy via plain fill.
         - #GuestRegistrationSubmitButton ("Register for this Event").
      3. Post-submit: event player loads. The actual recording is served as
         a direct MP4 from static.events.q4inc.com/edited-recordings/{id}/{uuid}.mp4
         — no HLS, no reCAPTCHA. Just capture the URL from network and download.

    Reference: tested on TSN's 2026 Annual Meeting (attendee 891408037).
    Returns the MP4 URL on success, None on timeout.
    """
    captured: dict[str, str | None] = {"url": None}

    def on_request(req):
        u = req.url
        if ("static.events.q4inc.com/edited-recordings/" in u
                and captured["url"] is None):
            captured["url"] = u

    page.on("request", on_request)

    try:
        page.goto(webcast_url, wait_until="domcontentloaded", timeout=30000)
    except PWTimeout:
        return None
    page.wait_for_timeout(3000)  # SPA needs a moment to hydrate

    # Step 1: click "Continue without a Q4 account"
    try:
        page.locator("#registration-box_login-button").click(timeout=5000)
    except Exception as e:
        print(f"       [q4_inc] ✗ continue-without-account: {type(e).__name__}")
        return None
    page.wait_for_timeout(2500)  # navigation to /guest

    # Step 2a: check "I am an individual attendee" via its label (the input
    # itself is display:none inside a custom component).
    checked = False
    for sel in ("label:has-text('I am an individual attendee')",
                "text=I am an individual attendee"):
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=500):
                loc.click(timeout=1500, force=True)
                checked = True
                break
        except Exception:
            pass
    if not checked:
        # Not fatal — non-investor flow might still work if Company field is
        # populated. Continue and see what happens.
        print("       [q4_inc] could not check individual-attendee; continuing")

    # Step 2b: fill First / Last / Email. Role may be hidden when the
    # individual-attendee checkbox is set; skip if it times out.
    for sel, val in (
        ("#GuestRegistrationFirstNameInput", "Research"),
        ("#GuestRegistrationLastNameInput", "Analyst"),
        ("#GuestRegistrationEmailInput", "research@example.com"),
    ):
        try:
            page.locator(sel).first.fill(val, timeout=3000)
        except Exception as e:
            print(f"       [q4_inc] ✗ fill {sel}: {type(e).__name__}")

    page.wait_for_timeout(500)

    # Step 2c: click submit
    try:
        page.locator("#GuestRegistrationSubmitButton").first.click(timeout=3000)
    except Exception as e:
        print(f"       [q4_inc] ✗ submit: {type(e).__name__}")
        return None

    # Step 3: wait for the MP4 URL. It arrives once the player mounts (usually
    # 5-15s after registration). wait_for_timeout (not time.sleep) so Playwright
    # drains the event queue and on_request fires — see west_intrado sniffer
    # for the full explanation of this gotcha.
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if captured["url"]:
            break
        page.wait_for_timeout(500)
    return captured["url"]


# --- Webcast-vendor URL catalog --------------------------------------------
# Known hosts / path fragments that identify each webcast-streaming vendor.
# Seeded from generic_backend._is_webcast_portal (5 hosts we already filter
# out during PDF extraction) + hosts observed on individual IR sites.
# When survey_webcast_urls scans link hrefs, a match against any substring
# for a vendor attributes that hit to that vendor. First-match-wins — pattern
# lists within a vendor are alternate ways the same vendor appears.
#
# Each audio vendor module (to be built after the survey) will register its
# own subset of these patterns plus the sniff logic for that player protocol.

# Vendors where a failure on one URL predicts failures on all same-vendor URLs
# on the same page (e.g. mediasite's reCAPTCHA gates every event identically).
# Excluded: vendors where each URL is a distinct event with independent state
# — q4_inc_attendee (attendee/12345 is a specific event; past calls have
# recordings, future calls don't), west_intrado (similar — each event has its
# own registration state).
_DEDUPE_ON_VENDOR_FAILURE = frozenset({
    "mediasite",
    "veracast",
    "open_exchange",
    "webcast_eqs",
})

WEBCAST_VENDOR_PATTERNS: dict[str, tuple[str, ...]] = {
    "mediasite":       ("edge.media-server.com", "media-server.com/mediasite",
                        "mediasite.com/mediasite", "sonicfoundry.com"),
    "q4_inc_attendee": ("events.q4inc.com/attendee",),
    "choruscall":      ("event.choruscall.com/mediaframe",
                        "services.choruscall.com/mediaframe"),
    "west_intrado":    ("event.webcasts.com", "webcasts.com/starthere",
                        "cc.webcasts.com", "webcasts.com/viewer",
                        "notifiedsuite.com", "notified.com/conference"),
    "wsw":             ("wsw.com/webcast",),
    "open_exchange":   ("open-exchange.net",),
    "veracast":        ("veracast.com",),
    "ir_direct":       ("irdirect.net/player",),
    "spark_live":      ("spark.live",),
    "brainshark":      ("brainshark.com",),
    "streetevents":    ("streetevents.com", "refinitiv.com/streetevents"),
    "webcast_eqs":     ("webcast-eqs.com",),
    "youtube_live":    ("youtube.com/live/", "youtu.be/",
                        "youtube.com/watch", "youtube.com/embed/",
                        "youtube-nocookie.com/embed/"),
}

# Link text phrases that strongly signal a webcast/replay, used as a fallback
# classifier when the href doesn't match a known vendor host (e.g. the link
# points at an IR site's own vanity redirector like `ir.company.com/events/
# webcast-replay/q4-2025`). These are recorded under the `(unknown)` vendor
# bucket for manual review.
_WEBCAST_TEXT_HINTS = (
    "webcast", "audio replay", "audio webcast", "conference call",
    "listen to", "listen to webcast", "replay", "audio", "live stream",
    "live event", "event replay", "watch webcast", "earnings call",
)
_WEBCAST_URL_HINTS = (
    "webcast", "replay", "conference-call", "conference_call",
    "earnings-call", "audio", "live-event", "live-stream",
)


_DIRECT_AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".webm")


def classify_webcast_url(href: str, text: str = "") -> str | None:
    """Return the vendor name if the href matches a known vendor host, else
    '(unknown)' when the href or link text looks webcast-ish, else None.

    Special bucket `direct_audio` for IR sites that host the raw MP3/M4A
    themselves — KMB's events-and-presentations listing is the reference case
    (direct `.mp3` download, no registration, no vendor sniffer needed). These
    tickers don't need a vendor module at all, just a download call."""
    h = (href or "").lower()
    if not h.startswith(("http://", "https://")):
        return None
    # Direct audio file → highest-precedence bucket. Check the path portion
    # only so query strings don't defeat the extension match.
    h_path = h.split("?")[0].split("#")[0]
    if any(h_path.endswith(ext) for ext in _DIRECT_AUDIO_EXTENSIONS):
        return "direct_audio"
    for vendor, patterns in WEBCAST_VENDOR_PATTERNS.items():
        if any(p in h for p in patterns):
            return vendor
    t = (text or "").lower().strip()
    # Skip links that obviously aren't webcasts even when the keyword matches.
    # Covers: PR/news detail pages ("earnings call" in title), SEC filings,
    # calendar-invite downloads, social/news redirectors, and generic event-
    # detail listing pages (which we already walk into via the candidate loop,
    # so recording the URL as a webcast hit is redundant noise).
    if any(skip in h for skip in (".pdf", "/static-files/", "news-release",
                                   "press-release", "news-detail", "news_detail",
                                   "/filing/", "/sec-filings",
                                   "downloadical", "addtocalendar", "add-to-calendar",
                                   ".ics", "platform=googlecalendar", "platform=outlook",
                                   "cts.businesswire.com", "businesswire.com/ct/",
                                   "twitter.com", "x.com/", "linkedin.com", "facebook.com",
                                   "event-details/", "event_details/")):
        return None
    if any(hint in h for hint in _WEBCAST_URL_HINTS):
        return "(unknown)"
    if any(hint in t for hint in _WEBCAST_TEXT_HINTS):
        return "(unknown)"
    return None


# --- Generic backend --------------------------------------------------------
# Heuristic crawl that works for most IR sites without per-ticker code:
# corp homepage (from yfinance) → IR page → events page → earnings event → PDFs.
# Audio extraction is deferred — handled by per-vendor sniffers once the
# vendor-module dispatcher is wired in.

_IR_NAV_KEYWORDS_TEXT = ("investor relations", "investors", "investor")
_IR_NAV_KEYWORDS_URL = ("investor", "/ir/", "ir.", "investors.", "stock.")
_EVENTS_KEYWORDS_TEXT = (
    "news & events", "news and events", "press releases", "events & presentations",
    "quarterly results", "quarterly reports", "financial results", "financial reports",
    "financial information", "sec filings", "investor news", "investor news and events",
    "earnings", "events", "news", "results", "reports",
)
_EVENTS_KEYWORDS_URL = (
    "events", "press-release", "press_release", "earnings", "news", "quarterly",
    "financial-information", "financial-reports", "quarterly-results", "quarterly-reports",
    "results", "reports", "filings",
)


def _rank_link(text: str, href: str, text_keywords: tuple, url_keywords: tuple) -> int:
    score = 0
    t = (text or "").lower().strip()
    h = (href or "").lower()
    for i, kw in enumerate(text_keywords):
        if kw in t:
            score += 10 - i  # earlier keywords are more preferred
            break
    for kw in url_keywords:
        if kw in h:
            score += 3
            break
    return score


def _best_link(page: Page, text_keywords: tuple, url_keywords: tuple) -> str | None:
    links = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => ({text: (e.innerText || '').trim(), href: e.href}))",
    )
    best, best_score = None, 0
    for l in links:
        sc = _rank_link(l["text"], l["href"], text_keywords, url_keywords)
        if sc > best_score:
            best, best_score = l["href"], sc
    return best


def _ranked_candidates(page: Page, text_keywords: tuple, url_keywords: tuple,
                       limit: int = 5) -> list[str]:
    """Return up to N unique candidate URLs ranked by keyword score."""
    links = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => ({text: (e.innerText || '').trim(), href: e.href}))",
    )
    scored = []
    for l in links:
        sc = _rank_link(l["text"], l["href"], text_keywords, url_keywords)
        if sc > 0:
            scored.append((sc, l["href"]))
    scored.sort(reverse=True)
    out, seen = [], set()
    for _, href in scored:
        if href in seen:
            continue
        seen.add(href)
        out.append(href)
        if len(out) >= limit:
            break
    return out


def _find_ir_page(page: Page, home_url: str) -> str | None:
    try:
        page.goto(home_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return None
    time.sleep(2)
    return _best_link(page, _IR_NAV_KEYWORDS_TEXT, _IR_NAV_KEYWORDS_URL)


def _find_events_page(page: Page, ir_url: str) -> str | None:
    try:
        page.goto(ir_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return None
    time.sleep(2)
    return _best_link(page, _EVENTS_KEYWORDS_TEXT, _EVENTS_KEYWORDS_URL)


def _find_earnings_event_link(page: Page, events_url: str) -> str | None:
    """Return the first link on the listing page whose text/URL looks like an
    earnings release. IR sites almost always sort news reverse-chronologically,
    so the first earnings-keyword match is the most recent call.

    Date-agnostic by design — matching on target_date is fragile because every
    IR site uses a different date format (long-form, slash-delimited, path-segment,
    compact, etc.). Finding the topmost earnings release and later parsing the
    quarter/year from its URL/title handles the variation automatically."""
    try:
        page.goto(events_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return None
    time.sleep(3)
    # Trigger lazy-loaded content by scrolling once
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    links = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => ({text: (e.innerText || '').trim(), href: e.href}))",
    )
    GENERIC_NAV_TEXT = {
        "earnings", "events", "news", "press releases", "quarterly",
        "quarterly results", "financial results", "results", "reports",
        "view all news", "view all events", "view more", "view event",
    }
    # Phrases that indicate an *announcement of an upcoming call*, not a results
    # release. E.g. Altria's "to host webcast of 2026 First Quarter..." comes out
    # weeks before the call; we want the Q4 2025 Results release, not this.
    ANNOUNCEMENT_PATTERNS = (
        "to host", "to announce", "to release", "to report",
        "announces date", "announces timing", "schedules",
        "will host", "will announce", "will release", "will report",
        "webcast of", "conference call details",
    )
    for l in links:
        text = (l["text"] or "").strip()
        href = l["href"] or ""
        blob = (text + " " + href).lower()
        if not is_earnings_event(blob):
            continue
        if text.lower() in GENERIC_NAV_TEXT:
            continue
        if any(pat in blob for pat in ANNOUNCEMENT_PATTERNS):
            continue
        if len(text) < 10 and not any(k in href.lower() for k in ("detail", "press-release", "news-release", "/news/")):
            continue
        return href
    return None


# Shared constants for hop-follow matching. The Playwright path (which has
# access to link text) uses these plus text-based checks; the curl_cffi path
# uses them on URLs only when rendered link text isn't available.
_HOP_DETAIL_PATTERNS = (
    "news-release-details/", "news-release-detail/",
    "press-releases/detail/", "press-release-detail",
    "news-details/", "news-detail",
)
_HOP_ANNOUNCE_PATTERNS = (
    "to-host", "to-announce", "to-release", "to-report",
    "announces-date", "announces-timing", "schedules",
    "will-host", "webcast-of", "conference-call-details",
)
_HOP_EARNINGS_KWS = (
    "earnings", "quarter", "results", "reports-", "reports_",
    "-q1-", "-q2-", "-q3-", "-q4-",
    "first-quarter", "second-quarter",
    "third-quarter", "fourth-quarter",
    "full-year", "fy25", "fy26", "fy-25", "fy-26",
)


def _find_hop_url_from_hrefs(hrefs: list[str], current_url: str = "") -> str | None:
    """URL-only hop-follow matcher. Returns the first href that looks like a
    press-release detail page with earnings keywords and no announcement
    markers. Used by the curl_cffi fallback (Playwright path has richer
    text-aware matching inline). First match wins — IR sites list newest-
    first so the first hit is the most recent."""
    for href in hrefs:
        h = (href or "").lower()
        if not any(pat in h for pat in _HOP_DETAIL_PATTERNS):
            continue
        if any(pat in h for pat in _HOP_ANNOUNCE_PATTERNS):
            continue
        if not any(kw in h for kw in _HOP_EARNINGS_KWS):
            continue
        if current_url and href == current_url:
            continue
        return href
    return None


def _derive_quarter_from_links(hrefs: list[str], target_date: str) -> str:
    """Scan a list of URLs for the first one parse_quarter_label can turn into a
    real `YYYY-QN` label; fall back to the target_date-based label otherwise.

    Use when we've landed on an IR home page (or any URL without a quarter in
    its path) and want to label the quarter correctly — e.g. LW's IR home
    exposes the latest artifacts as /static-files/{uuid} with no quarter info,
    but also links out to `/events/event-details/fiscal-2026-third-quarter-
    earnings-call` which parses cleanly as 2026-Q3."""
    fallback = cse.parse_quarter_label(target_date, target_date)
    for href in hrefs:
        q = cse.parse_quarter_label(href, target_date)
        if q and q != fallback and "-Q" in q:
            return q
    return fallback


def _extract_pdfs_from_html(url: str, event_url: str = "") -> tuple[dict[str, str], list[str]]:
    """HTML-only PDF classifier: fetch via curl_cffi and parse <a> tags.
    Bypasses Playwright/Akamai-HTTP2 issues on Q4 Inc tenants where the press
    release page is server-rendered anyway.

    Returns (pdfs_by_label, all_absolute_hrefs). The second value lets callers
    derive a quarter label from page links when the URL itself lacks one."""
    try:
        r = cc_requests.get(url, impersonate="chrome131", timeout=30)
    except Exception:
        return {}, []
    if r.status_code != 200:
        return {}, []
    import re
    from urllib.parse import urljoin
    html = r.text
    links_raw = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.{0,300}?)</a>', html, re.I | re.S)
    out: dict[str, str] = {}
    all_hrefs: list[str] = []
    generic_pdf_url: str | None = None
    for href, text in links_raw:
        text_clean = re.sub(r"<[^>]+>", " ", text).strip()
        text_clean = re.sub(r"\s+", " ", text_clean)
        t = text_clean.lower()
        h = href.lower()
        abs_href = urljoin(url, href)
        all_hrefs.append(abs_href)
        # Drupal IR sites (e.g. MNST) serve press releases via `/node/{id}/pdf`
        # — treat any URL ending in `/pdf` as a PDF-serving URL even without a
        # `.pdf` extension in the path.
        is_pdf_url = (".pdf" in h) or ("/static-files/" in h) or ("/static_files/" in h) or h.endswith("/pdf")
        if not is_pdf_url:
            continue
        # `"slides" in href` alone is too aggressive — DG's archive has 2016
        # Analyst Day slides as `.../1-MPilkington-Opening_Slides.pdf` that get
        # mis-classified as the current presentation. Require "presentation" or
        # "slide" in the link text for a clean match.
        if "presentation" in t or "slide" in t:
            out.setdefault("presentation", abs_href)
        elif "transcript" in t or "transcript" in h:
            out.setdefault("transcript", abs_href)
        elif "press release" in t or "news release" in t or "earnings release" in t:
            out.setdefault("press_release", abs_href)
        elif generic_pdf_url is None and ("download as pdf" in t or "download pdf" in t
                                          or t == "pdf" or "view pdf" in t
                                          or "pdf version" in t or "full report" in t):
            generic_pdf_url = abs_href
    is_pr_page = any(s in event_url.lower() for s in (
        "press-release", "press_release", "news-release", "news_release",
        "news-details", "news-detail", "/news/",
    ))
    if "press_release" not in out and generic_pdf_url and is_pr_page:
        out["press_release"] = generic_pdf_url
    return out, all_hrefs


def _collect_pdf_links(page: Page, event_url: str = "") -> dict[str, str]:
    """Classify PDF links on an event-detail page into press_release / presentation
    / transcript. Specific labels (slides, transcript) win over generic "download
    as PDF" labels; when we're on a press-release detail page, a generic download
    link is treated as the press release itself.

    Recognizes a link as PDF-serving if the URL has `.pdf` in it OR contains
    `/static-files/` (Q4 Inc's opaque-UUID pattern for hosted PDFs — used by
    MDLZ, COST, and every other Q4 Inc tenant)."""
    links = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => ({text: (e.innerText || '').trim(), href: e.href}))",
    )
    # First pass: specific labels
    out: dict[str, str] = {}
    generic_pdf_url: str | None = None
    for l in links:
        t = (l["text"] or "").lower()
        h = (l["href"] or "").lower()
        # Accept `.pdf` OR Q4 Inc's `/static-files/{uuid}` pattern.
        # Drupal IR sites (e.g. MNST) serve press releases via `/node/{id}/pdf`
        # — treat any URL ending in `/pdf` as a PDF-serving URL even without a
        # `.pdf` extension in the path.
        is_pdf_url = (".pdf" in h) or ("/static-files/" in h) or ("/static_files/" in h) or h.endswith("/pdf")
        if not is_pdf_url:
            continue
        # Match "presentation" or "slide" in link text only — `"slides" in href`
        # alone mis-matches DG's 2016 Analyst Day slides (URLs like
        # `.../1-MPilkington-Opening_Slides.pdf`) as the current presentation.
        if "presentation" in t or "slide" in t:
            out.setdefault("presentation", l["href"])
        elif "transcript" in t or "transcript" in h:
            out.setdefault("transcript", l["href"])
        elif "press release" in t or "news release" in t or "earnings release" in t:
            out.setdefault("press_release", l["href"])
        elif generic_pdf_url is None and ("download as pdf" in t or "download pdf" in t
                                          or t == "pdf" or "view pdf" in t
                                          or "pdf version" in t or "full report" in t):
            generic_pdf_url = l["href"]
    # Second pass: if we didn't find an explicit press release but we're on a
    # press-release/news page and have a generic download link, use that.
    is_pr_page = any(s in event_url.lower() for s in (
        "press-release", "press_release", "news-release", "news_release",
        "news-details", "news-detail", "/news/",
    ))
    if "press_release" not in out and generic_pdf_url and is_pr_page:
        out["press_release"] = generic_pdf_url
    return out


# Link-text tokens that signal an audio download on Q4 Inc-style opaque URLs
# (KMB's "Pre-Recorded Management Discussion (Audio)" at /static-files/{uuid}
# has no `.mp3` extension — only the text reveals it's audio).
_AUDIO_TEXT_SIGNALS = ("(audio)", " audio ", "audio version", "mp3", "m4a", "(wav)")

# Content-Type → file extension mapping for opaque-URL downloads where the
# href has no extension. Fallback to mp3 if the server doesn't send a useful
# Content-Type.
_AUDIO_CT_TO_EXT = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
}


def _looks_like_audio_text(text: str, href: str) -> bool:
    """Text-based audio hint — catches Q4 Inc opaque URLs (e.g. KMB's
    `/static-files/{uuid}` pointing at an MP3, where only the anchor text
    reveals it's audio). Excludes PDF-serving URLs explicitly."""
    t = (text or "").lower()
    h = (href or "").lower()
    if ".pdf" in h or h.endswith("/pdf"):
        return False
    return any(sig in t for sig in _AUDIO_TEXT_SIGNALS)


def _audio_ext_from_response(url: str, referer: str | None = None) -> str:
    """HEAD the URL, map Content-Type to a file extension. Falls back to mp3."""
    try:
        headers = {"Accept": "audio/*,*/*"}
        if referer:
            headers["Referer"] = referer
        r = cc_requests.head(url, impersonate="chrome131", headers=headers,
                             timeout=15, allow_redirects=True)
        ct = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        return _AUDIO_CT_TO_EXT.get(ct, "mp3")
    except Exception:
        return "mp3"


def _scan_and_download_audio(page: Page, ticker: str, target_date: str,
                              event_url: str, audio_dir: Path,
                              semi_auto: bool = False) -> list[Artifact]:
    """Scan the page's <a> tags and dispatch to the right downloader based on
    the webcast vendor matched. Returns a list with one Artifact on the first
    success, or [] if nothing was found / all attempts failed.

    semi_auto=True pauses for manual CAPTCHA solving on vendors that require
    it (Mediasite)."""
    try:
        links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({text: (e.innerText||'').trim(), href: e.href}))",
        )
    except Exception:
        return []
    # Also scan iframes. Some IR sites embed the player directly rather than
    # linking out — TGT's event-details pages are the reference case: a single
    # `<iframe src="https://www.youtube.com/embed/{id}">`. Treat src as href.
    try:
        frames = page.eval_on_selector_all(
            "iframe[src]",
            "els => els.map(e => ({text: (e.title || e.name || '').trim(), href: e.src}))",
        )
        links = list(links) + list(frames)
    except Exception:
        pass

    # Dedupe by URL AND by failed-vendor-when-systemic: IR pages commonly link
    # the same webcast multiple times (sidebar + inline + footer) or link
    # multiple events of the same vendor (current + past earnings calls for
    # Q4 Inc). We need to distinguish:
    #   - Systemic failures (mediasite reCAPTCHA) — all same-vendor links
    #     will fail; skip subsequent ones after first failure.
    #   - Per-event failures (Q4 Inc attendee 12345 is a future event
    #     with no recording) — other same-vendor links could be past
    #     events with recordings; keep trying.
    # _DEDUPE_ON_VENDOR_FAILURE lists vendors where first-fail-skip-rest is
    # correct. Q4 Inc is excluded because each attendee URL is a different
    # event.
    seen: set[str] = set()
    failed_vendors: set[str] = set()
    for l in links:
        href = l["href"] or ""
        text = l["text"] or ""
        if href in seen:
            continue
        seen.add(href)

        vendor = classify_webcast_url(href, text)
        if vendor in failed_vendors and vendor in _DEDUPE_ON_VENDOR_FAILURE:
            continue

        # Direct-extension match OR text-signaled audio on a non-vendor URL.
        # The text-signal fallback only fires when no known vendor matched —
        # otherwise a Mediasite/Q4/West-Intrado page with "Listen to audio
        # webcast" in the link text would be wrongly treated as a direct file.
        is_direct = vendor == "direct_audio" or (
            vendor in (None, "(unknown)") and _looks_like_audio_text(text, href)
        )
        if is_direct:
            h_path = href.split("?")[0].split("#")[0]
            ext = (h_path.rsplit(".", 1)[-1].lower()
                   if "." in h_path.rsplit("/", 1)[-1]
                   else _audio_ext_from_response(href, referer=event_url))
            dest = audio_dir / f"{ticker}_{target_date}.{ext}"
            try:
                download_audio_file(href, dest, referer=event_url)
                print(f"     [audio] direct_audio downloaded: {dest.name}")
                return [Artifact("audio", dest, href)]
            except Exception as e:
                print(f"     [audio] direct_audio failed ({href[:80]}): {e}")
            continue

        if vendor == "youtube_live":
            dest = audio_dir / f"{ticker}_{target_date}.m4a"
            try:
                download_youtube_audio(href, dest)
                final = dest if dest.exists() else next(
                    audio_dir.glob(f"{ticker}_{target_date}.*"), dest
                )
                print(f"     [audio] youtube_live downloaded: {final.name}")
                return [Artifact("audio", final, href)]
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr.decode("utf-8", errors="replace") if e.stderr else "")[:400]
                print(f"     [audio] yt-dlp failed: {stderr}")
            except Exception as e:
                print(f"     [audio] youtube_live failed: {e}")
            continue

        if vendor == "west_intrado":
            # Register on the West/Intrado form, sniff the .m3u8 URL from
            # network traffic, then ffmpeg it to m4a. Sniffer navigates `page`
            # away from the event-detail URL — fine since the caller returns
            # right after audio extraction (next candidate gets a fresh goto).
            print(f"     [audio] west_intrado: sniffing HLS from {href[:100]}")
            try:
                hls_url = _sniff_west_intrado_hls(page, href, timeout_s=90)
            except Exception as e:
                print(f"     [audio] west_intrado sniff raised: {e}")
                failed_vendors.add(vendor)
                continue
            if not hls_url:
                print(f"     [audio] west_intrado: no HLS URL captured")
                failed_vendors.add(vendor)
                continue
            dest = audio_dir / f"{ticker}_{target_date}.m4a"
            try:
                download_hls_to_m4a(hls_url, dest)
                print(f"     [audio] west_intrado downloaded: {dest.name}")
                return [Artifact("audio", dest, href)]
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr.decode("utf-8", errors="replace") if e.stderr else "")[:400]
                print(f"     [audio] ffmpeg HLS failed: {stderr}")
            except FileNotFoundError:
                print(f"     [audio] ffmpeg not on PATH")
            except Exception as e:
                print(f"     [audio] west_intrado download failed: {e}")

        if vendor == "choruscall":
            # ChorusCall registration → direct MP4 download. Cleanest
            # vendor behind Q4 Inc — no reCAPTCHA, no SPA quirks, just a
            # classic HTML form. See _sniff_choruscall_mp4 for shape.
            print(f"     [audio] choruscall: registering on {href[:100]}")
            try:
                mp4_url = _sniff_choruscall_mp4(page, href, timeout_s=60)
            except Exception as e:
                print(f"     [audio] choruscall sniff raised: {e}")
                continue
            if not mp4_url:
                print(f"     [audio] choruscall: no MP4 URL captured")
                continue
            dest = audio_dir / f"{ticker}_{target_date}.mp4"
            try:
                download_audio_file(mp4_url, dest, referer=href)
                print(f"     [audio] choruscall downloaded: {dest.name}")
                return [Artifact("audio", dest, href)]
            except Exception as e:
                print(f"     [audio] choruscall download failed: {e}")

        if vendor == "q4_inc_attendee":
            # Q4 Inc's guest flow is the cleanest of the form-gated vendors —
            # no reCAPTCHA, and the recording is served as a direct MP4 from
            # static.events.q4inc.com. Sniffer walks the React SPA registration.
            print(f"     [audio] q4_inc: registering on {href[:100]}")
            try:
                mp4_url = _sniff_q4_inc_mp4(page, href, timeout_s=60)
            except Exception as e:
                print(f"     [audio] q4_inc sniff raised: {e}")
                failed_vendors.add(vendor)
                continue
            if not mp4_url:
                print(f"     [audio] q4_inc: no MP4 URL captured")
                failed_vendors.add(vendor)
                continue
            dest = audio_dir / f"{ticker}_{target_date}.mp4"
            try:
                download_audio_file(mp4_url, dest, referer=href)
                print(f"     [audio] q4_inc downloaded: {dest.name}")
                return [Artifact("audio", dest, href)]
            except Exception as e:
                print(f"     [audio] q4_inc download failed: {e}")

        if vendor == "mediasite":
            # Mediasite guestbook form is gated by a reCAPTCHA — auto submit
            # will fail when the site flags Playwright. `--semi-auto` opens a
            # headed browser, pauses, and lets the user solve + click submit
            # manually. Auto mode still worth attempting on events that never
            # set reCAPTCHA (rare but happens on unlisted / private webcasts).
            print(f"     [audio] mediasite: sniffing HLS from {href[:100]}"
                  + (" (semi-auto)" if semi_auto else ""))
            try:
                hls_url = _sniff_mediasite_hls(page, href, timeout_s=120,
                                               semi_auto=semi_auto)
            except Exception as e:
                print(f"     [audio] mediasite sniff raised: {e}")
                failed_vendors.add(vendor)
                continue
            if not hls_url:
                print(f"     [audio] mediasite: no HLS URL captured"
                      + ("" if semi_auto else " (retry with --semi-auto)"))
                failed_vendors.add(vendor)
                continue
            dest = audio_dir / f"{ticker}_{target_date}.m4a"
            try:
                download_hls_to_m4a(hls_url, dest)
                print(f"     [audio] mediasite downloaded: {dest.name}")
                return [Artifact("audio", dest, href)]
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr.decode("utf-8", errors="replace") if e.stderr else "")[:400]
                print(f"     [audio] ffmpeg HLS failed: {stderr}")
            except FileNotFoundError:
                print(f"     [audio] ffmpeg not on PATH")
            except Exception as e:
                print(f"     [audio] mediasite download failed: {e}")
    return []


def _try_extract_audio_from_page(page: Page, ticker: str, target_date: str,
                                  event_url: str, audio_dir: Path,
                                  semi_auto: bool = False) -> list[Artifact]:
    """Two-pass audio extraction:
      1. Scan the current page (where PDFs were just found).
      2. If nothing surfaced, drill into the first plausible earnings event-
         detail URL on the page and scan there. IR-home fast-path tickers
         (LW, MKC, HSY) typically have PDFs on the home but webcast links only
         on the event-detail sub-page.

    Vendor dispatch is handled by `_scan_and_download_audio`. Drill-in picks
    the first href that looks like an earnings event-detail URL and isn't an
    announcement ("to-host", "announces") or the same URL we're already on."""
    hits = _scan_and_download_audio(page, ticker, target_date, event_url,
                                     audio_dir, semi_auto=semi_auto)
    if hits:
        return hits

    # Drill-in pass. Find a candidate event-detail URL from the current page's
    # hrefs. Reuses the constants _HOP_DETAIL_PATTERNS / _HOP_ANNOUNCE_PATTERNS
    # / _HOP_EARNINGS_KWS already used by the PDF hop-follow path.
    try:
        links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({text: (e.innerText||'').trim(), href: e.href}))",
        )
    except Exception:
        return []
    # For audio drill-in we prefer event-details URLs over news-release URLs —
    # the webcast player link lives on the event-details page; news-release
    # pages are text only. LW's IR home links to both; we want the former.
    hop_url: str | None = None
    for l in links:
        h = (l["href"] or "").lower()
        t = (l["text"] or "").lower()
        if "/events/event-details/" not in h and "/event-details/" not in h:
            continue
        if any(pat in h for pat in _HOP_ANNOUNCE_PATTERNS):
            continue
        if any(kw in h or kw in t for kw in _HOP_EARNINGS_KWS):
            hop_url = l["href"]
            break
    # Fallback: the PR-hop target (news-release/press-release-detail). Less
    # likely to have the webcast URL but some IR sites embed it there too.
    if not hop_url:
        hrefs = [l["href"] for l in links if l.get("href")]
        hop_url = _find_hop_url_from_hrefs(hrefs, current_url=event_url)
    if not hop_url or hop_url.rstrip("/").lower() == (event_url or "").rstrip("/").lower():
        return []

    print(f"     [audio] no audio on current page; drilling into {hop_url[:100]}")
    try:
        page.goto(hop_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
    except Exception as e:
        print(f"     [audio] drill-in goto failed: {e}")
        return []
    return _scan_and_download_audio(page, ticker, target_date, hop_url,
                                     audio_dir, semi_auto=semi_auto)


def _resolve_ir_starting_point(ticker: str, ir_url: str) -> str | None:
    """Return a URL we can navigate to first — either IR_URLS override or the
    corporate website from yfinance (which will be crawled to find IR)."""
    if ir_url:
        return ir_url
    try:
        info = yf.Ticker(ticker).info or {}
        return info.get("website") or info.get("irWebsite")
    except Exception:
        return None


def _derive_alt_roots(url: str) -> list[str]:
    """From any URL, derive alternate root URLs by swapping the subdomain for
    common corporate-site variants on the apex domain.

    Handles the case where yfinance returns a stub IR landing (e.g.
    `stock.walmart.com`) but the actual press releases live on a sibling
    subdomain (`corporate.walmart.com/news/...`)."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
    except Exception:
        return []
    host = (parsed.netloc or "").lower()
    if not host:
        return []
    parts = host.split(".")
    apex = ".".join(parts[-2:]) if len(parts) >= 2 else host
    candidates = [
        f"https://corporate.{apex}",
        f"https://news.{apex}",
        f"https://newsroom.{apex}",
        f"https://www.{apex}",
        f"https://{apex}",
    ]
    out, seen = [], {url.lower().rstrip("/")}
    for c in candidates:
        key = c.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _try_common_ir_subpaths(ir_url: str) -> list[str]:
    """When the IR page's nav yields no keyword-matching links (often because the
    page is a JS-rendered SPA we didn't wait long enough for, or a minimalist
    landing page that links out to subdomains), brute-force common subpath URLs.
    Returns a list of URLs that responded 200 OK — caller can treat these as
    candidates to search for the target event."""
    from urllib.parse import urljoin
    base = ir_url.rstrip("/") + "/"
    paths = [
        "news-releases", "news", "press-releases", "press",
        "events", "events-and-presentations", "events-presentations",
        "quarterly-results", "financial-information", "financials",
        "financial-reports", "quarterly-reports",
        "investor-news", "news-and-events", "sec-filings",
    ]
    found: list[str] = []
    for p in paths:
        url = urljoin(base, p)
        try:
            r = cc_requests.get(url, impersonate="chrome131", timeout=8, allow_redirects=True)
            if r.status_code != 200:
                continue
            body = (r.text or "").lower()
            if any(k in body for k in ("press release", "earnings", "quarterly", "results")):
                found.append(str(r.url))
        except Exception:
            pass
    return found


def _try_common_ir_patterns(website: str) -> str | None:
    """Try well-known IR subdomain/path patterns. Returns the first URL that
    responds 200 and has IR-ish content. Saves the crawl step for big-cap sites
    whose corporate homepage buries the IR link in JS mega-menus (COST, PEP)."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(website)
    except Exception:
        return None
    host = (parsed.netloc or parsed.path).replace("www.", "").strip("/")
    if not host:
        return None
    base_path = website.rstrip("/")
    candidates = [
        f"https://investors.{host}",
        f"https://investor.{host}",  # HRL, CHD use singular
        f"https://ir.{host}",
        f"{base_path}/investors",
        f"{base_path}/investor-relations",
        f"{base_path}/investor",
    ]
    for url in candidates:
        try:
            r = cc_requests.get(url, impersonate="chrome131", timeout=8, allow_redirects=True)
            if r.status_code != 200:
                continue
            body = (r.text or "").lower()
            if any(k in body for k in ("press release", "earnings", "quarterly", "sec filing")):
                return str(r.url)
        except Exception:
            pass
    return None


def generic_backend(ticker: str, ir_url: str, target_date: str, page: Page,
                    semi_auto: bool = False) -> ScrapeResult:
    result = ScrapeResult(ticker=ticker, event_date=target_date)
    start = _resolve_ir_starting_point(ticker, ir_url)
    if not start:
        result.errors.append("no IR URL in config and no website from yfinance")
        return result
    print(f"     [generic] start={start}")

    # Step 1: resolve an IR page. Three-pass strategy, cheapest first:
    #   (a) if start URL already looks IR-ish, use it directly
    #   (b) try common IR URL patterns (investors.X, ir.X, X/investors) via curl_cffi
    #       — fast and works for big-caps (COST, PEP) whose corp homepage buries
    #       the "Investors" link in a JS-rendered mega-menu
    #   (c) fall back to crawling the corporate homepage for nav links
    start_lower = start.lower()
    if any(k in start_lower for k in ("investor", "/ir/", "ir.", "investors.", "stock.")):
        ir = start
    else:
        ir = _try_common_ir_patterns(start)
        if ir:
            print(f"     [generic] IR via URL pattern: {ir}")
        else:
            ir = _find_ir_page(page, start)
            if not ir:
                result.errors.append(f"could not find IR link from corp homepage {start}")
                return result
            print(f"     [generic] IR via crawl: {ir}")

    # Step 2: collect candidate sub-pages (press releases / events / quarterly results /
    # financial information). IR sites vary on which page holds the target event:
    # past earnings releases usually live under "Press Releases" or "Quarterly Results";
    # upcoming earnings calls under "Events". Try each in score order until one
    # actually yields PDFs.
    try:
        page.goto(ir, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass
    time.sleep(2)
    candidates = _ranked_candidates(page, _EVENTS_KEYWORDS_TEXT, _EVENTS_KEYWORDS_URL, limit=6)
    # Also include the IR home page itself — some tickers (Lamb Weston) list every
    # earnings artifact (press release, presentation, transcript) directly on the
    # IR home page with no sub-navigation required.
    if ir and ir not in candidates:
        candidates.append(ir)
    if not candidates:
        # Fallback: brute-force common subpath URLs when nav crawling fails.
        # Happens on JS-heavy SPA IR sites (Q4 Inc tenants) and minimalist
        # landing pages (stock.walmart.com) where the nav links aren't present
        # in the initial DOM or don't match our keyword set.
        # Try BOTH the resolved IR URL and the original corporate homepage —
        # for companies like WMT, the IR URL points at a stub (stock.walmart.com)
        # but the actual press releases live on corporate.walmart.com/news/.
        seen_roots = set()
        seen_cands = set()
        fallback_roots: list[str] = []
        def _add_root(u: str | None) -> None:
            if not u: return
            key = u.lower().rstrip("/")
            if key in seen_roots: return
            seen_roots.add(key)
            fallback_roots.append(u)
        _add_root(ir)
        _add_root(start)
        # Sibling-subdomain alternates: `stock.walmart.com` → `corporate.walmart.com`
        # etc. Covers yfinance-returned stub hosts.
        for alt in _derive_alt_roots(ir):
            _add_root(alt)
        if start:
            for alt in _derive_alt_roots(start):
                _add_root(alt)
        for root in fallback_roots:
            print(f"     [generic] no nav candidates; trying common subpaths under {root}")
            for u in _try_common_ir_subpaths(root):
                if u not in seen_cands:
                    seen_cands.add(u)
                    candidates.append(u)
    if not candidates:
        result.errors.append(
            f"could not find any events/press candidates from {ir} (also tried corp homepage {start})"
        )
        return result
    print(f"     [generic] candidate pages: {len(candidates)}")
    for c in candidates:
        print(f"        · {c}")

    # Step 3: walk candidates until one yields PDFs. Each candidate is either
    # (a) already a specific earnings event page (URL contains year + quarter/results
    # keyword), or (b) a listing page we search for a child event link.
    # Webcast-portal URLs (Q4 Inc attendee, Mediasite, Intrado) are audio-only and
    # filtered out — they never contain PDFs, so landing there wastes effort.
    def _url_is_earnings_event(url: str) -> bool:
        """Does the URL itself look like a specific earnings event detail page
        (not a listing)? Date-agnostic — we trust that navigating to it will
        yield PDFs for *some* quarter, and parse the quarter label from the URL
        later. IR sites list newest-first so this naturally picks the most recent."""
        u = url.lower()
        return any(k in u for k in (
            "-q1-", "-q2-", "-q3-", "-q4-",
            "first-quarter", "second-quarter", "third-quarter", "fourth-quarter",
            "earnings-release", "earnings-press-release", "-earnings-", "_earnings_",
            "quarterly-results", "full-year-results", "annual-results",
        ))

    def _is_webcast_portal(url: str) -> bool:
        u = url.lower()
        return any(host in u for host in (
            "events.q4inc.com/attendee",
            "edge.media-server.com",
            "event.webcasts.com",
            "webcasts.com/starthere",
            "wsw.com/webcast",
        ))

    def _resolve_candidate_to_event_url(cand: str) -> str | None:
        if _is_webcast_portal(cand):
            return None
        if _url_is_earnings_event(cand):
            return cand
        found = _find_earnings_event_link(page, cand)
        if found:
            return found
        # Last resort: use the candidate URL itself as an event URL. IR home pages
        # (LW) sometimes list all earnings artifacts directly; the PDF extractor's
        # curl_cffi fallback will pick them up even when Playwright's view is empty.
        return cand

    # Quarter + target dirs derived once; the exact quarter may be re-parsed
    # later from the post-redirect event detail URL for slightly better accuracy.
    quarter = cse.parse_quarter_label(target_date, target_date)  # initial fallback
    transcripts_d = cse.ticker_transcripts_dir(ticker, quarter)
    presentation_d = cse.ticker_presentation_dir(ticker, quarter)

    def _try_extract_from_event_url(event_url: str) -> list[Artifact]:
        """Try to download PDFs from a single event URL. Returns list of new
        artifacts (empty = nothing found, caller should try next candidate)."""
        nonlocal quarter, transcripts_d, presentation_d
        q = cse.parse_quarter_label(event_url, target_date)
        if q != quarter:
            quarter = q
            transcripts_d = cse.ticker_transcripts_dir(ticker, q)
            presentation_d = cse.ticker_presentation_dir(ticker, q)
        result.quarter = quarter
        artifacts: list[Artifact] = []

        # Direct-PDF smell test
        if (".pdf" in event_url.lower() or "earnings-release" in event_url.lower()
                or "press-release" in event_url.lower() and event_url.endswith((".pdf", "/"))):
            if ".pdf" in event_url.lower():
                dest = transcripts_d / f"{ticker}_{target_date}_press_release.pdf"
                try:
                    download_pdf(event_url, dest)
                    artifacts.append(Artifact("press_release", dest, event_url))
                    return artifacts
                except Exception as e:
                    print(f"     [generic] direct-PDF failed ({e}); trying page.goto()")

        try:
            page.goto(event_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            if "Download is starting" in str(e):
                # Playwright refuses to navigate to a file-download response; treat
                # as a direct press release PDF and download it.
                print(f"     [generic] goto hit a download — routing to direct PDF fetch")
                dest = transcripts_d / f"{ticker}_{target_date}_press_release.pdf"
                try:
                    download_pdf(event_url, dest)
                    artifacts.append(Artifact("press_release", dest, event_url))
                    return artifacts
                except Exception as e2:
                    print(f"     [generic] direct PDF fallback failed: {e2}")
                    return artifacts  # empty
            # Akamai-fronted IR sites (LW, COST Q4 Inc tenants) RST_STREAM Playwright's
            # HTTP/2 requests with ERR_HTTP2_PROTOCOL_ERROR regardless of headers.
            # curl_cffi with Chrome TLS impersonation bypasses this; the HTML classifier
            # can still extract PDFs if the page is server-rendered.
            print(f"     [generic] Playwright goto failed ({type(e).__name__}); trying curl_cffi HTML fallback")
            pdfs_from_html, hrefs = _extract_pdfs_from_html(event_url, event_url=event_url)

            # If direct PDFs aren't on this page, try hop-follow via curl_cffi.
            # E.g. MNST's IR home lists the latest earnings press release as
            # /news-releases/news-release-details/monster-beverage-reports-…-fourth-quarter…
            # with no PDF on the home itself. Hop to the detail page and extract
            # there. This was previously only available in the Playwright-success
            # path — extending it here unlocks Akamai-blocked tenants.
            hop_pdfs_used = False
            if not pdfs_from_html:
                hop_url = _find_hop_url_from_hrefs(hrefs, current_url=event_url)
                if hop_url:
                    print(f"     [generic] curl_cffi hop-follow to {hop_url[:100]}")
                    hop_pdfs, hop_hrefs = _extract_pdfs_from_html(hop_url, event_url=hop_url)
                    if hop_pdfs:
                        pdfs_from_html = hop_pdfs
                        # Prefer the hop URL + its links for quarter derivation;
                        # the hop URL itself usually carries the quarter in its slug.
                        hrefs = [hop_url] + hop_hrefs
                        event_url = hop_url
                        hop_pdfs_used = True
                        print(f"     [generic] PDFs after curl_cffi hop: {list(hop_pdfs.keys())}")

            if pdfs_from_html:
                label_source = "curl_cffi hop" if hop_pdfs_used else "curl_cffi after Playwright failure"
                print(f"     [generic] PDFs via {label_source}: {list(pdfs_from_html.keys())}")
                # If event_url is the IR home (no quarter in its path), derive
                # the quarter from earnings links elsewhere on the page.
                q_derived = _derive_quarter_from_links(hrefs, target_date)
                if q_derived != quarter:
                    quarter = q_derived
                    transcripts_d = cse.ticker_transcripts_dir(ticker, q_derived)
                    presentation_d = cse.ticker_presentation_dir(ticker, q_derived)
                    result.quarter = quarter
                dest_for = {
                    "press_release": transcripts_d / f"{ticker}_{target_date}_press_release.pdf",
                    "presentation": presentation_d / f"{ticker}_{target_date}_presentation.pdf",
                    "transcript": transcripts_d / f"{ticker}_{target_date}_transcript.pdf",
                }
                for label, url in pdfs_from_html.items():
                    dest = dest_for.get(label)
                    if not dest:
                        continue
                    try:
                        download_pdf(url, dest, referer=event_url)
                        artifacts.append(Artifact(label, dest, url))
                    except Exception as dl_err:
                        result.errors.append(f"{label} download failed: {dl_err}")
                return artifacts
            print(f"     [generic] event-detail navigation failed: {e}")
            return artifacts  # empty
        time.sleep(3)
        event_detail_url = page.url
        pdfs = _collect_pdf_links(page, event_url=event_detail_url)
        print(f"     [generic] PDFs found: {list(pdfs.keys())}")
        # Hrefs seen on this page — used later to derive the quarter label when
        # event_detail_url lacks quarter info (IR home pages, Q4 Inc stub pages).
        # Populate from Playwright up front so even the direct-_collect_pdf_links
        # success path benefits from link-based quarter derivation.
        try:
            hrefs_for_quarter: list[str] = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.href)"
            )
        except Exception:
            hrefs_for_quarter = []
        if not pdfs:
            # curl_cffi fallback on the same URL. Some IR home pages (LW) list all
            # earnings artifacts directly but are JS-heavy — Playwright's default
            # wait captures nothing while curl_cffi sees the server-rendered HTML.
            pdfs_from_html, hrefs_from_html = _extract_pdfs_from_html(event_detail_url, event_url=event_detail_url)
            if pdfs_from_html:
                pdfs = pdfs_from_html
                hrefs_for_quarter = hrefs_from_html
                print(f"     [generic] PDFs via curl_cffi fallback: {list(pdfs.keys())}")
        if not pdfs:
            # Hop-follow: if the page has no PDFs but contains a link to what
            # looks like a press-release-detail page (Q4 Inc patterns), follow
            # it once. MDLZ's `/news/2025_q4_fy_earnings/` page is a summary that
            # links out to the real press-release detail on `ir.mondelezinternational.com`.
            try:
                links = page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => ({text: (e.innerText || '').trim(), href: e.href}))",
                )
                hop_url = None
                ANNOUNCE = ("to-host", "to-announce", "to-release", "to-report",
                            "announces-date", "announces-timing", "schedules",
                            "will-host", "webcast-of", "conference-call-details")
                EARNINGS_KWS = ("earnings", "quarter", "results", "reports-", "reports_",
                                "-q1-", "-q2-", "-q3-", "-q4-",
                                "first-quarter", "second-quarter",
                                "third-quarter", "fourth-quarter",
                                "full-year", "fy25", "fy26", "fy-25", "fy-26")
                for l in links:
                    h = (l["href"] or "").lower()
                    t = (l["text"] or "").lower()
                    if not any(pat in h for pat in (
                        "news-release-details/", "news-release-detail/",
                        "press-releases/detail/", "press-release-detail",
                        "news-details/", "news-detail",
                    )):
                        continue
                    # Skip "to host webcast" / "announces date" style announcements —
                    # these point at an upcoming-call calendar post, not results.
                    if any(pat in h for pat in ANNOUNCE) or any(
                            pat.replace("-", " ") in t for pat in ANNOUNCE):
                        continue
                    # Require the hop target to look like an earnings release, not
                    # a product/partnership/executive-change press release.
                    if not any(kw in h or kw.replace("-", " ") in t for kw in EARNINGS_KWS):
                        continue
                    hop_url = l["href"]
                    break
                if hop_url and hop_url != event_detail_url:
                    print(f"     [generic] hop-follow to {hop_url[:100]}")
                    hop_ok = False
                    try:
                        page.goto(hop_url, wait_until="domcontentloaded", timeout=30000)
                        time.sleep(3)
                        event_detail_url = page.url
                        pdfs = _collect_pdf_links(page, event_url=event_detail_url)
                        print(f"     [generic] PDFs after hop (Playwright): {list(pdfs.keys())}")
                        hop_ok = True
                    except Exception as e:
                        print(f"     [generic] Playwright hop failed ({type(e).__name__}); trying curl_cffi")
                    # curl_cffi fallback — server-rendered Q4 Inc detail pages
                    # expose PDF links in plain HTML, so no JS rendering needed.
                    if not hop_ok or not pdfs:
                        pdfs_from_html, hrefs_from_html = _extract_pdfs_from_html(hop_url, event_url=hop_url)
                        if pdfs_from_html:
                            event_detail_url = hop_url
                            pdfs = pdfs_from_html
                            hrefs_for_quarter = hrefs_from_html
                            print(f"     [generic] PDFs after hop (curl_cffi): {list(pdfs.keys())}")
            except Exception:
                pass
        if not pdfs:
            # Final fallback: render the page itself to PDF. Some IR sites (DG)
            # publish earnings press releases as HTML-only articles with no
            # downloadable file — the web page IS the press release. If we're
            # on a press-release-detail URL with earnings content, render it.
            is_pr_detail = any(s in event_detail_url.lower() for s in (
                "news-detail", "press-release/detail", "news-release-details",
                "news-release-detail", "press-releases/detail", "/news-release/",
            ))
            if is_pr_detail:
                try:
                    body_text = (page.eval_on_selector("body", "el => el.innerText || ''") or "")[:8000].lower()
                except Exception:
                    body_text = ""
                has_earnings_content = any(k in body_text for k in (
                    "earnings", "quarterly results", "fourth quarter", "third quarter",
                    "second quarter", "first quarter", "fiscal year",
                ))
                if has_earnings_content:
                    # Derive quarter from URL / hrefs before choosing the dest dir.
                    q_render = cse.parse_quarter_label(event_detail_url, target_date)
                    date_fallback = cse.parse_quarter_label(target_date, target_date)
                    if q_render == date_fallback and hrefs_for_quarter:
                        q_render = _derive_quarter_from_links(hrefs_for_quarter, target_date)
                    if q_render != quarter:
                        quarter = q_render
                        transcripts_d = cse.ticker_transcripts_dir(ticker, q_render)
                        presentation_d = cse.ticker_presentation_dir(ticker, q_render)
                        result.quarter = quarter
                    dest = transcripts_d / f"{ticker}_{target_date}_press_release.pdf"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        page.emulate_media(media="print")
                        page.pdf(path=str(dest), format="Letter",
                                 margin={"top":"0.5in","bottom":"0.5in","left":"0.5in","right":"0.5in"},
                                 print_background=True)
                        artifacts.append(Artifact("press_release", dest, event_detail_url))
                        print(f"     [generic] rendered page-to-PDF as press release: {dest.name}")
                        return artifacts
                    except Exception as e:
                        print(f"     [generic] page.pdf() failed: {e}")
            return artifacts  # empty — caller tries next candidate

        # Re-parse quarter from the post-redirect URL (slightly more accurate).
        # If the URL itself has no quarter info (IR home page, stub landing),
        # fall back to scanning page links for a quarter-bearing URL — e.g. LW's
        # IR home links out to /events/event-details/fiscal-2026-third-quarter-
        # earnings-call which parses cleanly as 2026-Q3.
        q2 = cse.parse_quarter_label(event_detail_url, target_date)
        date_fallback = cse.parse_quarter_label(target_date, target_date)
        if q2 == date_fallback and hrefs_for_quarter:
            q2 = _derive_quarter_from_links(hrefs_for_quarter, target_date)
        if q2 != quarter:
            quarter = q2
            transcripts_d = cse.ticker_transcripts_dir(ticker, q2)
            presentation_d = cse.ticker_presentation_dir(ticker, q2)
            result.quarter = quarter

        dest_for = {
            "press_release": transcripts_d / f"{ticker}_{target_date}_press_release.pdf",
            "presentation": presentation_d / f"{ticker}_{target_date}_presentation.pdf",
            "transcript": transcripts_d / f"{ticker}_{target_date}_transcript.pdf",
        }
        for label, url in pdfs.items():
            dest = dest_for.get(label)
            if not dest:
                continue
            try:
                download_pdf(url, dest, referer=event_detail_url)
                artifacts.append(Artifact(label, dest, url))
            except Exception as e:
                result.errors.append(f"{label} download failed: {e}")

        # If press_release is still missing after downloading classified PDFs,
        # look for a text-labeled "Press Release" / "News Release" link that
        # points at a news-detail URL (HTML-only press release, no PDF file —
        # DG's pattern). Navigate there and render the page to PDF.
        already_have_pr = any(a.kind == "press_release" for a in artifacts)
        if not already_have_pr:
            try:
                all_links = page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => ({text: (e.innerText||'').trim(), href: e.href}))",
                )
            except Exception:
                all_links = []
            _PR_TEXT_KWS = ("press release", "news release", "earnings release")
            _PR_URL_PATTERNS = ("news-detail", "press-release/detail", "news-release-details",
                                "news-release-detail", "press-releases/detail", "/news-release/")
            html_pr_url = None
            for l in all_links:
                t = (l["text"] or "").lower().strip()
                h = (l["href"] or "").lower()
                if t not in _PR_TEXT_KWS:  # require exact label (not "press releases" nav)
                    continue
                if not any(p in h for p in _PR_URL_PATTERNS):
                    continue
                html_pr_url = l["href"]
                break
            if html_pr_url:
                print(f"     [generic] HTML press release fallback: rendering {html_pr_url[:100]}")
                try:
                    page.goto(html_pr_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3)
                    dest = transcripts_d / f"{ticker}_{target_date}_press_release.pdf"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    page.emulate_media(media="print")
                    page.pdf(path=str(dest), format="Letter",
                             margin={"top":"0.5in","bottom":"0.5in","left":"0.5in","right":"0.5in"},
                             print_background=True)
                    artifacts.append(Artifact("press_release", dest, html_pr_url))
                    print(f"     [generic] press_release rendered from HTML: {dest.name}")
                except Exception as e:
                    print(f"     [generic] HTML press release render failed: {e}")

        # Audio extraction. Vendor dispatch inside _scan_and_download_audio:
        # direct_audio + youtube_live (fully auto), west_intrado + mediasite
        # (registration-form sniffers; mediasite may need --semi-auto for
        # reCAPTCHA). Q4 Inc + other vendors still pending.
        if not any(a.kind == "audio" for a in artifacts):
            audio_d = cse.ticker_audio_dir(ticker, quarter)
            audio_arts = _try_extract_audio_from_page(
                page, ticker, target_date, event_detail_url, audio_d,
                semi_auto=semi_auto
            )
            artifacts.extend(audio_arts)

        return artifacts

    # Fast-path: some IR sites (Lamb Weston's Drupal-based landing is the reference
    # case) expose the latest quarter's Earnings Presentation + Press Release +
    # Transcript PDFs directly on the IR home page as `/static-files/{uuid}` or
    # `.pdf` links labeled "Earnings Presentation" / "Press Release" / "Transcript".
    # CMS widgets auto-update these to point at the most recent quarter, so when
    # present they are authoritative — no need to drill into sub-navigation.
    # Try the IR home URL directly; if it yields classifiable PDFs, return early.
    print(f"     [generic] IR-home fast-path: {ir}")
    direct_arts = _try_extract_from_event_url(ir)
    if direct_arts:
        result.artifacts.extend(direct_arts)
        result.note = "via generic_backend (IR-home direct)"
        # Post-fast-path audio walk: IR home commonly surfaces only PDFs (press
        # release + presentation + transcript links). The actual webcast URL
        # typically lives on an "events-and-presentations" or "events-calendar"
        # sub-page. If we got PDFs but no audio, scan each candidate for audio
        # only — don't repeat the PDF extraction. Covers CAG, BG, CHD, CLX,
        # KDP, MKC, PEP, EL, DG (all confirmed via webcast survey).
        if not any(a.kind == "audio" for a in result.artifacts):
            audio_d = cse.ticker_audio_dir(ticker, quarter)
            for cand in candidates:
                if cand.rstrip("/").lower() == ir.rstrip("/").lower():
                    continue
                print(f"     [generic] audio-only scan on candidate: {cand}")
                try:
                    page.goto(cand, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"       [audio] goto failed: {e}")
                    continue
                audio_arts = _try_extract_audio_from_page(
                    page, ticker, target_date, cand, audio_d,
                    semi_auto=semi_auto,
                )
                if audio_arts:
                    result.artifacts.extend(audio_arts)
                    break
        return result
    print(f"     [generic] IR-home had no direct artifacts; walking candidates")

    # Main candidate walk: try each candidate until one yields at least one PDF.
    # Two passes per candidate:
    #   (a) Direct-extract on the candidate URL itself. Listings can expose PDFs
    #       right on the listing page (COST's events-and-presentations shows
    #       "PRESENTATION → Q2-FY-26-Earnings-Supplement.pdf" inline with the
    #       Q2 row; the Q3 placeholder-sub-event has nothing). Try this first.
    #   (b) If direct extraction failed and the candidate is a listing (not
    #       already an event URL), drill into the first earnings-keyword sub-
    #       event link and extract from that page. Original behavior.
    # Candidate walk: instead of returning on the first candidate with PDFs,
    # accumulate artifacts and keep walking until we have both PDFs and audio.
    # Many IR sites (CLX, MKC) show PDFs on a press-releases candidate page and
    # the webcast link on the events-and-presentations candidate page — earlier
    # return-on-first-PDF logic skipped the latter.
    attempted = 0
    pdf_found = False
    audio_d = cse.ticker_audio_dir(ticker, quarter)

    def _have_audio() -> bool:
        return any(a.kind == "audio" for a in result.artifacts)

    for cand in candidates:
        if cand.rstrip("/").lower() == ir.rstrip("/").lower():
            continue  # already handled by the IR-home fast-path
        if _is_webcast_portal(cand):
            continue

        attempted += 1

        # Pass (a): direct extraction on the candidate. Skip the full PDF+audio
        # extractor if we already have PDFs — an audio-only scan is cheaper.
        if not pdf_found:
            print(f"     [generic] try candidate direct: {cand}")
            new_arts = _try_extract_from_event_url(cand)
            if new_arts:
                result.artifacts.extend(new_arts)
                pdf_found = any(a.kind != "audio" for a in new_arts) or pdf_found
                if not result.note:
                    result.note = "via generic_backend (candidate direct)"
        elif not _have_audio():
            print(f"     [generic] candidate audio-only scan: {cand}")
            try:
                page.goto(cand, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"       [audio] goto failed: {e}")
                continue
            audio_arts = _try_extract_audio_from_page(
                page, ticker, target_date, cand, audio_d, semi_auto=semi_auto,
            )
            if audio_arts:
                result.artifacts.extend(audio_arts)

        # Pass (b): if the candidate URL isn't already an event, drill into the
        # first earnings-keyword sub-event link on the listing. Skip when we
        # already have PDFs — the direct-pass on the listing already did the
        # drill internally via _try_extract_audio_from_page.
        if _url_is_earnings_event(cand) or pdf_found:
            if pdf_found and _have_audio():
                return result
            continue
        sub_event_url = _find_earnings_event_link(page, cand)
        if sub_event_url and sub_event_url != cand:
            print(f"     [generic] try candidate->sub-event: {sub_event_url}")
            new_arts = _try_extract_from_event_url(sub_event_url)
            if new_arts:
                result.artifacts.extend(new_arts)
                pdf_found = any(a.kind != "audio" for a in new_arts) or pdf_found
                if not result.note:
                    result.note = "via generic_backend (sub-event)"
                if pdf_found and _have_audio():
                    return result
            else:
                print(f"     [generic] no artifacts from sub-event {sub_event_url[:80]}")

    if result.artifacts:
        # We got some PDFs but audio might be missing — return what we have.
        return result

    # PDF walk exhausted with no wins. Last resort: audio-only sweep across
    # candidates. Some IR sites (CAG, SYY) bury the webcast link on an events-
    # calendar page that doesn't host any classifiable PDFs.
    for cand in candidates:
        if cand.rstrip("/").lower() == (ir or "").rstrip("/").lower():
            continue
        print(f"     [generic] no-PDF audio-only scan: {cand}")
        try:
            page.goto(cand, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1500)
        except Exception as e:
            print(f"       [audio] goto failed: {e}")
            continue
        audio_arts = _try_extract_audio_from_page(
            page, ticker, target_date, cand, audio_d,
            semi_auto=semi_auto,
        )
        if audio_arts:
            result.artifacts.extend(audio_arts)
            result.note = "via generic_backend (audio-only fallback)"
            return result

    if attempted == 0:
        result.errors.append(
            f"no earnings event matching {target_date} on any of {len(candidates)} candidate pages"
        )
    else:
        result.errors.append(
            f"tried {attempted} candidate URL(s); none yielded classifiable PDFs"
        )
    return result


# --- Webcast-URL survey -----------------------------------------------------
# One-time / on-demand survey: walks each ticker's IR the same way generic_backend
# does, but instead of downloading PDFs it harvests every webcast-vendor URL it
# finds. Output is a markdown report bucketed by vendor — the catalog that
# drives which per-vendor audio modules we build next.
#
# Independent of build_gap_list: iterates ALL tickers in cse.TICKERS regardless
# of whether they already have a transcript on disk. Audio is a separate gap
# dimension and the survey has to cover the whole watchlist to be useful.

WEBCAST_SURVEY_PATH = Path(r"C:\Users\rodin\Desktop\Brain\Knowledge\IR Webcast Vendor Survey.md")


@dataclass
class WebcastHit:
    vendor: str                # e.g. "mediasite", "q4_inc_attendee", "(unknown)"
    url: str                   # the webcast/replay URL
    text: str                  # link text as rendered on the page
    found_on: str              # the page we discovered the link on


def _collect_webcast_hits_on_page(page: Page, page_url: str) -> list[WebcastHit]:
    """Scan all <a> elements on the current page, classify each href against
    WEBCAST_VENDOR_PATTERNS + keyword hints, return the deduplicated hits."""
    try:
        links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({text: (e.innerText || '').trim(), href: e.href}))",
        )
    except Exception:
        return []
    seen: set[str] = set()
    hits: list[WebcastHit] = []
    for l in links:
        href = l["href"] or ""
        text = l["text"] or ""
        vendor = classify_webcast_url(href, text)
        if not vendor:
            continue
        if href in seen:
            continue
        seen.add(href)
        hits.append(WebcastHit(vendor=vendor, url=href, text=text[:120], found_on=page_url))
    return hits


# Candidate URL patterns that never host webcast links and are known-slow
# (heavy PDFs, JS-heavy annual-report portals). Skipping them avoids survey
# hangs on pages like kimberly-clark.com/en-us/investors/annual-reports where
# Playwright's goto can block past its own timeout.
_SURVEY_BLOCKED_CANDIDATE_PATTERNS = (
    "annual-report", "annual_report", "annualreport",
    "/10-k", "/10k/", "/proxy-statement",
    "/governance", "/sustainability", "/esg/",
    "/careers", "/media-resources", "/downloads-archive",
)


def _is_survey_blocked_candidate(url: str) -> bool:
    u = (url or "").lower()
    return any(pat in u for pat in _SURVEY_BLOCKED_CANDIDATE_PATTERNS)


def survey_webcast_urls_for_ticker(ticker: str, ir_url: str, page: Page,
                                    max_candidates: int = 3) -> list[WebcastHit]:
    """Walk one ticker's IR looking for webcast URLs. Reuses generic_backend's
    IR-resolution and candidate-ranking helpers to match its traversal exactly
    — any link generic_backend would reach during PDF scraping is reachable
    here, plus the sub-event page drilled into under each listing candidate."""
    hits: list[WebcastHit] = []

    start = _resolve_ir_starting_point(ticker, ir_url)
    if not start:
        print(f"     [survey] no IR starting point for {ticker}")
        return hits
    print(f"     [survey] start={start}")

    # Resolve an IR page (same 3-pass strategy as generic_backend).
    start_lower = start.lower()
    if any(k in start_lower for k in ("investor", "/ir/", "ir.", "investors.", "stock.")):
        ir = start
    else:
        ir = _try_common_ir_patterns(start) or _find_ir_page(page, start)
    if not ir:
        print(f"     [survey] could not resolve IR page for {ticker}")
        return hits
    print(f"     [survey] IR: {ir}")

    # Tighten timeouts for survey mode — we'd rather skip a slow page than
    # hang the whole sweep (KMB's annual-reports page stalled a 30s goto and
    # blocked the run for >6 min in the first attempt).
    page.set_default_navigation_timeout(15000)
    page.set_default_timeout(15000)

    # Visit IR home and collect webcast links + candidate sub-pages.
    try:
        page.goto(ir, wait_until="domcontentloaded", timeout=15000)
        time.sleep(1)
    except Exception as e:
        print(f"     [survey] IR goto failed: {e}")
    hits.extend(_collect_webcast_hits_on_page(page, ir))

    candidates = _ranked_candidates(page, _EVENTS_KEYWORDS_TEXT, _EVENTS_KEYWORDS_URL, limit=max_candidates)
    if not candidates:
        print(f"     [survey] no nav candidates on IR home")

    # Visit each candidate + attempt to drill into the first earnings sub-event
    # (webcast links most often appear on the event-detail page, not the listing).
    visited: set[str] = {ir.rstrip("/").lower()}
    for cand in candidates:
        key = cand.rstrip("/").lower()
        if key in visited:
            continue
        visited.add(key)
        if _is_survey_blocked_candidate(cand):
            print(f"     [survey] candidate skipped (blocked pattern): {cand}")
            continue
        print(f"     [survey] candidate: {cand}")
        try:
            page.goto(cand, wait_until="domcontentloaded", timeout=15000)
            time.sleep(1)
        except Exception as e:
            print(f"     [survey] candidate goto failed: {e}")
            continue
        hits.extend(_collect_webcast_hits_on_page(page, cand))

        # Drill into the first earnings sub-event on this candidate (only if
        # it's a listing — if the candidate itself is an event URL, skip).
        if not any(k in cand.lower() for k in (
            "-q1-", "-q2-", "-q3-", "-q4-", "first-quarter", "second-quarter",
            "third-quarter", "fourth-quarter", "earnings-release", "-earnings-",
        )):
            # _find_earnings_event_link does its own page.goto + page.evaluate
            # (scroll). Guard the whole call so a hang in that helper can't
            # freeze the survey.
            try:
                sub = _find_earnings_event_link(page, cand)
            except Exception as e:
                print(f"     [survey]   find sub-event failed: {e}")
                sub = None
            if sub and sub.rstrip("/").lower() not in visited:
                visited.add(sub.rstrip("/").lower())
                print(f"     [survey]   sub-event: {sub}")
                try:
                    page.goto(sub, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(1)
                    hits.extend(_collect_webcast_hits_on_page(page, sub))
                except Exception as e:
                    print(f"     [survey]   sub-event goto failed: {e}")

    # Deduplicate across all pages by URL (we may have seen the same link on
    # multiple candidate pages).
    seen_urls: set[str] = set()
    unique: list[WebcastHit] = []
    for h in hits:
        if h.url in seen_urls:
            continue
        seen_urls.add(h.url)
        unique.append(h)
    return unique


def write_webcast_survey_report(results: dict[str, list[WebcastHit]]) -> None:
    """Write the vendor-bucketed survey to WEBCAST_SURVEY_PATH."""
    vendor_to_tickers: dict[str, list[str]] = {}
    no_hits: list[str] = []
    for ticker, hits in results.items():
        if not hits:
            no_hits.append(ticker)
            continue
        for v in {h.vendor for h in hits}:
            vendor_to_tickers.setdefault(v, []).append(ticker)

    lines = [
        "---",
        "type: scraper-report",
        f"generated_on: {datetime.now().date().isoformat()}",
        f"tickers_surveyed: {len(results)}",
        "---",
        "",
        "# IR Webcast Vendor Survey",
        "",
        "Harvested by `survey_webcast_urls` — every webcast/replay URL found on each ticker's IR home, candidate events page, and first earnings sub-event. Use this as the catalog driving per-vendor audio-extraction modules.",
        "",
        "## Summary by vendor",
        "",
        "| Vendor | Ticker count | Tickers |",
        "| ------ | ------------ | ------- |",
    ]
    for v in sorted(vendor_to_tickers, key=lambda x: (-len(vendor_to_tickers[x]), x)):
        ts = sorted(vendor_to_tickers[v])
        lines.append(f"| `{v}` | {len(ts)} | {', '.join(ts)} |")
    if no_hits:
        lines.append(f"| *(no webcast found)* | {len(no_hits)} | {', '.join(sorted(no_hits))} |")
    lines.append("")

    lines.append("## Per-ticker hits")
    lines.append("")
    for ticker in sorted(results):
        lines.append(f"### {ticker}")
        hits = results[ticker]
        if not hits:
            lines.append("- *(no webcast URLs found)*")
            lines.append("")
            continue
        for h in hits:
            text = (h.text or "—").replace("|", "\\|")
            lines.append(f"- **`{h.vendor}`** — {h.url}")
            lines.append(f"  - text: {text}")
            lines.append(f"  - found on: {h.found_on}")
        lines.append("")

    WEBCAST_SURVEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEBCAST_SURVEY_PATH.write_text("\n".join(lines), encoding="utf-8")


def run_webcast_survey(tickers_filter: set[str] | None, semi_auto: bool = False) -> int:
    """Entry point for `python scrape.py --survey-webcasts`. Spins up a stealth
    Playwright browser, iterates tickers, writes the markdown report."""
    tickers = cse.TICKERS if not tickers_filter else {
        t: cse.TICKERS[t] for t in tickers_filter if t in cse.TICKERS
    }
    print(f"[survey] surveying {len(tickers)} ticker(s)")
    results: dict[str, list[WebcastHit]] = {}
    stealth = Stealth()
    with stealth.use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=not semi_auto)
        ctx = browser.new_context(user_agent=USER_AGENT)
        for ticker in tickers:
            ir_url = cse.IR_URLS.get(ticker, "")
            print(f"\n   [{ticker}]")
            page = ctx.new_page()
            try:
                hits = survey_webcast_urls_for_ticker(ticker, ir_url, page)
            except Exception as e:
                print(f"     [survey] raised: {e}")
                hits = []
            finally:
                page.close()
            results[ticker] = hits
            if hits:
                vendors = sorted({h.vendor for h in hits})
                print(f"     → {len(hits)} hit(s); vendors: {vendors}")
            else:
                print(f"     → no webcast URLs found")
        browser.close()

    write_webcast_survey_report(results)
    print(f"\nSurvey written to: {WEBCAST_SURVEY_PATH}")
    hit_tickers = sum(1 for h in results.values() if h)
    print(f"Coverage: {hit_tickers}/{len(results)} tickers had ≥1 webcast URL.")
    return 0


# --- Gap detection ----------------------------------------------------------

def build_gap_list(tickers_filter: set[str] | None) -> list[dict]:
    gaps = []
    tickers_iter = cse.TICKERS if not tickers_filter else {t: cse.TICKERS[t] for t in tickers_filter if t in cse.TICKERS}
    for ticker in tickers_iter:
        cse.ensure_ticker_folders(ticker)
        dates = cse.fetch_earnings_dates(ticker)
        last_date = dates.get("last_date")
        if not last_date:
            continue
        has_audio = cse.has_source(ticker, last_date, cse.AUDIO_EXTS, "audio")
        has_transcript = cse.has_source(ticker, last_date, cse.TRANSCRIPT_EXTS, "transcripts")
        # Skip only when BOTH sides are covered. The generic backend now also
        # handles `direct_audio` + `youtube_live` inline, so tickers with a
        # transcript but no audio are still worth re-running — generic_backend
        # may pick the audio up on the same walk it already uses for PDFs.
        if has_transcript and has_audio:
            continue
        gaps.append({
            "ticker": ticker,
            "last_date": last_date,
            "has_audio": has_audio,
            "has_transcript": has_transcript,
            "ir_url": cse.IR_URLS.get(ticker, ""),
        })
    return gaps


# --- Transcription chain ----------------------------------------------------

def trigger_transcription(audio_path: Path, ticker: str, date: str) -> tuple[bool, str]:
    if not TRANSCRIBE_SCRIPT.exists():
        return False, f"transcribe script not found at {TRANSCRIBE_SCRIPT}"
    cmd = [sys.executable, str(TRANSCRIBE_SCRIPT),
           "--audio", str(audio_path), "--ticker", ticker, "--date", date]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if r.returncode == 0:
            return True, (r.stdout or "")[-400:]
        return False, (r.stderr or r.stdout or "")[-400:]
    except Exception as e:
        return False, f"transcription invocation failed: {e}"


# --- Gap report -------------------------------------------------------------

def write_gap_report(results: list[ScrapeResult], gaps: list[dict]) -> None:
    url_lookup = {g["ticker"]: g["ir_url"] for g in gaps}
    lines = [
        "---",
        "type: scraper-report",
        f"generated_on: {datetime.now().date().isoformat()}",
        "---",
        "",
        "# IR Scraper Gap Report",
        "",
    ]
    remaining = []
    for r in results:
        kinds = {a.kind for a in r.artifacts}
        got_audio = "audio" in kinds
        got_any_pdf = "press_release" in kinds or "presentation" in kinds
        if r.note or r.errors or not got_audio or not got_any_pdf:
            remaining.append((r, got_audio, got_any_pdf))

    if not remaining:
        lines.append("_No gaps remaining — every ticker scraped successfully._")
    else:
        lines.extend([
            "| Ticker | Last Earnings | Got Audio | Got PDFs | Note | IR Page |",
            "| ------ | ------------- | --------- | -------- | ---- | ------- |",
        ])
        for r, got_audio, got_pdf in remaining:
            note = r.note or ("; ".join(r.errors)[:120] if r.errors else "—")
            ir_url = url_lookup.get(r.ticker, "")
            ir_link = f"[Link]({ir_url})" if ir_url else "—"
            lines.append(
                f"| {r.ticker} | {r.event_date or '—'} | {'✅' if got_audio else '❌'} | {'✅' if got_pdf else '❌'} | {note} | {ir_link} |"
            )

    lines.append("")
    GAP_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    GAP_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


# --- Orchestrator -----------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", help="Comma-separated ticker subset")
    parser.add_argument("--no-transcribe", action="store_true", help="Skip audio-transcription chain")
    parser.add_argument("--dry-run", action="store_true", help="Report gaps, don't scrape")
    parser.add_argument("--semi-auto", action="store_true",
                        help="Headed browser; pause for manual CAPTCHA/submit when form gating blocks us")
    parser.add_argument("--survey-webcasts", action="store_true",
                        help="Harvest webcast URLs on each ticker's IR; write vendor-bucketed report. Skips PDF scrape.")
    args = parser.parse_args()
    tickers_filter = set(t.strip().upper() for t in args.tickers.split(",")) if args.tickers else None

    if args.survey_webcasts:
        return run_webcast_survey(tickers_filter, semi_auto=args.semi_auto)

    print("[1/4] Building gap list...")
    gaps = build_gap_list(tickers_filter)
    print(f"   {len(gaps)} ticker(s) with gaps.")
    for g in gaps:
        ir_flag = "✓" if g["ir_url"] else "(empty)"
        print(f"     {g['ticker']:<5}  last={g['last_date']}  audio={g['has_audio']}  "
              f"transcript={g['has_transcript']}  ir={ir_flag}")

    if args.dry_run:
        print("\n--dry-run: stopping before scraping.")
        write_gap_report([ScrapeResult(g["ticker"], g["last_date"], note="dry-run") for g in gaps], gaps)
        return 0

    print("\n[2/4] Scraping...")
    results: list[ScrapeResult] = []
    # `Stealth.use_sync` wraps sync_playwright() so every page created under
    # the browser context gets the stealth init-scripts injected at construction
    # time. Bypasses Cloudflare's passive bot-fingerprinting (COST), and makes
    # reCAPTCHA score-based challenges less likely to trigger — though visible
    # checkbox CAPTCHAs (PM's Mediasite) still need --semi-auto or a solver.
    stealth = Stealth()
    with stealth.use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=not args.semi_auto)
        ctx = browser.new_context(user_agent=USER_AGENT)
        # Cap every page-level operation at 30s. Without this, MNST's IR SPA
        # can hang page.eval_on_selector_all / page.url access indefinitely,
        # locking the whole batch on one ticker. Survey mode already does this;
        # the main scrape path was missing it.
        ctx.set_default_timeout(30000)
        ctx.set_default_navigation_timeout(30000)
        for g in gaps:
            ticker, ir_url, target_date = g["ticker"], g["ir_url"], g["last_date"]
            print(f"\n   [{ticker}] target={target_date}")
            page = ctx.new_page()
            try:
                r = generic_backend(ticker, ir_url, target_date, page, semi_auto=args.semi_auto)
            except Exception as e:
                r = ScrapeResult(ticker, target_date, errors=[f"backend raised: {e}"])
            finally:
                page.close()
            for a in r.artifacts:
                print(f"     ✓ {a.kind}: {a.path.name}")
            for err in r.errors:
                print(f"     ✗ {err}")
            results.append(r)
        browser.close()

    if not args.no_transcribe:
        print("\n[3/4] Transcribing new audio files...")
        for r in results:
            for a in r.artifacts:
                if a.kind != "audio":
                    continue
                print(f"   transcribing {a.path.name}...")
                ok, log = trigger_transcription(a.path, r.ticker, r.event_date)
                print(f"     {'✓' if ok else '✗'} {log[:200]}")
    else:
        print("\n[3/4] Skipping transcription (--no-transcribe).")

    write_gap_report(results, gaps)
    total_artifacts = sum(len(r.artifacts) for r in results)
    total_errors = sum(len(r.errors) for r in results)
    print(f"\nSummary: {total_artifacts} artifact(s), {total_errors} error(s), {len(results)} ticker(s) attempted.")
    print(f"Gap report: {GAP_REPORT_PATH}")

    # Regenerate the Consumer Staples Earnings Calendar so ✅/❌ cells reflect
    # everything just downloaded. Skipped when nothing changed on disk.
    if total_artifacts > 0:
        print("\n[4/4] Refreshing Consumer Staples Earnings Calendar...")
        try:
            cse.main()
        except Exception as e:
            print(f"   ✗ calendar refresh failed: {e}")
    else:
        print("\n[4/4] No new artifacts — skipping calendar refresh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
