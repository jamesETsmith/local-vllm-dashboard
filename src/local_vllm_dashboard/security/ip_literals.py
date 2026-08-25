from __future__ import annotations

import ipaddress
import re
import sys
from dataclasses import dataclass
from pathlib import Path

IPV4_PATTERN = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
IPV6_PATTERN = re.compile(
    r"(?<![\da-fA-F:])(?:[\da-fA-F]{0,4}:){2,7}[\da-fA-F]{0,4}(?![\da-fA-F:])"
)
ALLOWED_ADDRESSES = frozenset(
    ipaddress.ip_address(value)
    for value in (
        ".".join(("0", "0", "0", "0")),
        ".".join(("127", "0", "0", "1")),
        ":".join(("", "", "1")),
    )
)
ALLOWED_NETWORKS = (
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("2001:db8::/32"),
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    address: str


def is_allowed(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_global
        or address in ALLOWED_ADDRESSES
        or any(address in network for network in ALLOWED_NETWORKS)
    )


def addresses_in(line: str) -> tuple[str, ...]:
    candidates = IPV4_PATTERN.findall(line) + IPV6_PATTERN.findall(line)
    return tuple(dict.fromkeys(candidates))


def check_paths(paths: tuple[Path, ...]) -> tuple[Finding, ...]:
    findings = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(lines, start=1):
            for candidate in addresses_in(line):
                try:
                    address = ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                if not is_allowed(address):
                    findings.append(Finding(path=path, line=line_number, address=candidate))
    return tuple(findings)


def main() -> int:
    paths = tuple(Path(value) for value in sys.argv[1:])
    if not paths:
        print("provide one or more files to scan")
        return 2
    findings = check_paths(paths)
    for finding in findings:
        print(f"{finding.path}:{finding.line}: non-public IP literal {finding.address}")
    if findings:
        print("Use an RFC 5737 IPv4 or RFC 3849 IPv6 documentation address instead.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
