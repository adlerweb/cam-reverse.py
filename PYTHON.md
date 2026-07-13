# Python port

`cam_reverse/` is the camera client, feature-complete across all three subcommands. It uses **asyncio** (UDP datagram endpoints + timer tasks) and **aiohttp** (MJPEG + SSE), with PyYAML for the config file. It started life as a port of an earlier TypeScript implementation (since removed); the module names below preserve that lineage.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # runtime deps: aiohttp, PyYAML
```

## Run

```bash
cam-reverse.py http_server --config_file config.yml   # MJPEG UI on :5000
cam-reverse.py pair --ssid <SSID> --password <PW>      # while on the camera's AP
cam-reverse.py frame --discovery_ip <IP> --out out.jpg
# from a checkout without installing: python cam-reverse.py <subcommand> ...
# equivalently: python -m cam_reverse <subcommand> ...
```

The config file format, CLI flags, HTTP routes and streaming behaviour match the
TypeScript version; `config.example.yml` works unchanged.

## Test

```bash
.venv/bin/pytest tests_py -q
```

`tests_py/test_fn.py` is the port of the TS regression suite — the same captured
hex packets, asserted byte-for-byte. `tests_py/test_integration.py` drives
discovery against the asyncio mock camera in `cam_reverse/mock_server.py`.

## Module map

| Module | Responsibility |
| --- | --- |
| `dataview.py` | `DV`: byte cursor with `add()` + big/little-endian read/write over a shared `bytearray` |
| `crypto.py` | `xq_bytes_enc`/`dec` — the control-payload obfuscation |
| `datatypes.py` | `Commands` (outer packet type) vs `ControlCommands` (inner Drw command) |
| `impl.py` | outgoing packet builders + `parse_PunchPkt` |
| `handlers.py` | incoming handlers + `_deal_with_data` frame assembly |
| `session.py` | `Session` on a connected datagram endpoint; two timer tasks (keepalive, Drw retransmit) |
| `discovery.py` | broadcast LanSearch, emit `discover` |
| `http_server.py` | aiohttp; per-client `asyncio.Queue` bridges the sync `frame`/`audio` events to async writes |
| `event_emitter.py` | tiny synchronous `on`/`emit` |
| `pair.py` / `capture_single.py` | the `pair` and `frame` subcommands |
| `cli.py` | argparse entry point (`cam-reverse.py`) |

### Things to know

- **`DV` shares its backing `bytearray`** so `add(offset)` sub-views mutate the
  original — the Xq de/obfuscation relies on this, same as the JS `DataView`.
- **Endianness is mixed**: headers big-endian (`read_u16`), many payload fields
  little-endian (`read_u16le`/`read_u32le`). The hex fixtures in `test_fn.py`
  are ground truth.
- The web UI (`asd.html`) and favicon (`cam.ico.gz`) are packaged under
  `cam_reverse/assets/` and loaded at runtime (the TS build inlines them).
