import http.server
import socketserver
import os
import urllib

PORT = 8000
SERVE_DIR = "/Users/domingo/⭐️ Documentación"

class HTMLOnlyRequestHandler(http.server.SimpleHTTPRequestHandler):
    def list_directory(self, path):
        try:
            entries = os.listdir(path)
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None

        entries.sort()
        r = []
        displaypath = urllib.parse.unquote(self.path)
        r.append(f"<html><head><title>Index of {displaypath}</title></head>")
        r.append(f"<body><h2>Index of {displaypath}</h2><hr><ul>")

        # Añade enlace para volver atrás
        if displaypath != "/":
            parent = os.path.dirname(displaypath.rstrip("/"))
            r.append(f'<li><a href="{parent or "/"}">../</a></li>')

        for name in entries:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            if os.path.isdir(fullname):
                # añade subdirectorio (con barra final)
                displayname = name + "/"
                linkname = name + "/"
                r.append(f'<li><a href="{linkname}">{displayname}</a></li>')
            elif name.endswith(".html"):
                r.append(f'<li><a href="{linkname}">{displayname}</a></li>')

        r.append("</ul><hr></body></html>")
        encoded = "\n".join(r).encode("utf-8", "surrogateescape")
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
        return None

    def translate_path(self, path):
        # Traducir URL a ruta absoluta dentro de SERVE_DIR
        path = urllib.parse.unquote(path)
        path = path.lstrip("/")
        return os.path.join(SERVE_DIR, *path.split("/"))

os.chdir(SERVE_DIR)

with socketserver.TCPServer(("", PORT), HTMLOnlyRequestHandler) as httpd:
    print(f"Serving ONLY .html files (and folders) from: {SERVE_DIR}")
    print(f"Access at: http://localhost:{PORT}")
    httpd.serve_forever()