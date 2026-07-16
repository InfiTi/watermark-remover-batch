"""
Watermark Remover - Crop Method
Crops the bottom strip containing the "豆包AI生成" watermark.
No AI needed - just PIL. Clean and simple.

Watermark is at bottom-right corner, roughly 280x130px area.
Since it's on background/blank area, cropping the bottom strip
removes it completely without affecting the main subject.
"""
from PIL import Image, ImageDraw
import os
import sys
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading

# ===== Config =====
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "watermark_height": 150,          # pixels to crop from bottom (watermark height + padding)
    "output_suffix": "_nowm",
    "output_dir": "",
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # Merge with defaults
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def remove_watermark(img, cfg):
    """
    Remove watermark by cropping the bottom strip.
    The watermark "豆包AI生成" sits at the bottom-right corner.
    Cropping the bottom ~150px removes it cleanly.
    """
    w, h = img.size
    crop_bottom = cfg.get("watermark_height", 150)
    
    if crop_bottom >= h:
        return img  # Don't crop if image is too small
    
    result = img.crop((0, 0, w, h - crop_bottom))
    return result


class WatermarkRemoverApp:
    def __init__(self, root):
        self.root = root
        self.root.title("去水印工具 - 裁剪填充法")
        self.root.geometry("900x700")
        self.root.configure(bg="#1a1a2e")
        
        self.cfg = load_config()
        self.tasks = []
        self.is_processing = False
        
        self._build_ui()
    
    def _build_ui(self):
        style = {"bg": "#1a1a2e", "fg": "#e0e0e0", "font": ("Microsoft YaHei UI", 10)}
        btn_style = {**style, "bg": "#16213e", "fg": "#e0e0e0", "activebackground": "#0f3460", "relief": "flat", "font": ("Microsoft YaHei UI", 10, "bold")}
        entry_style = {**style, "bg": "#16213e", "fg": "#e0e0e0", "insertbackground": "#e0e0e0", "relief": "flat"}
        
        # Title
        tk.Label(self.root, text="✂️ 去水印工具（裁剪法）", font=("Microsoft YaHei UI", 16, "bold"), bg="#1a1a2e", fg="#e0e0e0").pack(pady=10)
        
        # Config frame
        cfg_frame = tk.Frame(self.root, bg="#1a1a2e")
        cfg_frame.pack(fill="x", padx=20, pady=5)
        
        # Watermark region params
        param_frame = tk.LabelFrame(cfg_frame, text="裁剪设置", font=("Microsoft YaHei UI", 10, "bold"), bg="#1a1a2e", fg="#e0e0e0")
        param_frame.pack(fill="x", pady=5)
        
        row = tk.Frame(param_frame, bg="#1a1a2e")
        row.pack(fill="x", padx=10, pady=5)
        tk.Label(row, text="底部裁剪高度（像素）:", bg="#1a1a2e", fg="#e0e0e0", font=("Microsoft YaHei UI", 10)).pack(side="left")
        self.e_crop = tk.Entry(row, width=8, bg="#16213e", fg="#e0e0e0", insertbackground="#e0e0e0", relief="flat")
        self.e_crop.insert(0, str(self.cfg.get("watermark_height", 150)))
        self.e_crop.pack(side="left", padx=5)
        tk.Label(row, text="（默认150，水印「豆包AI生成」在右下角）", bg="#1a1a2e", fg="#888", font=("Microsoft YaHei UI", 9)).pack(side="left")
        
        # Output dir
        out_frame = tk.Frame(cfg_frame, bg="#1a1a2e")
        out_frame.pack(fill="x", pady=5)
        tk.Label(out_frame, text="输出目录:", bg="#1a1a2e", fg="#e0e0e0", font=("Microsoft YaHei UI", 10)).pack(side="left")
        self.e_out = tk.Entry(out_frame, **entry_style)
        self.e_out.insert(0, self.cfg["output_dir"])
        self.e_out.pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(out_frame, text="浏览", command=self.browse_out, bg="#16213e", fg="#e0e0e0", activebackground="#0f3460", relief="flat", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        
        # Buttons
        btn_frame = tk.Frame(self.root, bg="#1a1a2e")
        btn_frame.pack(fill="x", padx=20, pady=10)
        tk.Button(btn_frame, text="📁 添加图片", command=self.add_images, bg="#16213e", fg="#e0e0e0", activebackground="#0f3460", relief="flat", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=5)
        tk.Button(btn_frame, text="▶️ 开始处理", command=self.start_process, bg="#16213e", fg="#e0e0e0", activebackground="#0f3460", relief="flat", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=5)
        tk.Button(btn_frame, text="🗑️ 清空列表", command=self.clear_list, bg="#16213e", fg="#e0e0e0", activebackground="#0f3460", relief="flat", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=5)
        
        # Progress
        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", padx=20, pady=5)
        self.status_label = tk.Label(self.root, text="就绪", bg="#1a1a2e", fg="#e0e0e0", font=("Microsoft YaHei UI", 10))
        self.status_label.pack(pady=2)
        
        # Task list
        list_frame = tk.Frame(self.root, bg="#1a1a2e")
        list_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        cols = ("file", "status", "result")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=15)
        self.tree.heading("file", text="文件名")
        self.tree.heading("status", text="状态")
        self.tree.heading("result", text="结果")
        self.tree.column("file", width=350)
        self.tree.column("status", width=100)
        self.tree.column("result", width=300)
        self.tree.pack(fill="both", expand=True)
        
        # Drag and drop
        self.root.drop_target_register = None  # Would need tkinterdnd2
        
    def browse_out(self):
        d = filedialog.askdirectory()
        if d:
            self.e_out.delete(0, tk.END)
            self.e_out.insert(0, d)
    
    def add_images(self):
        files = filedialog.askopenfilenames(
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.webp")]
        )
        for f in files:
            self.tasks.append({"file": f, "status": "pending", "result": ""})
            self.tree.insert("", "end", values=(os.path.basename(f), "待处理", ""))
        self.status_label.config(text=f"已添加 {len(self.tasks)} 张图片")
    
    def clear_list(self):
        self.tasks.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.progress.config(value=0)
        self.status_label.config(text="已清空")
    
    def start_process(self):
        if self.is_processing:
            return
        if not self.tasks:
            messagebox.showinfo("提示", "请先添加图片")
            return
        
        # Save config
        self.cfg["watermark_height"] = int(self.e_crop.get())
        self.cfg["output_dir"] = self.e_out.get()
        save_config(self.cfg)
        
        self.is_processing = True
        threading.Thread(target=self._process_all, daemon=True).start()
    
    def _process_all(self):
        total = len(self.tasks)
        self.progress.config(maximum=total, value=0)
        
        out_dir = self.cfg["output_dir"]
        suffix = self.cfg["output_suffix"]
        
        for i, task in enumerate(self.tasks):
            if task["status"] == "done":
                continue
            
            item_id = self.tree.get_children()[i]
            self.tree.set(item_id, "status", "处理中...")
            self.status_label.config(text=f"处理中: {os.path.basename(task['file'])} ({i+1}/{total})")
            
            try:
                img = Image.open(task["file"])
                result = remove_watermark(img, self.cfg)
                
                # Save
                base, ext = os.path.splitext(os.path.basename(task["file"]))
                out_name = f"{base}{suffix}{ext}"
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                    out_path = os.path.join(out_dir, out_name)
                else:
                    out_path = os.path.join(os.path.dirname(task["file"]), out_name)
                
                result.save(out_path)
                
                task["status"] = "done"
                task["result"] = out_path
                self.tree.set(item_id, "status", "✅ 完成")
                self.tree.set(item_id, "result", out_name)
                
            except Exception as e:
                task["status"] = "error"
                task["result"] = str(e)
                self.tree.set(item_id, "status", "❌ 错误")
                self.tree.set(item_id, "result", str(e))
            
            self.progress.config(value=i + 1)
        
        self.is_processing = False
        self.status_label.config(text=f"完成！共处理 {total} 张图片")


if __name__ == "__main__":
    root = tk.Tk()
    app = WatermarkRemoverApp(root)
    root.mainloop()
