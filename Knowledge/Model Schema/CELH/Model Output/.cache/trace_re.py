import re

# The actual CLUTTER_RE
CLUTTER_RE = re.compile(
    r"(?:[,;]\s*)?\$?[\d.,]*\s*"
    r"(?:par\s+value|cumulative\s+dividends|liquidation\s+preference|aggregate\s+liquidation"
    r"|[\d,]+\s+shares\s+\w+)"
    r".*$",
    re.IGNORECASE | re.DOTALL,
)

for s in [
    'Mezzanine equity, shares outstanding (in shares)',
    'Mezzanine equity, par value (in USD per share)',
]:
    m = CLUTTER_RE.search(s)
    if m:
        print(f"INPUT  : {s!r}")
        print(f"  match: span={m.span()}, group={m.group()!r}")
    else:
        print(f"NO MATCH: {s!r}")

# What's the alternative that's matching for "shares outstanding (in shares)"?
# Let's strip the optional prefix and try just the alternatives
ALT_RE = re.compile(
    r"(par\s+value|cumulative\s+dividends|liquidation\s+preference|aggregate\s+liquidation"
    r"|[\d,]+\s+shares\s+\w+)",
    re.IGNORECASE,
)
print()
for s in [
    'shares outstanding (in shares)',
    '1,000 shares outstanding',
    'in shares',
]:
    m = ALT_RE.search(s)
    print(f"alt match {s!r}: {m.group() if m else 'NONE'!r}")
