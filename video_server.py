"""
视频水印批量裁剪工具
- 裁剪左上角和/或右下角水印区域
- 基于 FFmpeg crop 滤镜
- Web UI 批量处理
"""
import os
import sys
import json
import subprocess
import hashlib
import shutil
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.parse

DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(DIR, "config.json")

DEFAULT_CONFIG = {
    "crop_top": 0,
    "crop_bottom": 70,
    "crop_left": 0,
    "crop_right": 0,
    "crf": 18,
    "preset": "medium"
}

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # Merge with defaults
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def get_video_info(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
            capture_output=True, text=True, timeout=10
        )
        info = json.loads(result.stdout)
        for s in info.get("streams", []):
            if s.get("codec_type") == "video":
                return {
                    "width": int(s["width"]),
                    "height": int(s["height"]),
                    "duration": float(s.get("duration", 0))
                }
    except Exception as e:
        print(f"ffprobe error: {e}")
    return None

def process_video(input_path, output_path, crop_top, crop_bottom, crop_left, crop_right, crf, preset, progress_cb=None):
    """Crop watermark areas from video."""
    info = get_video_info(input_path)
    if not info:
        return False, "Failed to read video info"

    w, h = info["width"], info["height"]
    
    # Validate crop values
    crop_top = max(0, crop_top)
    crop_bottom = max(0, crop_bottom)
    crop_left = max(0, crop_left)
    crop_right = max(0, crop_right)
    
    new_w = w - crop_left - crop_right
    new_h = h - crop_top - crop_bottom
    
    if new_w < 2 or new_h < 2:
        return False, f"Crop too large: {w}x{h} -> {new_w}x{new_h}"
    
    # Build crop filter: crop=new_w:new_h:crop_left:crop_top
    vf = f"crop={new_w}:{new_h}:{crop_left}:{crop_top}"
    
    # If we need even dimensions for x264, adjust
    if new_w % 2 != 0:
        new_w -= 1
    if new_h % 2 != 0:
        new_h -= 1
    vf = f"crop={new_w}:{new_h}:{crop_left}:{crop_top}"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path
    ]

    print(f"Running: {' '.join(cmd)}")
    print(f"Crop: {w}x{h} -> {new_w}x{new_h} (top={crop_top} bottom={crop_bottom} left={crop_left} right={crop_right})")

    proc = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

    duration = info["duration"]
    last_progress = -1

    for line in proc.stderr:
        if progress_cb and "time=" in line:
            try:
                time_str = line.split("time=")[1].split(" ")[0]
                t = sum(float(x) * 60 ** i for i, x in enumerate(reversed(time_str.split(":"))))
                pct = min(100, int(t / duration * 100)) if duration > 0 else 0
                if pct != last_progress:
                    last_progress = pct
                    progress_cb(pct)
            except:
                pass

    proc.wait()
    if proc.returncode == 0:
        return True, f"{w}x{h} -> {new_w}x{new_h}"
    else:
        return False, f"FFmpeg exited with code {proc.returncode}"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/config":
            self._json(load_config())
            return
        if path == "/api/ffmpeg-check":
            try:
                r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
                if r.returncode == 0:
                    ver = r.stdout.split("\n")[0]
                    self._json({"ok": True, "version": ver})
                else:
                    self._json({"ok": False, "error": "ffmpeg not found"})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
            return
        super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/config":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                cfg = json.loads(body)
                save_config(cfg)
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if path == "/api/process":
            ct = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ct:
                self._json({"error": "Expected multipart/form-data"}, 400)
                return

            boundary = ct.split("boundary=")[1].encode()
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            parts = body.split(b"--" + boundary)

            files = []
            output_dir = ""
            crf = 18
            preset = "medium"
            crop_top = 0
            crop_bottom = 70
            crop_left = 0
            crop_right = 0

            for part in parts:
                if b"Content-Disposition" not in part:
                    continue
                header_end = part.find(b"\r\n\r\n")
                if header_end < 0:
                    continue
                header = part[:header_end].decode("utf-8", errors="replace")
                content = part[header_end + 4:]
                if content.endswith(b"\r\n"):
                    content = content[:-2]

                if 'name="files"' in header:
                    fname = "video"
                    for seg in header.split(";"):
                        seg = seg.strip()
                        if seg.startswith("filename="):
                            fname = seg.split("=", 1)[1].strip('"')
                    files.append((fname, content))
                elif 'name="outputDir"' in header:
                    output_dir = content.decode("utf-8", errors="replace").strip()
                elif 'name="crf"' in header:
                    crf = int(content.decode("utf-8", errors="replace").strip() or "18")
                elif 'name="preset"' in header:
                    preset = content.decode("utf-8", errors="replace").strip() or "medium"
                elif 'name="crop_top"' in header:
                    crop_top = int(content.decode("utf-8", errors="replace").strip() or "0")
                elif 'name="crop_bottom"' in header:
                    crop_bottom = int(content.decode("utf-8", errors="replace").strip() or "0")
                elif 'name="crop_left"' in header:
                    crop_left = int(content.decode("utf-8", errors="replace").strip() or "0")
                elif 'name="crop_right"' in header:
                    crop_right = int(content.decode("utf-8", errors="replace").strip() or "0")

            if not files:
                self._json({"error": "No files uploaded"}, 400)
                return

            if output_dir:
                out_dir = os.path.abspath(output_dir)
            else:
                out_dir = os.path.join(DIR, "output")
            os.makedirs(out_dir, exist_ok=True)

            results = []
            for fname, fdata in files:
                tmp_id = hashlib.md5(fname.encode()).hexdigest()[:8]
                ext = os.path.splitext(fname)[1] or ".mp4"
                tmp_in = os.path.join(DIR, f"_tmp_input_{tmp_id}{ext}")
                with open(tmp_in, "wb") as f:
                    f.write(fdata)

                base = os.path.splitext(fname)[0]
                out_path = os.path.join(out_dir, f"{base}_nowm.mp4")

                ok, msg = process_video(tmp_in, out_path, crop_top, crop_bottom, crop_left, crop_right, crf, preset)

                try:
                    os.remove(tmp_in)
                except:
                    pass

                if ok:
                    results.append({
                        "name": fname,
                        "output": f"{base}_nowm.mp4",
                        "savedPath": out_path,
                        "info": msg,
                        "status": "ok"
                    })
                else:
                    results.append({
                        "name": fname,
                        "status": "error",
                        "error": msg
                    })

            self._json({"results": results})
            return

        self._json({"error": "Not found"}, 404)

    def log_message(self, fmt, *args):
        pass


def main():
    port = 7891
    print(f"视频去水印裁剪工具启动中... http://localhost:{port}")
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"✅ 服务运行在 http://localhost:{port}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止服务")
        server.shutdown()


if __name__ == "__main__":
    main()
