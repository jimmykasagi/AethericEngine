#!/usr/bin/env python3
"""
Simple socket dumper for AE endpoints.

Opens a connection, sends AUTH <jwt> if provided, then prints each raw message
received (binary-safe) and any parsed ASCII/Binary frames reconstructed across
fragments. When the requested count is reached, it clears the pipe by sending
STATUS (or a custom command).
"""

from __future__ import annotations

import argparse
import socket
import sys
from typing import Generator, Tuple

from aetheric.parser import StreamParser


def recv_messages(
    host: str,
    port: int,
    jwt: str | None,
    limit: int,
    timeout: float,
    read_size: int,
    status_cmd: bytes,
) -> Generator[Tuple[int, bytes], None, None]:
    """Yield (index, data) tuples for each received message."""
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)

        if jwt:
            sock.sendall(f"AUTH {jwt}\n".encode("ascii"))

        count = 0
        while count < limit:
            try:
                data = sock.recv(read_size)
            except socket.timeout:
                continue

            if not data:
                break

            count += 1
            yield count, data

        if count >= limit:
            try:
                sock.sendall(status_cmd)
            except Exception:
                # If clearing fails, we've already delivered captured messages.
                pass


def _print_ascii_messages(msgs) -> None:
    if not msgs:
        return
    print("ascii messages:")
    for idx, msg in enumerate(msgs, 1):
        print(f"  {idx}. {msg.payload}")


def _print_binary_messages(msgs) -> None:
    if not msgs:
        return
    print("binary messages:")
    for idx, msg in enumerate(msgs, 1):
        info = f"header=0x{msg.header:02X} declared={msg.declared_len} received={msg.received_len}"
        if msg.truncated:
            info += " (truncated)"
        print(f"  {idx}. {info}")
        print(f"     payload hex: {msg.payload.hex()}")


def dump(host: str, port: int, jwt: str | None, limit: int, timeout: float, read_size: int, status_cmd: bytes) -> int:
    parser = StreamParser()
    try:
        for idx, data in recv_messages(host, port, jwt, limit, timeout, read_size, status_cmd):
            print(f"\n[# {idx}] {len(data)} bytes")
            print(f"hex: {data.hex()}")
            sys.stdout.buffer.write(b"raw: ")
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.write(b"\n")
            sys.stdout.buffer.flush()
            ascii_msgs, binary_msgs = parser.feed(data)
            _print_ascii_messages(ascii_msgs)
            _print_binary_messages(binary_msgs)
    except Exception as exc:  # pragma: no cover - manual tool
        print(f"[!] Dump failed: {exc}")
        return 1

    ascii_msgs, binary_msgs = parser.flush()
    if ascii_msgs or binary_msgs:
        print("\n[flush] Remaining buffered data")
        _print_ascii_messages(ascii_msgs)
        _print_binary_messages(binary_msgs)

    print("\n[+] Completed")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dump raw AE socket messages")
    parser.add_argument("--host", required=True, help="AE host")
    parser.add_argument("--port", required=True, type=int, help="AE port")
    parser.add_argument("--jwt", help="JWT token for AUTH")
    parser.add_argument("--limit", type=int, default=1, help="Number of messages to capture")
    parser.add_argument("--timeout", type=float, default=5.0, help="Socket timeout seconds")
    parser.add_argument("--read-size", type=int, default=8192, help="Bytes per recv")
    parser.add_argument(
        "--status-cmd",
        default=b"STATUS\n",
        type=lambda s: s.encode("ascii"),
        help='Command to clear the pipe before reading (default: "STATUS\\n")',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return dump(
        host=args.host,
        port=args.port,
        jwt=args.jwt,
        limit=args.limit,
        timeout=args.timeout,
        read_size=args.read_size,
        status_cmd=args.status_cmd,
    )


if __name__ == "__main__":  # pragma: no cover - manual tool
    raise SystemExit(main())
