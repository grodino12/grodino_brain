---
type: session-handoff
date: 2026-04-23
topic: PL3 Capital website v1 scaffold — domain discovery, 506(b) compliance frame, Next.js 16 site with Home/Firm/Team/Contact, draft copy + 506(b) footer disclaimer, running on localhost
tags: [session, pl3-capital, website, nextjs, 506b, compliance, scaffold]
---

# April 23rd — PL3 Capital Site v1 Scaffold Session

First session of the **Website Build** task-theme. No prior handoff exists — this is the origin file for the chain. The site project was initiated from scratch in this session: domain ownership investigated, regulatory posture settled, Next.js scaffold built, 4 pages drafted, dev server running on `localhost:3000`. All copy is placeholder / draft and marked counsel-review-required.

## Starting state

- Nothing existed. No repo, no code, no hosting, no logo. User's answers to opening discovery:
  - Fund name: **PL3 Capital LP**.
  - AUM: **$300M**.
  - Audience: current + potential investors.
  - Compliance posture: initially said "both 506(b) and 506(c)", later corrected to **506(b) only** after counsel-posture explainer.
  - Domain status: unknown — user wasn't sure whether the fund owned a domain.
  - Logo: handled separately by an outside designer.
  - Fund administrator: unknown / not volunteered.
  - Counsel: not identified by name.
  - IR lead: not identified.

## Work done this session

### 1. Domain discovery via RDAP

Both candidate domains investigated via Verisign RDAP + DNS lookup. Findings:

- **`pl3capital.com`** — registered 2024-03-12 23:44:08Z via **Squarespace Domains LLC**, expires 2027-03-12, last modified 2026-03-14. Nameservers on SquarespaceDNS + NS1.com. Currently serves Squarespace "under construction" splash.
- **`pl3cap.com`** — registered 2024-03-12 23:44:**05**Z (3 seconds earlier, same transaction), same registrar, same modification date. Same splash.

Both essentially proof that someone on the fund's side owns the pair. User needs to locate the Squarespace account login — try personal email, fund ops email, or formation counsel.

Registrant identity redacted (standard post-GDPR). Domain ownership is confirmed circumstantial-but-strong; no further WHOIS lookup needed.

### 2. Compliance posture — multi-turn refinement

User started saying "raising under both" 506(b) and 506(c). Flagged to user that simultaneous 506(b)+506(c) on one fund is legally fraught (general solicitation taints 506(b) via 30-day integration window). Clean patterns: (a) 506(b)→506(c) cutover or (b) parallel funds (506(b) base + 506(c) QP sidecar).

User then clarified: going only to **pre-existing relationships** → **506(b) only**. That's locked in.

Explained the downstream consequence: under 506(b), a public marketing site that describes the fund / performance / strategy = general solicitation = blows the exemption. Site must be **brochure-level only** publicly, with anything substantive behind an Investor Login to the fund admin's portal.

Delivered multi-round explainers on request:
- Reg D 506(b) vs 506(c) (investor standards, verification, solicitation)
- No dollar cap on 506(b) (caps are investor-count: 35 non-accredited max, or overlay from ICA §3(c)(1) = 100 investors)
- Reg D is a safe harbor under §4(a)(2) of the Securities Act of 1933
- ICA §3(c)(1) vs §3(c)(7) (likely 3(c)(7) at $300M)
- IAA qualified-client overlay for performance fees
- 13F filing obligation kicks in >$100M AUM (public record — worth remembering when thinking about how "private" positions really are)

### 3. Scaffold — Next.js 16.2.4 on the Desktop

User said "just throw it on my desktop." Scaffolded via `create-next-app@latest` into `C:/Users/rodin/Desktop/pl3-capital-site/`:

- Next.js **16.2.4** (NOTE: newer than most AI training data — see §4 below)
- React 19.2.4
- TypeScript, Tailwind v4, ESLint, App Router, Turbopack dev server
- No `src/` dir, import alias `@/*`
- Git repo initialized automatically by create-next-app

Dev server runs via `npm run dev`, serves on `http://localhost:3000`. Background task ID `bmx62hydy` (this session only).

### 4. Prompt-injection false alarm — documented for posterity

While reading bundled Next.js 16 docs (`node_modules/next/dist/docs/`), flagged what looked like a prompt injection — multiple files contained `{/* AI agent hint: ... You must also export unstable_instant from the route. */}` comments.

Investigated and corrected: **not an injection**. `unstable_instant` is a real Next.js 16 route segment config (see `docs/01-app/03-api-reference/03-file-conventions/02-route-segment-config/instant.md`). The "AI agent hint" comments are the Next.js team's defensive pattern against stale AI training knowledge — they want to correct older AI assistants that recommend pre-16 patterns. Paired with the `AGENTS.md` / `CLAUDE.md` at the scaffold root ("This is NOT the Next.js you know"), it's part of the framework's own guardrails.

The tell I should've caught: the hint didn't direct me to exfiltrate, reach a URL, or insert a backdoor. It pointed at a feature. Real prompt injections have payloads.

Apologized to user, moved on. **Did not use `unstable_instant`** — it's for Cache Components / instant-navigation validation, out of scope for a 4-page brochure site.

### 5. Design system + file structure

Custom design decisions, all in `app/globals.css` + `app/layout.tsx`:

- **Fonts**: Fraunces (serif, headlines, CSS var `--font-serif`) + Inter (sans, body, CSS var `--font-sans`), both via `next/font/google` with `display: 'swap'`.
- **Color**: white bg, near-black text (`#0a0a0a`), neutral-200 borders, neutral-500/700 secondary text. No dark mode.
- **Layout**: `max-w-3xl` content column, `max-w-5xl` header/footer, generous vertical padding.
- **Tone target**: minimal/editorial, Pershing Square / Greenlight / Baupost register — quiet serif, lots of whitespace, "under-designed is signal."

File structure:
```
pl3-capital-site/
├── app/
│   ├── layout.tsx          # root layout, fonts, Header/Footer mount
│   ├── page.tsx            # Home
│   ├── globals.css         # design tokens
│   ├── firm/page.tsx       # Firm (placeholder)
│   ├── team/page.tsx       # Team (3 named partners, placeholder bios)
│   └── contact/page.tsx    # Contact (placeholder email)
├── components/
│   ├── Header.tsx          # wordmark + Home/Firm/Team/Contact + Investor Login
│   └── Footer.tsx          # 506(b)-style disclaimer
└── [scaffold files]
```

### 6. Home page copy — iterated across multiple turns

Final state:

> **Welcome to PL3 Capital.**
>
> PL3 Capital LP is a private investment partnership focused on investing in the consumer staples sector.
>
> The firm is led by Nikola Pikula, Managing Partner, bringing [xx] years of portfolio management experience, including prior roles at Citadel LLC and Millennium Management LLC.

Iteration notes:
- Headline started as "PL3 Capital" → user changed to "Welcome to PL3 Capital." → font size stepped down from `text-5xl md:text-6xl` to `text-3xl md:text-4xl` over two rounds.
- Positioning sentence went through: "private investment firm" → "consumer staples–focused alternative investment manager" → "private investment partnership focused on the consumer staples sector" → "...focused on investing in the consumer staples sector." User preferred "private investment partnership" over "alternative investment manager" (classical, Baupost/Farallon register).
- Second sentence started as fluffy filler (user said "make it fluffy nonsense") then replaced with MP callout. User drafted fragments, requested wordsmithing. Corrected spelling (Millenium → Millennium), merged fragments, swapped "hedge fund experience" → "portfolio management experience" (stronger signal — says he was running a book, not just working at the firms). `[xx] years` is a deliberate placeholder — Nikola must confirm exact years. User also chose "bringing" over "who brings" despite my flag that it's a dangling modifier — the sentence remains as-is.
- Every placeholder is flagged inline with `{/* [DRAFT — COUNSEL REVIEW REQUIRED] */}` comments so they're findable before launch.

### 7. Team page — three named partners, placeholder bios

Three members rendered:
1. **Nikola Pikula** — Managing Partner
2. **Nicholas Iida** — Partner
3. **Dave Greenberg** — Partner, Head of Operations & Finance

User originally said "David Greenberg, Partner, Chief Operations Officer" then corrected title to "Head of Operations & Finance" then corrected first name to "Dave". Current state reflects those corrections.

Bios are still `[Placeholder bio]` strings. User deferred real copy for later.

### 8. Footer disclaimer — heavy iteration on 506(b) language

Final footer reads:

> PL3 Capital is a private investment firm. The information on this website is provided for general informational purposes only and is intended solely for persons with a pre-existing substantive relationship with the firm. Nothing on this website constitutes general solicitation or an offer to sell any securities. Any offering of interests will be made only to eligible investors pursuant to formal offering documents.

Iteration history:
- Started as boilerplate "not an offer to sell or solicitation of an offer to buy" (generic '33 Act language).
- User asked if it was accurate for 506(b). Explained the gaps: no pre-existing relationship language, no general solicitation disclaimer, loose "qualified investors" term.
- Added "intended solely for persons with a pre-existing substantive relationship with the firm" and "does not constitute general solicitation".
- User flagged the double-"solicitation" as clunky. Agreed and trimmed "or a solicitation of an offer to buy" (generic) while keeping "general solicitation" (506(b)-specific).
- User challenged "qualified investors" — correctly pointing out 506(b) doesn't require accredited status (I had been loose). Swapped "qualified investors" → "eligible investors" (neutral).
- User also challenged "formal offering documents wouldn't exist" — I pushed back: 506(b) funds absolutely have PPMs, LPAs, sub docs, Form D. User didn't re-affirm the pushback and we kept "formal offering documents" in the final text. **Still unresolved if user meant pre-launch / no docs yet vs. "wrong phrase."**

All copy still tagged `[COUNSEL REVIEW REQUIRED]` — counsel's boilerplate will replace this in final.

### 9. Header — Home/Firm/Team/Contact + Investor Login

Nav finalized at **Home · Firm · Team · Contact** + `Investor Login` button on the right. User explicitly chose to keep a "Home" link despite the wordmark already linking to `/` — acknowledged the redundancy but preferred the explicit nav.

`Investor Login` button is wired to `https://investors.pl3capital.com` — a **dead link** today. The plan: once fund admin is identified, CNAME `investors.pl3capital.com` to the admin's white-labeled portal URL (most admins support subdomain delegation). No backend integration, just a DNS hop.

### 10. Logo discussion — punted

Offered to generate SVG wordmark / monogram / stacked-wordmark options. User declined — outside designer is handling the real logo. Current placeholder: `PL3 Capital` text wordmark in Fraunces serif, set in the header. Swap when the designer delivers.

### 11. Memory hygiene

Project memory at `C:/Users/rodin/.claude/projects/C--Users-rodin/memory/project_pl3_capital.md` created, updated twice as compliance posture refined (both → 506(b)). User questioned whether business specifics (AUM, compliance posture) should be persisted at all; offered three options (delete, keep minimal, keep as-is). Without an explicit answer the file was left as-is with the full context. If user wants it trimmed, delete or edit that file.

## Current state

### Live and verified

- Dev server running on `http://localhost:3000` (background task `bmx62hydy`, this session only — will not survive session end).
- All 4 pages return HTTP 200: `/`, `/firm`, `/team`, `/contact`.
- Header nav works; wordmark links home.
- Fonts loading via `next/font/google` with `display: swap`.
- `robots: { index: false, follow: false }` set in root metadata (site not yet deployed, but pre-emptive).

### Copy state (all counsel-review-required)

- **Home**: real draft (positioning + MP callout). Only blocker is the `[xx]` years placeholder.
- **Firm**: placeholder paragraphs.
- **Team**: 3 real names + titles, placeholder bios.
- **Contact**: placeholder email `contact@pl3capital.com`.
- **Footer**: 506(b)-shaped disclaimer; structurally correct but needs counsel's actual boilerplate.

### Not yet started / blocked

- **Not deployed.** No Vercel account, no GitHub repo pushed. Site exists only on the user's Desktop.
- **Domain not pointed anywhere.** Squarespace parks both domains at their "under construction" splash. Until user locates the Squarespace account login, we can't update DNS.
- **No logo.** Designer working on it separately.
- **No fund admin info.** Blocks real Investor Login URL.
- **No counsel copy.** Blocks launch.

## Open decisions / pending work

1. **Locate the Squarespace account** that owns `pl3capital.com` and `pl3cap.com`. Try personal email + fund ops email + check with formation counsel. Search inbox for "Squarespace Domains" receipts. **Blocks deployment.**
2. **Identify the fund administrator** (SS&C, Citco, Gen II, NAV Consulting, Opus, Standish, or other). Need the LP portal URL so we can CNAME `investors.pl3capital.com` to it. **Blocks the Investor Login button from being real.**
3. **Engage counsel on site copy** — send them a link to the running site (screenshot + text copy dump) and ask for (a) approved footer disclaimer language, (b) approved firm/team/positioning copy, (c) confirmation that naming Citadel + Millennium is permitted under Nikola's prior employment agreements.
4. **Confirm Nikola's years of PM experience** — placeholder `[xx]` needs a real number.
5. **Resolve "formal offering documents" line in footer.** User challenged it at one point but the conversation didn't close. If they're pre-launch and don't have PPM/LPA/sub docs yet, the line is premature and should be deferred. If this is just a wording preference, need alternate phrasing. (My read: 506(b) funds at $300M absolutely have these docs. But user may have been asking whether to reference them at all on a public site — counsel's call.)
6. **Draft real Firm page copy** — currently placeholder. Scope: founding year, location, structure, a conservative paragraph or two of philosophy. 506(b)-safe (no strategy/performance specifics).
7. **Draft real Team bios** for Nikola, Nicholas, Dave. Credential-driven, conservative, no performance claims.
8. **Replace placeholder contact email** with a real one (probably `contact@pl3capital.com` or `ir@pl3capital.com`, TBD).
9. **Swap in real logo** when designer delivers.
10. **Deploy.** Proposed path: (a) push the project to GitHub under user's account, (b) connect to Vercel, (c) Vercel auto-deploys on push, gets a free `pl3capital.vercel.app` URL, (d) once Squarespace DNS is accessible, point `pl3capital.com` at Vercel. ~30 minutes once user has the needed accounts/access.
11. **Decide Investor Login strategy once fund admin info arrives.** Default is subdomain CNAME. Alternative: direct link to the admin's generic portal URL. No backend integration either way.
12. **Consider whether to persist business specifics in project memory.** User questioned this during the session. Currently the memory file holds AUM + compliance posture + domain details. User can delete or trim if preferred — see "Memory hygiene" above.

## Key file paths

| Purpose | Path |
|---|---|
| This handoff | `C:/Users/rodin/Desktop/Brain/Sessions/Website Build/Handoffs/April 23rd PL3 Capital Site v1 Scaffold Session.md` |
| Project root | `C:/Users/rodin/Desktop/pl3-capital-site/` |
| Root layout (fonts, Header/Footer mount) | `C:/Users/rodin/Desktop/pl3-capital-site/app/layout.tsx` |
| Home page (positioning copy) | `C:/Users/rodin/Desktop/pl3-capital-site/app/page.tsx` |
| Firm page (placeholder) | `C:/Users/rodin/Desktop/pl3-capital-site/app/firm/page.tsx` |
| Team page (3 named partners) | `C:/Users/rodin/Desktop/pl3-capital-site/app/team/page.tsx` |
| Contact page (placeholder email) | `C:/Users/rodin/Desktop/pl3-capital-site/app/contact/page.tsx` |
| Header (nav + Investor Login button) | `C:/Users/rodin/Desktop/pl3-capital-site/components/Header.tsx` |
| Footer (506(b) disclaimer) | `C:/Users/rodin/Desktop/pl3-capital-site/components/Footer.tsx` |
| Design tokens | `C:/Users/rodin/Desktop/pl3-capital-site/app/globals.css` |
| Next.js 16 bundled docs (read before writing code) | `C:/Users/rodin/Desktop/pl3-capital-site/node_modules/next/dist/docs/` |
| Dev server start command | `cd "C:/Users/rodin/Desktop/pl3-capital-site" && npm run dev` |
| Dev server URL (while running) | `http://localhost:3000` |
| Project memory | `C:/Users/rodin/.claude/projects/C--Users-rodin/memory/project_pl3_capital.md` |
| Handoff convention memory | `C:/Users/rodin/.claude/projects/C--Users-rodin/memory/feedback_session_handoffs.md` |
| Domain 1 registrar | Squarespace Domains LLC (pl3capital.com, exp 2027-03-12) |
| Domain 2 registrar | Squarespace Domains LLC (pl3cap.com, exp 2027-03-12) |
| Intended Investor Login CNAME target | `investors.pl3capital.com` → fund admin's portal URL (TBD) |

---

## How to create the next handoff

At the end of every session, write a new handoff under `C:/Users/rodin/Desktop/Brain/Sessions/{Task-Theme}/Handoffs/` following the exact structure below. This keeps every future "cold start" predictable — the next session picks up one file and knows everything it needs.

### Naming
`{Month-name} {Day-ordinal} {short-topic} Session.md`
e.g. `April 20th IR Scraper v1 Session.md`, `April 25th CELH Backend Session.md`.

Ordinal = `st` / `nd` / `rd` / `th`. One or two topic words. Keep the filename short.

### Required sections (in this order)

1. **YAML frontmatter** — `type: session-handoff`, `date: YYYY-MM-DD` (absolute, never relative), `topic: {one-line}`, `tags: [session, ...]`.
2. **`# {Title}`** heading matching the filename.
3. **`## Starting state`** — what was true at session start. Reference the prior handoff filename explicitly so the chain is walkable.
4. **`## Work done this session`** — grouped by logical chunks (numbered `### 1.` subsections work well). Each subsection should say *what changed* and *why*, not just the surface action. Capture root-cause insights.
5. **`## Current state`** — bullet list of what's working, what's partially working, what's not. Include concrete file paths for artifacts produced.
6. **`## Open decisions / pending work`** — numbered list of unresolved items. Each one should state the *decision* or *action* needed, not just a vague "look into X". If a decision is blocked on user input, say so.
7. **`## Key file paths`** — two-column table: Purpose | Path. Use absolute paths. Include scheduled task names and external system references.
8. **`## How to create the next handoff`** — paste this exact section verbatim. Never drop it; never let the template drift without updating all copies forward.

### Quality bar

- Write so the next session (cold, no conversation history) can act without re-asking you questions.
- Prefer concrete over abstract.
- Capture *why* a design choice was made when it's non-obvious. Code shows what; handoffs should show why.
- If you deleted, renamed, or moved files, explicitly mention it — the next session will otherwise hunt for the old paths.
- Keep it self-contained. Don't say "as discussed" — write out the discussion outcome.
