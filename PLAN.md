# Aetheric Engine Capture Plan

## Objectives
- Connect to AE via TCP, authenticate with `AUTH <JWT>`, ingest messages until ≥600 parsed.
- Persist ASCII messages into SQLite `msgascii`; binary messages into `msgbinary`; also keep a raw capture file for replay.
- Provide a validator tool to replay the raw capture and confirm tables match parsed output.
- Extract any hidden message by analyzing ordered ASCII + binary payloads.

## Protocol Notes (per README)
- AE emits ASCII frames delimited by `$` (start) and `;` (end); payload: ≥5 printable ASCII chars excluding delimiters.
- Binary frames: header byte `0xAA` or `0xBB`; followed by 5-byte big-endian payload length; payload is that many octets.
- Messages are unbounded by protocol; fragmentation possible (1/20); rare drop of final fragment (1/50); occasionally multiple messages back-to-back in one read.
- Stop sequence: send `STATUS`, drain remaining bytes, then disconnect.

## Stream Parsing Strategy
- Maintain two rolling buffers: one for ASCII frame detection, one for binary frames.
- ASCII: search for `$`; accumulate until `;`; on completion, store payload. If delimiters appear inside, treat earliest `$` as start.
- Binary: look for header byte (0xAA/0xBB); read next 5 bytes to get length (big-endian u40); then read that many bytes as payload. If stream ends early, mark truncated.
- Handle concatenated messages by continuing parsing after each completion within the same buffer.
- Keep counts by type; stop after 600 complete messages (still drain before close).

## Persistence
- SQLite file on disk (no Docker needed). Tables:
  - `msgascii(payload TEXT, ts INTEGER DEFAULT CURRENT_TIMESTAMP, idx INTEGER PRIMARY KEY AUTOINCREMENT)`
  - `msgbinary(header INTEGER, payload BLOB, declared_len INTEGER, received_len INTEGER, ts INTEGER DEFAULT CURRENT_TIMESTAMP, idx INTEGER PRIMARY KEY AUTOINCREMENT, truncated INTEGER DEFAULT 0)`
- Append-only raw capture file (e.g., `capture.bin`) of exact byte stream to support replay.
- Use streaming writes/chunking to avoid holding large payloads in memory; gate extremely large payloads if needed.

## Validation App
- Replay `capture.bin` through the parser; compare reconstructed rows to stored tables.
- Unit tests for: ASCII framing (including nested delimiters), binary length parsing, fragmented frames reassembly, and truncation detection.

## Hidden Message Extraction Approach
- Preserve arrival order (idx + timestamp) across tables.
- First pass: concatenate ASCII payloads; separately inspect binary payloads (`0xAA` vs `0xBB`) for patterns; convert to hex/base64.
- Treat `0xAA/0xBB` sequence as potential bits/markers; examine `0xBB` payloads and their neighbors closely.
- Run entropy checks to find low-entropy segments; try base64/hex/ASCII decoding, zlib/deflate/gzip on binaries, XOR with nearby ASCII bytes, and 7-bit packing.
- Log each transform attempt (inputs + output hash) for reproducibility; rerun winning transform across full ordered dataset.

## Runbook
1) Obtain JWT + host:port. Open TCP socket; send `AUTH <JWT>`.
2) Start read loop; feed bytes into parser; write to SQLite + `capture.bin` as parsed.
3) After ≥600 complete messages, send `STATUS`, drain until socket closes/timeout, then close.
4) Run validator against `capture.bin` to ensure tables match parsing logic.
