# Vendored JavaScript

These files are vendored — do not edit.

## elkjs 0.11.0

Source: <https://www.npmjs.com/package/elkjs>

License: EPL-2.0 (Eclipse Public License 2.0)

- `elk.bundled.js` — ELK layout engine (main thread + worker combined)
  - SHA-256: `cbf61b0182e9085d36dcd5b392f57cc816273169ac40bde80b52b808444c5cf8`
- `elk-worker.min.js` — ELK worker-only build (loaded via `workerUrl`)
  - SHA-256: `c0dc844ac1739a1e1e4f64d08a9ec4594818d5aa7e0cb26e5096b6d34b864e2b`

Used to run the layered graph layout + orthogonal routing in the browser.

### How to upgrade

```bash
curl -fsSL -o elk.bundled.js "https://unpkg.com/elkjs@<version>/lib/elk.bundled.js"
curl -fsSL -o elk-worker.min.js "https://unpkg.com/elkjs@<version>/lib/elk-worker.min.js"
shasum -a 256 elk.bundled.js elk-worker.min.js  # update the hashes above
```
