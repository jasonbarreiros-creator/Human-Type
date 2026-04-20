# HUMAN-TYPE

Realistic human-like typing automation — Simulates natural typing with variable speed, random typos, self-corrections, and a personal profile that learns from your sessions.

Features

- **Human-like typing** — Burst typing (2–6 chars), variable delays, natural pauses
- **Adjustable speed** — Slow → Normal → Fast → Expert
- **Typo simulation** — Configurable intensity with intelligent corrections
- **Live statistics** — Real-time WPM, typos, corrections, progress bar
- **Personal Profile** — Learns your actual WPM after 5 sessions
- **AI text generation** — Optional Ollama (local) or Claude API
- **Keyboard shortcuts** — `Cmd+Enter` start, `Esc` stop, `P` pause, `S` skip

## Quick Start

## Hotkeys

| Key | Action |
|-----|--------|
| `Cmd+Enter` | Start typing |
| `Esc` | Stop |
| `P` | Pause / Resume |
| `S` | Skip sentence |

## Acknowledgements

- **Human-like typing logic & adjacent-key typo system** — Inspired by [Auto-Type](https://github.com/GitLitAF/Auto-Type) by [GitLitAF](https://github.com/GitLitAF). Thank you for the foundational ideas!
- **PyAutoGUI** — Keyboard/mouse automation

## License

Apache License 2.0 — see [LICENSE](LICENSE) file for details.

### Prerequisites
- Python 3.9+
- Chrome browser

### 1. Install backend
```bash
pip install pyautogui
