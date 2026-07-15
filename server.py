#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ComfyUI 去水印批量处理工具 - 本地服务器"""

import os
import sys
import json
import subprocess
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
import urllib.request

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(TOOL_DIR, "index.html")
CONFIG_FILE = os.path.join(TOOL_DIR, "config.json")
PORT = 8899
COMFYUI_URL = "http://127.0.0.1:8188"


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, content, content_type, code=200):
        if isinstance(content, str):
            content = content.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self._cors()
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", code)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode("utf-8") if length > 0 else ""

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/" or path == "":
            try:
                with open(HTML_FILE, "r", encoding="utf-8") as f:
                    html = f.read()
                self._send(html, "text/html; charset=utf-8")
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif path == "/config":
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        cfg = f.read()
                    self._send(cfg, "application/json; charset=utf-8")
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
            else:
                self._send_json({"comfyui_url": COMFYUI_URL, "comfyui_path": r"E:\AIGC\ComfyUI\ComfyUI-aki-v1.7"})

        elif path == "/check-comfyui":
            qs = parse_qs(parsed.query)
            url = qs.get("url", [COMFYUI_URL])[0]
            try:
                req = urllib.request.Request(f"{url}/system_stats", method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    self._send_json({"online": True, "info": data})
            except Exception as e:
                self._send_json({"online": False, "error": str(e)})

        elif path == "/select-folder":
            self._select_folder()

        elif path == "/proxy":
            qs = parse_qs(parsed.query)
            target_url = qs.get("url", [None])[0]
            if target_url:
                try:
                    req = urllib.request.Request(target_url, method="GET")
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        content = resp.read()
                        ct = resp.headers.get("Content-Type", "application/octet-stream")
                        self._send(content, ct)
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
            else:
                self._send_json({"error": "Missing url parameter"}, 400)

        else:
            # Static file
            file_path = os.path.join(TOOL_DIR, path.lstrip("/"))
            if os.path.isfile(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                ct_map = {
                    ".html": "text/html; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".json": "application/json; charset=utf-8",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".ico": "image/x-icon",
                }
                ct = ct_map.get(ext, "application/octet-stream")
                with open(file_path, "rb") as f:
                    self._send(f.read(), ct)
            else:
                self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/launch-comfyui":
            body = self._read_body()
            data = json.loads(body)
            comfy_path = data.get("path", "")
            launcher = os.path.join(comfy_path, "绘世启动器.exe")

            if os.path.exists(launcher):
                subprocess.Popen([launcher], cwd=comfy_path)
                self._send_json({"success": True, "message": "启动器已运行，请在启动器中点击一键启动"})
            else:
                main_py = os.path.join(comfy_path, "ComfyUI", "main.py")
                python_exe = os.path.join(comfy_path, "python", "python.exe")
                if os.path.exists(main_py):
                    if os.path.exists(python_exe):
                        subprocess.Popen(
                            [python_exe, main_py, "--auto-launch", "--preview-method", "auto",
                             "--use-sage-attention", "--disable-cuda-malloc"],
                            cwd=os.path.join(comfy_path, "ComfyUI")
                        )
                        self._send_json({"success": True, "message": "ComfyUI 正在启动..."})
                    else:
                        self._send_json({"success": False, "error": "找不到 python.exe"})
                else:
                    self._send_json({"success": False, "error": "找不到 main.py"})

        elif path == "/save-image":
            body = self._read_body()
            data = json.loads(body)
            output_dir = data.get("output_dir", "")
            filename = data.get("filename", "result.png")
            image_data = data.get("image_data", "")

            try:
                import base64
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir, exist_ok=True)
                save_path = os.path.join(output_dir, filename)
                img_bytes = base64.b64decode(image_data)
                with open(save_path, "wb") as f:
                    f.write(img_bytes)
                self._send_json({"success": True, "path": save_path})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)

        elif path == "/proxy":
            # Read raw body (bytes) - supports both JSON and multipart/form-data
            length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(length) if length > 0 else b""
            qs = parse_qs(parsed.query)
            target_url = qs.get("url", [None])[0]
            if target_url:
                try:
                    # Forward the original Content-Type header (multipart/form-data or application/json)
                    ct = self.headers.get("Content-Type", "application/json")
                    req = urllib.request.Request(target_url, data=body_bytes,
                                                 method="POST",
                                                 headers={"Content-Type": ct})
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        content = resp.read()
                        resp_ct = resp.headers.get("Content-Type", "application/json")
                        self._send(content, resp_ct)
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
            else:
                self._send_json({"error": "Missing url parameter"}, 400)

        elif path == "/config":
            body = self._read_body()
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(body)
            self._send_json({"success": True})

        else:
            self._send_json({"error": "Not found"}, 404)

    def _select_folder(self):
        """Use tkinter to show folder dialog"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory(title="选择输出目录")
            root.destroy()
            if folder:
                self._send_json({"path": folder})
            else:
                self._send_json({"path": None})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def log_message(self, format, *args):
        pass  # Suppress default logging


def main():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print("=" * 50)
    print("  ComfyUI 去水印批量处理工具")
    print("  本地服务器已启动")
    print(f"  请在浏览器打开: http://127.0.0.1:{PORT}")
    print(f"  ComfyUI地址: {COMFYUI_URL}")
    print("  按 Ctrl+C 停止")
    print("=" * 50)
    print()

    # Auto open browser
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止。")
        server.server_close()


if __name__ == "__main__":
    main()
