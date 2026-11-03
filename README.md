# Cosysense for Home Assistant

Energy optimisation for commercial buildings. Bring your Cosysense sensors (CO2, occupancy, temperature, energy, gas, water) into Home Assistant.

The integration reads one or more of your Cosysense sites through the read-only Cosysense customer API. Every sensor and meter becomes a device, placed in the Home Assistant area named after its room in Cosysense. Energy, gas and water meters work with the Energy dashboard.

## What you need

- A Cosysense site with sensors.
- An integration token from Cosysense: an app client ID and a refresh token. Ask your Cosysense contact. The token is read-only, covers only the sites it was granted for and lasts 90 days.

## Install

1. In HACS, open the menu, choose **Custom repositories**, add `https://github.com/cosysense/homeassistant-cosysense` with category **Integration**, then install **Cosysense**.
2. Restart Home Assistant.
3. Go to **Settings > Devices & services > Add integration > Cosysense**. Enter the client ID and refresh token, then pick your sites. Each site becomes its own entry.

Manual install: copy `custom_components/cosysense` into your `config/custom_components` folder and restart.

## Options

| Option | Default | Range |
| --- | --- | --- |
| Poll interval | 120 s | 30 to 900 s |
| Mark a sensor unavailable after no update for | 3 h | 1 to 48 h |
| Buildings and levels to show | all | any subset |

## How it behaves

- The latest reading of every point is fetched each poll. The sensor list is refreshed hourly; new or removed sensors reload the entry.
- Values arrive calibrated. Gas reported in litres is shown in m³.
- The token is exchanged for a short-lived session on every poll. If it expires or is revoked, the entities go unavailable and Home Assistant asks for a new token.
- A steady reading can look up to five minutes older than the sensor's last report. That is expected.
- Diagnostics downloads hide the client ID and refresh token.

## Support

Open an issue on this repository. Include a diagnostics download.

## Licence

MIT. See `LICENSE`.
