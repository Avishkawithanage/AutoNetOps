"""Normalization, checksums, line-based diff and heuristic change categories.

Normalization rules (documented because they affect change detection):
  * trailing whitespace is stripped
  * blank lines and '!' comment/separator lines are dropped
  * volatile lines are dropped: 'Building configuration', 'Current configuration : N bytes',
    'Using N out of M bytes', '! Last configuration change at', '! NVRAM config last updated at',
    '! No configuration change since', 'ntp clock-period'
The RAW configuration is always stored unchanged; normalization is only used to decide whether a
new version is needed and (optionally) to produce a quieter diff.

Categories are keyword heuristics on the enclosing top-level block. They are NOT semantic analysis.
"""
import difflib
import hashlib
import re

_VOLATILE = re.compile(
    r"^(building configuration|current configuration\s*:|using \d+ out of|"
    r"! last configuration change|! nvram config last updated|! no configuration change since|"
    r"ntp clock-period)", re.I)

_CATEGORIES = [
    ("Interfaces", re.compile(r"^interface\b", re.I)),
    ("VLANs", re.compile(r"^vlan\b", re.I)),
    ("Routing", re.compile(r"^(router\s|ip route\b|ipv6 route\b|ip routing)", re.I)),
    ("ACLs", re.compile(r"^(ip access-list|access-list|ipv6 access-list)", re.I)),
    ("NAT", re.compile(r"^ip nat\b", re.I)),
    ("Hostname", re.compile(r"^hostname\b", re.I)),
    ("SNMP", re.compile(r"^snmp-server\b", re.I)),
    ("NTP", re.compile(r"^ntp\b", re.I)),
    ("AAA/Users", re.compile(r"^(aaa\b|username\b|enable (secret|password)|tacacs|radius)", re.I)),
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize(text: str) -> str:
    out = []
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.rstrip()
        s = line.strip()
        if not s or s.startswith("!") or _VOLATILE.match(s):
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def normalized_checksum(text: str) -> str:
    return sha256_text(normalize(text))


def _categorize(lines: list[str]) -> list[str]:
    """Return the category of the top-level block each line belongs to."""
    cats, current = [], "Other"
    for line in lines:
        if line and not line[0].isspace():
            current = "Other"
            for name, rx in _CATEGORIES:
                if rx.match(line):
                    current = name
                    break
        cats.append(current)
    return cats


def compute_diff(source: str, target: str, use_normalized: bool = True) -> dict:
    if use_normalized:
        source, target = normalize(source), normalize(target)
    a, b = source.splitlines(), target.splitlines()
    ca, cb = _categorize(a), _categorize(b)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    lines, added, removed = [], 0, 0
    categories: dict[str, int] = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                lines.append({"type": "equal", "text": a[i1 + k], "a_no": i1 + k + 1, "b_no": j1 + k + 1})
            continue
        for k in range(i1, i2):
            removed += 1
            categories[ca[k]] = categories.get(ca[k], 0) + 1
            lines.append({"type": "removed", "text": a[k], "a_no": k + 1, "b_no": None})
        for k in range(j1, j2):
            added += 1
            categories[cb[k]] = categories.get(cb[k], 0) + 1
            lines.append({"type": "added", "text": b[k], "a_no": None, "b_no": k + 1})
    unified = "\n".join(difflib.unified_diff(a, b, "source", "target", lineterm="", n=3))
    return {
        "added": added, "removed": removed, "total_changes": added + removed,
        "categories": categories, "lines": lines, "unified": unified,
        "identical": added == 0 and removed == 0,
    }
