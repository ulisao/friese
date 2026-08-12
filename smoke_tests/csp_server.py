"""Sirve el build de producción del frontend con la CSP real de vercel.json.

Además proxea /api al Django local, para que el navegador vea la app y la API en
el MISMO origen. Eso reproduce lo que va a pasar en producción con
app.friese.com.ar + api.friese.com.ar (que son orígenes distintos pero del mismo
SITIO, así que la cookie SameSite=Lax viaja igual), y permite probar de una sola
vez la cookie httpOnly y la CSP.
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(BASE_DIR, "frontend", "dist")
BACKEND = "http://127.0.0.1:8000"

with open(os.path.join(BASE_DIR, "frontend", "vercel.json"), encoding="utf-8") as fh:
    CABECERAS = {
        h["key"]: h["value"]
        for bloque in json.load(fh)["headers"]
        for h in bloque["headers"]
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST, **kwargs)

    def log_message(self, *args):
        pass

    def _proxy(self, cuerpo=None):
        url = BACKEND + self.path
        pedido = urllib.request.Request(url, data=cuerpo, method=self.command)
        for nombre in ("Content-Type", "Authorization", "Cookie", "Origin", "Referer"):
            if nombre in self.headers:
                pedido.add_header(nombre, self.headers[nombre])
        try:
            with urllib.request.urlopen(pedido, timeout=120) as respuesta:
                self.send_response(respuesta.status)
                for clave, valor in respuesta.getheaders():
                    if clave.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(clave, valor)
                self.end_headers()
                self.wfile.write(respuesta.read())
        except urllib.error.HTTPError as error:
            self.send_response(error.code)
            for clave, valor in error.headers.items():
                if clave.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(clave, valor)
            self.end_headers()
            self.wfile.write(error.read())

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        # Fallback del SPA: cualquier ruta que no sea un archivo va al index.
        ruta = self.path.split("?", 1)[0]
        if not os.path.isfile(os.path.join(DIST, ruta.lstrip("/"))):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        largo = int(self.headers.get("Content-Length") or 0)
        return self._proxy(self.rfile.read(largo) if largo else None)

    do_PATCH = do_PUT = do_DELETE = do_POST

    def end_headers(self):
        for clave, valor in CABECERAS.items():
            self.send_header(clave, valor)
        super().end_headers()


def servir(puerto=5174):
    servidor = HTTPServer(("127.0.0.1", puerto), Handler)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    return servidor


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 5174
    print(f"sirviendo {DIST} en http://127.0.0.1:{puerto} con la CSP de vercel.json")
    servir(puerto)
    threading.Event().wait()
