# udpecho

A disposable UDP listener and probe, for proving a network path **before** anything depends on it.

## Why this exists

[ADR 0002](../../docs/decisions/0002-reach-the-server-from-the-internet.md) rules generic UDP port
checkers and `nc -vzu` inadmissible as evidence, and it is right to. UDP has no handshake, so a
checker sends a datagram, hears nothing, and reports "open" for a port that is filtered, closed, or
attached to nothing at all. **The only admissible proof is a datagram that goes out and a reply that
comes back.**

Eventually Valheim provides that itself, with an A2S reply on 2457. But the host arrangement in
[ADR 0007](../../docs/decisions/0007-host-on-windows-with-docker-desktop-and-wsl2.md) puts three
layers under the game that no vendor page settles for external UDP: Docker Desktop's published-port
proxy, the WSL 2 network, and the Hyper-V firewall. Building the game on top of an unproven path and
then debugging the whole stack at once is the expensive order to do this in.

So this proves the path first, with the game-shaped hole left empty.

## Use

On the host, publish it exactly the way the game will be published. **The `/udp` is the point**:
omitting it publishes TCP and produces a silently dead server, which is
[ADR 0004](../../docs/decisions/0004-run-game-servers-as-containers.md) consequence 1.

```
docker build -t udpecho tools/udpecho
docker run --rm -p 2456:2456/udp --name udpecho udpecho
```

Then from **outside the network**, which in practice means a phone on mobile data with Wi-Fi off:

```
python3 udpecho.py probe --host <your public address> --port 2456
```

`probe` is stdlib-only and avoids 3.10+ syntax, so it runs on whatever Python is to hand.

## Reading the result

The probe exits non-zero on anything but a clean pass, so it can be scripted.

| Result | Means |
|---|---|
| `PASS` | Every datagram was answered. The path works in both directions. |
| `PARTIAL` | Some were answered. **Worse than a clean failure**, because in the game this presents as rubber-banding rather than as a refusal to connect. |
| `FAIL` | Nothing came back. Real evidence of a broken path, unlike a port checker's silence. |

**A warning about the address in the reply.** The server reports the source address it observed:

```
udpecho valheim-host saw 192.168.65.1:46101 at 2026-09-22T21:04:11Z echo=probe-1-481902
```

**That does not tell you where the datagram came from.** Measured on 2026-09-22 against Docker
Desktop, the published-port proxy rewrites the source to its own gateway address, so the server
sees the proxy and never the client. An earlier draft of this tool claimed the reply could
distinguish a genuine external request from a hairpinned one; testing it showed otherwise, and the
claim is removed rather than softened.

What the line is still good for is seeing **whether the proxy is in the path at all**. A
Docker-internal address means it is. Any other address is the real peer.

**So the thing that makes this test external is where you run it from**, which is what
[`networking.md`](../../docs/networking.md) asked for in the first place: a phone on mobile data
with Wi-Fi off. A router that hairpins will happily answer a probe from inside the building without
a single packet leaving it, and no amount of inspecting the reply will reveal that.

## Afterwards

Stop the container before starting the game. Both want UDP 2456.

Keep the tool. [`networking.md`](../../docs/networking.md) asks for the verification ladder to be
re-runnable, and this is the rung that isolates the network from the game: when the server stops
being reachable in six months, the first useful question is whether *anything* can be reached on
that port.
