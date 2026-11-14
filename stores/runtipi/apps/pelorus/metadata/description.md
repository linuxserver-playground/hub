# Pelorus

![Pelorus](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/pelorus-logo.png)

[Pelorus](https://github.com/linuxserver/pelorus) is an AI navigator for Selkies-powered Linux desktops. Pelorus runs a FastAPI server that gives an LLM agent (Ollama, OpenAI-compatible, or Gemini) control over mouse, keyboard, screenshot, and window management via the [Pixelflux computer-use backend](https://github.com/linuxserver/pixelflux#computer-use-interface-wayland), a Linux accessibility tree (AT-SPI), and optional KWin D-Bus integration.

## Application setup

https://github.com/user-attachments/assets/226bf96f-a6d6-46c2-95f4-677334dddd03

## Split Plane View

Pelorus ships with a **split plane** landing page served over HTTPS on port **3001**. The left pane loads the raw Pelorus chat UI and the right pane loads your Selkies desktop session in an iframe. Both are also available directly via their subfolders:

* **Pelorus UI** - `https://yourhost:3001/pelorus/`
* **Selkies Session** - `https://yourhost:3001/selkies/`

HTTP on port **3000** serves only the Selkies desktop session (no Pelorus UI).

### Provider Environment Variables

Set these to setup a provider on first boot:

| Variable | Default | Description |
|---|---|---|
| `PELORUS_PROVIDER` | `ollama` | Provider type (`ollama`, `openai`, `gemini`) |
| `PELORUS_ENDPOINT` | `http://host:11434` | LLM API endpoint |
| `PELORUS_MODEL` | `gemma4:12b` | Model name |
| `PELORUS_API_KEY` | *(empty)* | API key for the provider |

### Example API Call

Use `-k` with `curl` to skip certificate verification (the container uses a self-signed cert by default):

```bash
curl -k -s https://localhost:3001/pelorus/api/run \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"open kate please","response_format":"minimal","stream":true}'
```

Image: `ghcr.io/linuxserver-playground/pelorus:latest` ([https://github.com/linuxserver-playground/docker-pelorus](https://github.com/linuxserver-playground/docker-pelorus))
