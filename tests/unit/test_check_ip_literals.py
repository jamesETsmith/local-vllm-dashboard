from pathlib import Path

from local_vllm_dashboard.security.ip_literals import check_paths


def test_rejects_non_documentation_network_addresses(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.txt"
    blocked = (
        ".".join(("10", "20", "30", "40")),
        ".".join(("100", "64", "12", "34")),
        ".".join(("169", "254", "2", "3")),
        ":".join(("fd12", "3456", "", "1")),
    )
    source.write_text(
        "\n".join(f"address={address}" for address in blocked) + "\n",
        encoding="utf-8",
    )

    findings = check_paths((source,))

    assert [finding.address for finding in findings] == list(blocked)
    assert [finding.line for finding in findings] == [1, 2, 3, 4]


def test_allows_public_documentation_and_local_bind_addresses(tmp_path: Path) -> None:
    source = tmp_path / "safe.txt"
    source.write_text(
        "public=8.8.8.8\n"
        "documentation=192.0.2.10 198.51.100.20 203.0.113.30 2001:db8::1\n"
        "local=127.0.0.1 ::1 0.0.0.0\n",
        encoding="utf-8",
    )

    assert check_paths((source,)) == ()


def test_skips_binary_files(tmp_path: Path) -> None:
    source = tmp_path / "binary.bin"
    source.write_bytes(b"\xff\xfe" + b".".join((b"10", b"20", b"30", b"40")))

    assert check_paths((source,)) == ()
