# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Clean-room re-implementation of the "iLnk"/"iLnkP2P"/"PPPP" UDP protocol spoken by cheap TXW817-based IP cameras (branded X5 / A9, app `YsxLite`). The client discovers cameras on the LAN, establishes a session, and streams MJPEG + 8kHz A-law audio out over HTTP. See `README.md` for the protocol write-up, sequence diagrams and reversing notes; `proto` is a raw trace of the observed packet exchange.

The implementation is **Python** (asyncio + aiohttp) in `cam_reverse/`. It began as a port of a now-removed TypeScript version; `PYTHON.md` documents the package layout and has a module map. (A previous git history / earlier branches contain the TypeScript, if you ever need to diff against it.)

## Commands

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # runtime: aiohttp, PyYAML; dev: pytest

.venv/bin/pytest tests_py -q            # full test suite
.venv/bin/pytest tests_py/test_fn.py::test_parses_wifiscan_chan0   # single test

cam-reverse.py http_server --config_file config.yml   # MJPEG UI on :5000
cam-reverse.py pair --ssid <SSID> --password <PW>      # while on the camera's AP
cam-reverse.py frame --discovery_ip <IP> --out out.jpg
```

`cam-reverse.py` (installed command), `python cam-reverse.py` (root launcher, no
install needed) and `python -m cam_reverse` are equivalent entry points.

## Architecture

Layered, with each layer talking to the next through a tiny synchronous `EventEmitter` (`event_emitter.py`):

1. **`discovery.py`** — broadcasts `LanSearch` to `config["discovery_ips"]` on UDP/32108 every 3s; each `PunchPkt` reply emits `discover` with a `DevSerial` (the camera's `dev_id`).
2. **`session.py`** — `make_session(Handlers, dev, addr, on_login, timeout_ms)` opens a per-camera connected UDP datagram endpoint, drives the handshake (`P2pRdy` → `ConnectUser` → ticket), and runs two asyncio timer tasks: keepalive/timeout (`P2PAlive`) and Drw retransmit. Owns the `Session` object (ticket, `outgoing_command_id`, `unacked_drw`, in-progress `cur_image`). Emits `login`, `frame`, `audio`, `ListWifi`, `disconnect`.
3. **`handlers.py`** (incoming) / **`impl.py`** (outgoing) — the actual packet codecs.

The three consumers (`http_server.py`, `pair.py`, `capture_single.py`) are the same shape: call `discover_devices`, `make_session` on `discover`, then subscribe to the session's events. They differ only in `on_login` and what they do with frames. `make_session` returns synchronously and schedules the UDP endpoint as a task, so a caller can attach event handlers before the endpoint comes up on the next loop turn.

### Packet model

Two distinct command namespaces, both in `datatypes.py` — don't conflate them:

- **`Commands`** — the outer UDP packet type (`0xf1xx`: `LanSearch`, `P2pRdy`, `Drw`, `DrwAck`, `P2PAlive`, …). `session.py`'s `Handlers` dict maps every one of these (by name) to a handler; unimplemented ones point at `not_impl`.
- **`ControlCommands`** — the inner command inside a `Drw` payload (`ConnectUser`, `DevStatus`, `StartVideo`, `WifiSettingsSet`, …). `ccDest` holds each one's destination field.

`Drw` (`0xf1d0`) is the workhorse and is demultiplexed on the stream byte at offset 5: `1` = data (video/audio, → `_deal_with_data`), `0` = control (→ `create_response_for_control_command`). Data packets are further discriminated by a `55 aa 15 a8` frame header; some cameras send framed JPEG (stream type `0x03`), others send raw unframed JPEG segments starting with the JPEG SOI marker — `_deal_with_data` handles both, which is why it looks redundant.

Control payloads longer than 4 bytes are obfuscated with `xq_bytes_enc`/`xq_bytes_dec` (`crypto.py`), always with `rotate = 4`.

### Two conventions that bite

- **`DV` (`dataview.py`) shares its backing `bytearray`.** `add(offset)` returns another `DV` over the *same* buffer, so in-place mutation (the Xq de/obfuscation) propagates — the codecs depend on this, exactly like the JS `DataView` the port came from. Incoming datagrams are wrapped in a fresh `bytearray` at the socket boundary so decryption can mutate them.
- **Mixed endianness.** Protocol header fields are big-endian (`read_u16`), but many payload fields are little-endian (`read_u16le`/`read_u32le`) — see `parse_dev_status_ack` and `parse_list_wifi`. Match whatever the surrounding parser does; the hex fixtures in `tests_py/test_fn.py` are the ground truth.

### Settings

`settings.py` exposes a mutable module-level `config` dict. Read it as `settings.config[...]` at call time (not `from .settings import config` bound at import), because `load_config` rebinds it and the CLI overwrites individual keys afterwards. The merge with `DefaultConfig` is shallow — a partial `http_server:` or `logging:` block in the YAML drops the sibling defaults. `http_server.py` also mutates `config["cameras"][dev_id]` at runtime (the `/rotate/` and `/mirror/` routes).

### HTTP streaming

The session layer emits `frame`/`audio` **synchronously** from the datagram callback, but aiohttp writes are async. The bridge (`http_server.py`) gives each connected client an `asyncio.Queue`; the sync callbacks `put_nowait` into every queue (dropping on `QueueFull`), and the route coroutines drain the queue and `await resp.write(...)`. Video is `multipart/x-mixed-replace`; audio is SSE. The web UI (`assets/asd.html`) and favicon (`assets/cam.ico.gz`) are loaded from package data at runtime.

## Tests

`tests_py/test_fn.py` is a regression suite built from **real captured packets** pasted in as hex (device status, wifi scans, punch packets from differently-shaped serials); the builder tests assert byte-for-byte against captured output. When changing a parser or builder, add the capture that motivated it rather than a synthetic buffer. `tests_py/test_integration.py` uses `mock_server.py` to stand up a fake camera on UDP/32108 and exercise discovery end to end. `pyproject.toml` sets `asyncio_mode = "auto"`, so `async def test_*` just work.

## Reversing artifacts (not part of the running client)

`dissector.lua` (partial Wireshark dissector), `types/all.h` (Ghidra-recovered structs), `scripts/dec.py` + `scripts/dec_svr.py` (decode the hardcoded phone-home server strings), `proto` (packet-sequence trace), `data/`, `diagrams/`. The Frida hooks used during reversing were removed once the protocol was understood; the recovered behaviour now lives in `cam_reverse/`.
