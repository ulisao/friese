"""Driver mínimo de Chrome headless por CDP (ver memoria del proyecto).

Tres cosas que ya costaron caro y quedan resueltas acá:
- el handshake del WebSocket de DevTools falla si va con header `Origin`
  (`suppress_origin=True`), y `/json/new` exige PUT: se lanza Chrome con
  `about:blank` y se toma el target `page` de `/json/list`;
- la cámara falsa solo abre UNA vez por sesión salvo que se le pase un `.y4m`;
- se espera SIEMPRE por el elemento que prueba el caso, nunca por un sleep fijo.
"""

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")


def write_fake_camera(path, width=640, height=480, frames=12):
    """Genera un .y4m con un degradado, para que la cámara falsa no dé negro."""
    with open(path, "wb") as fh:
        fh.write(f"YUV4MPEG2 W{width} H{height} F30:1 Ip A1:1 C420\n".encode())
        for n in range(frames):
            fh.write(b"FRAME\n")
            luma = bytearray()
            for y in range(height):
                base = 60 + (y * 120 // height) + n * 3
                luma.extend(bytes(((base + x * 60 // width) % 235 or 16) for x in range(width)))
            fh.write(bytes(luma))
            fh.write(bytes([110] * (width // 2) * (height // 2)))
            fh.write(bytes([140] * (width // 2) * (height // 2)))
    return path


class Browser:
    def __init__(self, mobile=True):
        os.makedirs(SHOTS, exist_ok=True)
        self.profile = tempfile.mkdtemp(prefix="smoke66-chrome-")
        self.video = write_fake_camera(os.path.join(self.profile, "camara.y4m"))
        self.proc = subprocess.Popen([
            CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
            f"--user-data-dir={self.profile}", "--no-first-run", "--no-default-browser-check",
            "--disable-gpu", "--hide-scrollbars", "--window-size=390,844",
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-video-capture={self.video}",
            "--autoplay-policy=no-user-gesture-required", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        ws_url, deadline = None, time.time() + 30
        while time.time() < deadline and not ws_url:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=2) as r:
                    for t in json.loads(r.read().decode()):
                        if t.get("type") == "page":
                            ws_url = t["webSocketDebuggerUrl"]
                            break
            except Exception:
                time.sleep(0.3)
        if not ws_url:
            raise RuntimeError("no se pudo conectar a Chrome por CDP")

        self.ws = websocket.create_connection(ws_url, suppress_origin=True, timeout=60)
        self._id = 0
        # Los eventos que llegan mientras se espera una respuesta se guardan acá:
        # sirven para leer los errores de la consola (p. ej. las violaciones de CSP,
        # que el navegador reporta ahí y no rompen la página).
        self.eventos = []
        self.send("Page.enable")
        self.send("Runtime.enable")
        self.send("Log.enable")
        if mobile:
            self.send("Emulation.setDeviceMetricsOverride", {
                "width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True,
            })

    def send(self, method, params=None):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            if msg.get("method") in ("Log.entryAdded", "Runtime.consoleAPICalled"):
                self.eventos.append(msg)

    def errores_de_consola(self):
        """Mensajes de error de la consola (incluidas las violaciones de CSP)."""
        salida = []
        for evento in self.eventos:
            params = evento.get("params", {})
            entrada = params.get("entry", {})
            if entrada.get("level") == "error":
                salida.append(entrada.get("text", ""))
            elif params.get("type") == "error":
                salida.append(" ".join(
                    str(arg.get("value", "")) for arg in params.get("args", [])))
        return salida

    def js(self, expression):
        res = self.send("Runtime.evaluate", {
            "expression": expression, "awaitPromise": True, "returnByValue": True,
        })
        if res.get("exceptionDetails"):
            raise RuntimeError(f"JS: {res['exceptionDetails'].get('text')} :: {expression[:120]}")
        return res.get("result", {}).get("value")

    def goto(self, url):
        self.send("Page.navigate", {"url": url})
        self.wait("document.readyState === 'complete'", label=f"carga de {url}")

    def wait(self, expression, timeout=45, label=""):
        """Espera a que una expresión JS sea verdadera. Nunca un sleep fijo."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.js(f"!!({expression})"):
                    return True
            except RuntimeError:
                pass
            time.sleep(0.25)
        raise TimeoutError(f"timeout esperando {label or expression}")

    def click(self, selector):
        self.wait(f"document.querySelector({selector!r})", label=f"click en {selector}")
        self.js(f"document.querySelector({selector!r}).click()")

    def click_js(self, expression, label=""):
        """Clic sobre el elemento que devuelve una expresión JS (cuando no alcanza
        un selector CSS: p. ej. distinguir el link de una card del de «Nuevo remito»)."""
        self.wait(expression, label=label or expression)
        self.js(f"({expression}).click()")

    def fill(self, selector, value):
        """Escribe en un input controlado por React (setter nativo + evento input)."""
        self.wait(f"document.querySelector({selector!r})", label=f"input {selector}")
        self.js(f"""(() => {{
            const el = document.querySelector({selector!r});
            const proto = el.tagName === 'TEXTAREA'
                ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
            Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, {value!r});
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            return true;
        }})()""")

    def text(self, selector):
        return self.js(f"(document.querySelector({selector!r}) || {{}}).innerText || ''")

    def shot(self, name):
        path = os.path.join(SHOTS, f"{name}.png")
        data = self.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(data["data"]))
        print(f"    captura: smoke_tests/shots/{name}.png")
        return path

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)
