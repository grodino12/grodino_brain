import re

# Without the .*$ at the end
WITHOUT_DOTSTAR = re.compile(
    r"(?:[,;]\s*)?\$?[\d.,]*\s*"
    r"(?:par\s+value|cumulative\s+dividends|liquidation\s+preference|aggregate\s+liquidation"
    r"|[\d,]+\s+shares\s+\w+)",
    re.IGNORECASE,
)
for s in [
    'Mezzanine equity, shares outstanding (in shares)',
    'Mezzanine equity, par value (in USD per share)',
    'Mezzanine equity, redemption amount',
]:
    m = WITHOUT_DOTSTAR.search(s)
    print(f"{s!r}")
    print(f"  match: {m.group() if m else 'NONE'!r}")

# With JUST the keyword alternatives (no prefix, no dotstar)
KW_ONLY = re.compile(
    r"(par\s+value|cumulative\s+dividends|liquidation\s+preference|aggregate\s+liquidation|[\d,]+\s+shares\s+\w+)",
    re.IGNORECASE,
)
print()
for s in [
    ', shares outstanding (in shares)',
    'shares outstanding (in shares)',
    'Mezzanine equity, par value (in USD per share)',
]:
    matches = list(KW_ONLY.finditer(s))
    print(f"{s!r}")
    for m in matches:
        print(f"  kw match span={m.span()}, group={m.group()!r}")
