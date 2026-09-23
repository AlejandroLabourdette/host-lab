#!/usr/bin/env python3
"""Prove that a UDP path works, end to end, before anything depends on it.

ADR 0002 rules generic UDP port checkers and ``nc -vzu`` inadmissible as
evidence, and it is right to: UDP has no handshake, so a checker reports
"open" for a port that is filtered, closed or attached to nothing at all. The
only admissible proof is a datagram that goes out and a reply that comes back.

Valheim itself is the eventual proof, via an A2S query on 2457. But the whole
point of this tool is to test the network path *before* the game exists, on a
host arrangement (ADR 0007: Docker Desktop, WSL 2, mirrored networking) whose
UDP behaviour from outside the network no vendor page settles either way.

The reply carries the source address the server observed, which is diagnostic
but is *not* proof of where the datagram came from: measured on 2026-09-22,
Docker Desktop's published-port proxy rewrites the source to its own gateway
address, so the server sees the proxy rather than the client. What proves
external origin is running ``probe`` from a device that is genuinely not on
the LAN, which is what ``networking.md`` has always asked for.

Stdlib only, and no 3.10+ syntax, so ``probe`` runs on whatever is to hand.
"""

from __future__ import annotations

import argparse
import datetime
import os
import random
import socket
import sys

BUFFER_SIZE = 2048
DEFAULT_PORT = 2456


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def serve(host: str, port: int) -> int:
    """Answer every datagram, naming the source address that was observed."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))

    hostname = socket.gethostname()
    print("udpecho listening on {0}:{1} as {2}".format(host, port, hostname), flush=True)

    while True:
        try:
            payload, source = sock.recvfrom(BUFFER_SIZE)
        except KeyboardInterrupt:
            print("udpecho stopping", flush=True)
            return 0

        seen = "{0}:{1}".format(source[0], source[1])
        text = payload.decode("utf-8", "replace").strip()
        print("{0} from {1} payload={2!r}".format(_now(), seen, text), flush=True)

        reply = "udpecho {0} saw {1} at {2} echo={3}".format(hostname, seen, _now(), text)
        sock.sendto(reply.encode("utf-8"), source)


def probe(host: str, port: int, count: int, timeout: float) -> int:
    """Send datagrams and report how many were answered. Non-zero on failure."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)

    answered = 0
    for attempt in range(1, count + 1):
        nonce = "probe-{0}-{1:06d}".format(attempt, random.randrange(1000000))
        try:
            sock.sendto(nonce.encode("utf-8"), (host, port))
            reply, _ = sock.recvfrom(BUFFER_SIZE)
        except socket.timeout:
            print("  {0}  no reply within {1}s".format(nonce, timeout))
            continue
        except OSError as error:
            print("  {0}  {1}".format(nonce, error))
            continue

        text = reply.decode("utf-8", "replace").strip()
        if nonce not in text:
            print("  {0}  reply did not echo the nonce: {1}".format(nonce, text))
            continue

        answered += 1
        print("  {0}  {1}".format(nonce, text))

    print("\n{0}/{1} answered by {2}:{3}".format(answered, count, host, port))

    if answered == 0:
        print(
            "FAIL  Nothing came back. The datagram did not reach a listener, or the\n"
            "      reply did not return. This is real evidence of a broken path, unlike\n"
            "      a port checker's silence. Work down the ladder in networking.md."
        )
        return 1

    if answered < count:
        print(
            "PARTIAL  Some datagrams were answered and some were not. A marginal path\n"
            "         is worse than a broken one, because it presents in the game as\n"
            "         rubber-banding rather than as a failure to connect."
        )
        return 1

    print(
        "PASS  Every datagram was answered, so the path works in both directions.\n"
        "\n"
        "      This proves the path only if this machine is genuinely off the LAN.\n"
        "      A router that hairpins will answer a test from inside the building\n"
        "      without any of it leaving, so use mobile data with Wi-Fi off.\n"
        "\n"
        "      Do not try to read origin out of the address in the reply. Docker\n"
        "      Desktop's published-port proxy rewrites the source to its own\n"
        "      gateway, so a Docker-internal address there says the proxy is in\n"
        "      the path, and nothing about who sent the datagram."
    )
    return 0


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    server = sub.add_parser("serve", help="listen and answer, on the host")
    # Binding to all interfaces is the entire point: this listener exists to be
    # reached from outside the network, published exactly as the game will be.
    server.add_argument(
        "--host",
        default=os.environ.get("UDPECHO_HOST", "0.0.0.0"),  # noqa: S104
    )
    server.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("UDPECHO_PORT", DEFAULT_PORT)),
    )

    client = sub.add_parser("probe", help="send and report, from outside the network")
    client.add_argument("--host", required=True, help="the public address to test")
    client.add_argument("--port", type=int, default=DEFAULT_PORT)
    client.add_argument("--count", type=int, default=3)
    client.add_argument("--timeout", type=float, default=5.0)

    args = parser.parse_args(argv)

    if args.command == "serve":
        return serve(args.host, args.port)
    return probe(args.host, args.port, args.count, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
