# host-lab

Design and operations documentation for a **self-hosted game server platform**: one always-on
machine that owns the world save, so a group of friends never again has to wait for one particular
person to be at their computer before they can play.

Valheim is the first title documented, in depth. The platform is designed so that other titles
(Minecraft, Palworld, Satisfactory, Enshrouded) fit the same shape.

## Status

This repository currently contains **documentation only**. There is no implementation yet, and
that is deliberate: the research and the design decisions come first, and are recorded here so the
implementation that follows is a transcription rather than an improvisation.

## Start here

[`docs/README.md`](docs/README.md) is the index. It carries the reading order, the layout and the
writing conventions every document in this repository follows.

If you want the concrete thing rather than the design, go straight to
[`docs/titles/valheim.md`](docs/titles/valheim.md), which runs from a bare Linux machine to friends
connected, including the networking.
