# A disposable UDP listener, used to prove a network path before the game exists.
# See tools/udpecho/README.md and docs/networking.md.
#
# The tag is pinned rather than floating. ADR 0004 consequence 5 makes "latest"
# a dangerous tag, and a diagnostic whose behaviour changes under you is worse
# than no diagnostic.
FROM python:3.12-alpine

COPY udpecho.py /usr/local/bin/udpecho
RUN chmod +x /usr/local/bin/udpecho

# Runs unprivileged. Nothing here needs root, and this container exists to be
# exposed to the internet.
USER nobody

EXPOSE 2456/udp
ENTRYPOINT ["/usr/local/bin/udpecho"]
CMD ["serve"]
