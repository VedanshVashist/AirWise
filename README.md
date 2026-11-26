# Airwise

Airwise is a local-first air-quality assistant for households and community groups. It shows the current US Air Quality Index (AQI) and hourly forecasts for a location, then suggests actions for the household.

## Live Version!
https://airwise-chi-eight.vercel.app/

## Deploy to Vercel

Push this repository to your Git provider and import it as a new Vercel project. Select the repository root and the **Other** framework preset, leave the build command empty, and click **Deploy**. Vercel serves the dashboard from `public/` and runs the endpoints in `api/` as Python functions.

The dashboard, city search, browser alerts and built-in guide work without API keys. Hosted alerts require notification permission and an open page. For optional AI replies, add `AIRWISE_MODEL_URL`, `AIRWISE_MODEL` and, if required, `AIRWISE_MODEL_KEY` in the Vercel project's environment settings, then redeploy. Use a hosted endpoint reachable from Vercel that supports OpenAI-compatible chat completions and structured JSON outputs.

## Run locally

### Challenge vertical and campaign studio

Airwise targets environmental awareness for households and community organisers. In **Campaign studio**, select school families, commuters or neighbours and create a campaign. Each campaign combines an audience-specific emissions action, an explanation of how ground-level ozone affects trees, and the selected city's modeled US AQI. Airwise includes the observation time and timezone. When only sample or stale data is available it omits the number and points readers to local advisories. The general ozone fact applies to sensitive vegetation and does not attribute today's AQI to a particular pollutant. [EPA ecosystem effects](https://www.epa.gov/ground-level-ozone-pollution/ecosystem-effects-ozone-pollution)

Download the PNG or select and copy its plain-text caption. Review the timestamp before sharing. Airwise composes the poster in the browser. The local template works with zero provider credentials.

### Enable OpenAI campaign headlines

Sign in to the OpenAI API platform as the project owner and create a dedicated project key with write access to Chat Completions. Configure the following **server environment variables** in Vercel and redeploy, or provide them to the local Python process. The app never asks visitors for account credentials. API usage has separate billing from ChatGPT. [API key safety](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety) · [Billing](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform)

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Dedicated secret for campaign headlines. Set it only in the backend environment. |
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | HTTPS endpoint and write token for a dedicated Upstash Redis database with eviction disabled. |
| `AIRWISE_CAMPAIGN_DAILY_LIMIT` | Optional maximum OpenAI campaign calls across all visitors per UTC day. Defaults to 25. Set to 0 to disable. |
| `AIRWISE_CAMPAIGN_MODEL` | Optional Chat Completions model. Defaults to `gpt-4.1-mini`. |

Every paid campaign call first reserves a slot in a shared Redis transaction. Anyone using the public app can consume these slots. Failed model calls also use a slot. Missing credentials, exhausted quota and provider failures select a labeled template. OpenAI receives the selected audience and a fixed writing instruction. The city, coordinates and AQI stay out of that request. The separate assistant endpoint has its own configuration and does not use the campaign key. [Upstash REST API](https://upstash.com/docs/redis/features/restapi)

Run `python -m unittest -v` for offline campaign-provider and quota tests. Run `node --test campaign.test.cjs` for the freshness and attribution checks.

### Start the server

Install Python 3.11 or newer. The dashboard uses the Python standard library and can run without the optional AI model.

On Windows, double-click **Start Airwise.cmd**. From a terminal on any platform, run this command in the project directory (use `python3` if that is your Python command).

```sh
python server.py --open
```

The command opens the [local dashboard](http://localhost:8765). If the default port is busy, run `python server.py --port 8766 --open`. Press `Ctrl+C` in the terminal to stop the server.

## Public air quality API

`GET /api/observation?lat=52.52&lon=13.405` returns the latest outdoor PM2.5 and PM10 measurement within 10 km from [Sensor.Community](https://github.com/opendata-stuttgart/meta/wiki/EN-APIs). The response includes the sensor ID, Unix timestamp and concentration unit. A successful lookup with no qualifying reading returns `observation: null`. The dashboard checks this keyless feed alongside the Open-Meteo AQI every ten minutes. Both providers receive the selected coordinates.

## Using the app

- Choose a city or use device location. Open-Meteo supplies current modeled US AQI, hourly forecasts, PM2.5, PM10, nitrogen dioxide and ozone. Forecast times follow the selected location. The app labels saved readings and sample data during outages.
- Set household, transport and filtration preferences in **Household**. **Action plan** explains how each choice changes emissions or exposure and records daily completion on this device.
- Ask the **AI assistant** about commuting, indoor air, school runs or group activities. At elevated AQI the model assembles a plan from actions suitable for the reading. When inference is unavailable, replies are labeled as local guide responses.
- In **Air alerts**, choose a notification threshold and save. On Windows the local server checks every ten minutes and sends one desktop notification per qualifying reading and location. Keep the server running. Windows notification settings and Focus mode control display. On other systems browser notifications require permission and an open page. Alerts use fresh estimates only.

## Local AI

On Windows x64, run `python setup_ai.py` to download and verify the CPU runtime and Qwen2.5-1.5B-Instruct model (about 1.15 GB). The installer stores them in `.airwise/ai/`. The app starts inference on demand. The first answer can take longer while the model loads.

To use another inference server, set `AIRWISE_MODEL_URL` to its OpenAI-compatible base URL including `/v1`, and set `AIRWISE_MODEL` to its model name. Set `AIRWISE_MODEL_KEY` only if the service requires it. That server must support structured JSON outputs. Using a remote model sends the question, recent conversation, location name, AQI and selected lifestyle preferences to that provider.

The application binds to the loopback interface. Household preferences and action history are stored in browser storage. Desktop alert settings and recent alerts are stored in `.airwise/alerts.json`. City searches and coordinates are sent to Open-Meteo for air data.

## Sources

- [Open-Meteo air-quality data and attribution](https://open-meteo.com/en/docs/air-quality-api) and [Copernicus Atmosphere Monitoring Service](https://atmosphere.copernicus.eu/)
- [AirNow US AQI categories](https://www.airnow.gov/aqi/aqi-basics/) and [EPA cleaner indoor air guidance](https://www.epa.gov/wildfires/how-create-cleaner-air-room-home)
- [Qwen model and license](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) and [llama.cpp runtime](https://github.com/ggml-org/llama.cpp)
- DM Sans is distributed under the SIL Open Font License in `public/FONT-LICENSE.txt`. The Delhi skyline is generated artwork.

## License

Airwise's original code and documentation use the [MIT License](LICENSE). The bundled DM Sans font uses the [SIL Open Font License](public/FONT-LICENSE.txt).
