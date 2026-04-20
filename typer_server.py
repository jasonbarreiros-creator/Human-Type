#!/usr/bin/env python3
"""
HumanTyper Pro — Backend Server v3
====================================
Human-like typing with burst mode, word familiarity, context-aware pauses,
typo strategies, sentence skipping, pause/resume, and graceful shutdown.

SETUP:
    pip3 install pyautogui

RUN:
    python3 typer_server.py
"""
import http.server, json, threading, time, random, math, signal, sys

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False
    print("WARNING: pyautogui not installed. Run: pip3 install pyautogui")

# ── Keyboard layout ────────────────────────────────────────────────────────────
ADJACENT = {
    'q':['w','a'],'w':['q','e','s'],'e':['w','r','d'],'r':['e','t','f'],
    't':['r','y','g'],'y':['t','u','h'],'u':['y','i','j'],'i':['u','o','k'],
    'o':['i','p','l'],'p':['o'],'a':['q','s','z'],'s':['w','a','d','x'],
    'd':['e','s','f','c'],'f':['r','d','g','v'],'g':['t','f','h','b'],
    'h':['y','g','j','n'],'j':['u','h','k','m'],'k':['i','j','l'],'l':['o','k'],
    'z':['a','x'],'x':['s','z','c'],'c':['d','x','v'],'v':['f','c','b'],
    'b':['g','v','n'],'n':['h','b','m'],'m':['j','n'],
}

# Common words typed faster with fewer errors
FAMILIAR_WORDS = {
    'the','and','that','this','with','for','are','not','you','have',
    'was','they','from','but','been','has','had','can','will','would',
    'there','their','which','about','when','your','more','also','into',
    'time','some','could','these','its','than','then','now','look','only',
    'come','think','know','take','people','year','good','some','him','her',
}

# ── Shared state ───────────────────────────────────────────────────────────────
stop_flag   = threading.Event()
pause_flag  = threading.Event()
pause_flag.set()  # set = not paused
skip_flag   = threading.Event()

state = {
    "state": "idle",
    "chars": 0, "typos": 0, "corrections": 0,
    "wpm": 0, "total": 0, "progress": 0.0,
}

# ── Math helpers ───────────────────────────────────────────────────────────────
def gauss(mean, sd):
    u, v = 0, 0
    while u == 0: u = random.random()
    while v == 0: v = random.random()
    return mean + sd * math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)

def wait(ms):
    """Sleep interruptibly so pause/stop respond within ~20ms."""
    if ms <= 0: return
    end = time.time() + ms / 1000
    while time.time() < end:
        if stop_flag.is_set() or skip_flag.is_set():
            return
        pause_flag.wait(timeout=0.02)
        time.sleep(0.015)

# ── Context-aware pause ────────────────────────────────────────────────────────
def get_pause(cfg, prev_ch, ch, in_familiar_word=False):
    base_iki = cfg.get("base_iki", 238)
    iki_sd   = cfg.get("iki_sd", 111)
    base = max(30, gauss(base_iki, iki_sd))

    # familiar words are faster
    if in_familiar_word:
        base *= 0.70

    # context multipliers
    if ch in '.!?\n':
        base += gauss(cfg.get("pause_after_punct", 300), 80)
    elif ch == ',':
        base += gauss(cfg.get("pause_after_punct", 300) * 0.45, 40)
    elif ch == ' ':
        base += gauss(cfg.get("pause_after_word", 85), 30)
    elif prev_ch and prev_ch not in ' .,!?\n':
        # within-word acceleration
        base *= 0.82

    return max(25, base)

# ── Low-level type ─────────────────────────────────────────────────────────────
def type_ch(ch):
    if ch == '\n':
        pyautogui.press('enter')
    else:
        pyautogui.typewrite(ch, interval=0)

def backspace_n(cfg, n):
    base = cfg.get("base_iki", 238)
    sd   = cfg.get("iki_sd", 111)
    for _ in range(n):
        if stop_flag.is_set(): return
        pause_flag.wait()
        wait(max(25, gauss(base * 0.72, sd * 0.38)))
        pyautogui.press('backspace')

# ── Word familiarity helper ────────────────────────────────────────────────────
def word_at(text, pos):
    """Return the word the character at `pos` belongs to."""
    start = pos
    while start > 0 and text[start-1] not in ' \n.,!?;:':
        start -= 1
    end = pos
    while end < len(text) and text[end] not in ' \n.,!?;:':
        end += 1
    return text[start:end].lower().strip("'\"")

# ── Main typing engine ─────────────────────────────────────────────────────────
def do_type(text, cfg):
    global state
    stop_flag.clear()
    pause_flag.set()
    skip_flag.clear()

    chars = typos = corrections = 0
    start = time.time()
    state = {
        "state": "typing", "chars": 0, "typos": 0, "corrections": 0,
        "wpm": 0, "total": len(text), "progress": 0.0,
    }

    use_burst       = cfg.get("use_burst", True)
    use_familiarity = cfg.get("use_familiarity", True)
    error_rate      = cfg.get("error_rate", 0.012)
    corr_chance     = cfg.get("corr_chance", 0.80)
    corr_range      = cfg.get("corr_range", 3)

    i = 0
    while i < len(text):
        # ── control flags ──────────────────────────────────────────────────────
        if stop_flag.is_set():
            break

        if skip_flag.is_set():
            # skip to end of current sentence
            while i < len(text) and text[i] not in '.!?\n':
                i += 1
            if i < len(text):
                i += 1  # consume the punctuation
            skip_flag.clear()
            continue

        pause_flag.wait()

        ch      = text[i]
        prev_ch = text[i-1] if i > 0 else ''
        next_ch = text[i+1] if i+1 < len(text) else ''

        # ── word familiarity ───────────────────────────────────────────────────
        in_familiar = use_familiarity and word_at(text, i) in FAMILIAR_WORDS
        familiar_error_mult = 0.4 if in_familiar else 1.0

        # ── burst grouping ─────────────────────────────────────────────────────
        # At word boundaries, randomly decide on a burst size then type quickly
        if use_burst and ch not in ' .,!?\n' and prev_ch in (' ', '', '\n'):
            burst = random.randint(2, 6)
        else:
            burst = 1

        for b in range(burst):
            j = i + b
            if j >= len(text): break
            if text[j] in ' .,!?\n' and b > 0: break  # don't burst across boundaries
            if stop_flag.is_set() or skip_flag.is_set(): break
            pause_flag.wait()

            jch = text[j]
            adj = ADJACENT.get(jch.lower(), [])
            make_typo = bool(adj) and random.random() < error_rate * familiar_error_mult

            wait(get_pause(cfg, text[j-1] if j>0 else '', jch, in_familiar))
            if stop_flag.is_set(): break

            if make_typo:
                typo_ch = random.choice(adj)
                typo_ch = typo_ch.upper() if jch.isupper() else typo_ch
                type_ch(typo_ch)
                typos += 1; chars += 1

                r = random.random()
                if r < corr_chance * 0.4:
                    # immediate backspace correction
                    wait(gauss(cfg.get("base_iki", 238) * 1.2, 50))
                    back_n = min(random.randint(1, corr_range), j + 1)
                    backspace_n(cfg, back_n)
                    corrections += 1
                    for k in range(max(0, j - back_n + 1), j + 1):
                        wait(get_pause(cfg, text[k-1] if k>0 else '', text[k]))
                        type_ch(text[k]); chars += 1

                elif r < corr_chance:
                    # delayed correction — type a few more chars first
                    delay_n = random.randint(1, min(3, len(text) - j - 1))
                    extra_typed = 0
                    for k in range(delay_n):
                        jj = j + 1 + k
                        if jj >= len(text): break
                        if stop_flag.is_set(): break
                        wait(get_pause(cfg, text[jj-1] if jj>0 else '', text[jj]))
                        type_ch(text[jj]); chars += 1; extra_typed += 1

                    wait(gauss(cfg.get("base_iki", 238) * 1.5, 60))
                    backspace_n(cfg, extra_typed + 1)
                    corrections += 1
                    for k in range(j, j + extra_typed + 1):
                        if k >= len(text): break
                        wait(get_pause(cfg, text[k-1] if k>0 else '', text[k]))
                        type_ch(text[k]); chars += 1

                    i += extra_typed  # advance past already-typed chars

                # else: no correction — leave the typo

            else:
                type_ch(jch); chars += 1

            # update state every char
            elapsed = (time.time() - start) / 60
            wpm = round((chars / 5) / elapsed) if elapsed > 0 else 0
            state = {
                "state": "typing", "chars": chars, "typos": typos,
                "corrections": corrections, "wpm": wpm,
                "total": len(text),
                "progress": round(chars / len(text) * 100, 1) if len(text) > 0 else 0,
            }

        # advance by burst amount (minus 1 since loop does i+=1)
        i += burst

    # ── final state ────────────────────────────────────────────────────────────
    elapsed = (time.time() - start) / 60
    wpm = round((chars / 5) / elapsed) if elapsed > 0 else 0
    final = "done" if not stop_flag.is_set() else "stopped"
    state = {
        "state": final, "chars": chars, "typos": typos,
        "corrections": corrections, "wpm": wpm,
        "total": len(text),
        "progress": 100.0 if final == "done" else state.get("progress", 0),
    }

# ── HTTP Handler ───────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST,GET,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        if self.path == "/status":
            self._json(state)
        elif self.path == "/ping":
            self._json({"ok": True, "pyautogui": PYAUTOGUI_OK})
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n)) if n else {}

        if self.path == "/type":
            if not PYAUTOGUI_OK:
                self._json({"ok": False, "error": "pyautogui not installed"}); return
            stop_flag.set(); time.sleep(0.15)
            cfg = data.get("cfg", {})
            # fill defaults
            for k, v in [("base_iki",238),("iki_sd",111),("error_rate",0.012),
                         ("corr_chance",0.80),("corr_range",3),
                         ("pause_after_word",85),("pause_after_punct",300),
                         ("use_burst",True),("use_familiarity",True)]:
                cfg.setdefault(k, v)
            threading.Thread(target=do_type, args=(data["text"], cfg), daemon=True).start()
            self._json({"ok": True})

        elif self.path == "/stop":
            stop_flag.set(); pause_flag.set()
            self._json({"ok": True})

        elif self.path == "/pause":
            pause_flag.clear()
            state["state"] = "paused"
            self._json({"ok": True})

        elif self.path == "/resume":
            pause_flag.set()
            if state.get("state") == "paused":
                state["state"] = "typing"
            self._json({"ok": True})

        elif self.path == "/skip":
            skip_flag.set()
            self._json({"ok": True})

        else:
            self.send_response(404); self.end_headers()

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200); self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers(); self.wfile.write(body)

# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    server = http.server.HTTPServer(("localhost", 7700), Handler)

    def shutdown(sig, frame):
        print("\nShutting down…")
        stop_flag.set(); pause_flag.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("=" * 52)
    print("  HumanTyper Pro — Server v3")
    print("  http://localhost:7700")
    print("  Open HumanTyper.html in Chrome")
    print("  Ctrl+C to stop")
    print("=" * 52)
    server.serve_forever()

if __name__ == "__main__":
    main()
