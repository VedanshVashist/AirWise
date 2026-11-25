# Airwise

Airwise is a local-first air-quality assistant for households and community groups. Open **Start Airwise.cmd** on Windows, or run `python server.py --open` with Python 3.11 or newer. The dashboard is available at http://localhost:8765.

## Using the app

- Choose a city or use device location. Open-Meteo supplies current modeled US AQI, hourly forecasts, PM2.5, PM10, nitrogen dioxide and ozone. Forecast times follow the selected location. The app labels saved readings and sample data during outages.
- Set household, transport and filtration preferences in **Household**. **Action plan** explains how each choice changes emissions or exposure and records daily completion on this device.
- Ask the **AI assistant** about commuting, indoor air, school runs or group activities. At elevated AQI the model assembles a plan from actions suitable for the reading. When inference is unavailable, replies are labeled as local guide responses.
- In **Air alerts**, choose a notification threshold and save. On Windows the local server checks every ten minutes and sends one desktop notification per qualifying reading and location. Keep the server running. Windows notification settings and Focus mode control display. On other systems browser notifications require permission and an open page. Alerts use fresh estimates only.

## Local AI

This workspace includes the Windows x64 CPU runtime and Qwen2.5-1.5B-Instruct in the ignored `.airwise/ai` directory. On a fresh checkout run `python setup_ai.py` to download and verify the runtime and model (about 1.15 GB). The app starts inference on demand. The first answer can take longer while the model loads.

To use another inference server, set `AIRWISE_MODEL_URL` to its OpenAI-compatible base URL including `/v1`, and set `AIRWISE_MODEL` to its model name. Set `AIRWISE_MODEL_KEY` only if the service requires it. That server must support structured JSON outputs. Using a remote model sends the question, recent conversation, location name, AQI and selected lifestyle preferences to that provider.

The application binds to the loopback interface. Household preferences and action history are stored in browser storage. Desktop alert settings and recent alerts are stored in `.airwise/alerts.json`. City searches and coordinates are sent to Open-Meteo for air data.

## Sources

- [Open-Meteo air-quality data and attribution](https://open-meteo.com/en/docs/air-quality-api) and [Copernicus Atmosphere Monitoring Service](https://atmosphere.copernicus.eu/)
- [AirNow US AQI categories](https://www.airnow.gov/aqi/aqi-basics/) and [EPA cleaner indoor air guidance](https://www.epa.gov/wildfires/how-create-cleaner-air-room-home)
- [Qwen model and license](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) and [llama.cpp runtime](https://github.com/ggml-org/llama.cpp)
- DM Sans is distributed under the SIL Open Font License in `public/FONT-LICENSE.txt`. The Delhi skyline is generated artwork.
