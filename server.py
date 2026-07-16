"""
Watermark Remover Batch Tool - Local Server
Simple Python HTTP server for batch watermark removal via browser.
No ComfyUI needed - just PIL cropping.
"""
import http.server
import socketserver
import json
import os
import io
import threading
from PIL import Image

PORT = 7890
DIR = os.path.dirname(os.path.abspath(__file__))

class WatermarkHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)
    
    def do_POST(self):
        if self.path == "/process":
            self._handle_process()
        else:
            self.send_error(404)
    
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        route = parsed.path

        if route == '/listdirs':
            params = parse_qs(parsed.query)
            dir_path = params.get('path', [''])[0]
            self._handle_list_dirs(dir_path)
        else:
            # 默认静态文件伺服
            super().do_GET()
    
    def _handle_list_dirs(self, dir_path):
        """列出指定目录下的子目录"""
        if not dir_path:
            self._json_response({"success": False, "error": "缺少路径"})
            return
        try:
            dir_path = os.path.abspath(dir_path)
            if not os.path.isdir(dir_path):
                self._json_response({"success": False, "error": "目录不存在"})
                return
            dirs = sorted([
                d for d in os.listdir(dir_path)
                if os.path.isdir(os.path.join(dir_path, d)) and not d.startswith('.')
            ])
            self._json_response({"success": True, "dirs": dirs})
        except Exception as e:
            self._json_response({"success": False, "error": str(e)})
    
    def _handle_process(self):
        content_type = self.headers.get("Content-Type", "")
        
        if not content_type.startswith("multipart/form-data"):
            self.send_error(400, "Expected multipart/form-data")
            return
        
        # Parse multipart form data
        try:
            form = self._parse_multipart()
        except Exception as e:
            self.send_error(400, f"Parse error: {e}")
            return
        
        files = form.get("files", [])
        crop_height = int(form.get("cropHeight", ["150"])[0])
        output_format = form.get("format", ["png"])[0]
        output_dir = form.get("outputDir", [""])[0] if "outputDir" in form else ""
        
        if not files:
            self._json_response({"error": "No files provided"})
            return
        
        # Validate and prepare output directory
        # If no output_dir specified, use default 'output' subdirectory
        if output_dir:
            output_dir = os.path.abspath(output_dir)
        else:
            output_dir = os.path.join(DIR, "output")
        os.makedirs(output_dir, exist_ok=True)
        
        results = []
        for filename, filedata in files:
            try:
                img = Image.open(io.BytesIO(filedata))
                w, h = img.size
                
                if crop_height >= h:
                    results.append({"name": filename, "error": "Image too small to crop"})
                    continue
                
                # Crop bottom strip
                result = img.crop((0, 0, w, h - crop_height))
                
                # Convert to output format
                out_buf = io.BytesIO()
                if output_format == "jpeg":
                    if result.mode in ("RGBA", "P"):
                        result = result.convert("RGB")
                    result.save(out_buf, format="JPEG", quality=95)
                    mime = "image/jpeg"
                    ext = ".jpg"
                else:
                    result.save(out_buf, format="PNG")
                    mime = "image/png"
                    ext = ".png"
                
                out_bytes = out_buf.getvalue()
                import base64
                out_b64_str = base64.b64encode(out_bytes).decode("ascii")
                
                base = os.path.splitext(filename)[0]
                out_name = f"{base}_nowm{ext}"
                
                # Save to output directory (always save)
                saved_path = os.path.join(output_dir, out_name)
                with open(saved_path, "wb") as f:
                    f.write(out_bytes)
                
                results.append({
                    "name": out_name,
                    "originalSize": f"{w}x{h}",
                    "newSize": f"{w}x{h - crop_height}",
                    "data": f"data:{mime};base64,{out_b64_str}",
                    "savedPath": saved_path
                })
                
            except Exception as e:
                results.append({"name": filename, "error": str(e)})
        
        self._json_response({"results": results})
    
    def _parse_multipart(self):
        """Simple multipart/form-data parser."""
        content_type = self.headers.get("Content-Type", "")
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[len("boundary="):]
                break
        
        if not boundary:
            raise ValueError("No boundary found")
        
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        boundary_bytes = ("--" + boundary).encode()
        parts = body.split(boundary_bytes)
        
        form = {"files": []}
        
        for part in parts:
            part = part.strip()
            if not part or part == b"--" or part == b"--\r\n":
                continue
            
            # Split headers and content
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            
            header_str = part[:header_end].decode("utf-8", errors="replace")
            content = part[header_end + 4:]
            
            # Remove trailing \r\n
            if content.endswith(b"\r\n"):
                content = content[:-2]
            
            # Parse headers
            field_name = None
            filename = None
            for line in header_str.split("\r\n"):
                if line.lower().startswith("content-disposition:"):
                    for item in line.split(";"):
                        item = item.strip()
                        if item.startswith("name="):
                            field_name = item[5:].strip('"')
                        elif item.startswith("filename="):
                            filename = item[9:].strip('"')
            
            if field_name == "files" and filename:
                form["files"].append((filename, content))
            elif field_name:
                if field_name not in form:
                    form[field_name] = []
                form[field_name].append(content.decode("utf-8", errors="replace"))
        
        return form
    
    def _json_response(self, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass


def main():
    os.chdir(DIR)
    
    with socketserver.ThreadingTCPServer(("", PORT), WatermarkHandler) as httpd:
        print(f"去水印工具服务器已启动: http://localhost:{PORT}")
        print(f"按 Ctrl+C 停止")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止")


if __name__ == "__main__":
    main()
