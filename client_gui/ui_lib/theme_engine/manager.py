import json
import os
from pathlib import Path

class ThemeManager:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.settings_path = self.config_dir / "theme_settings.json"
        self.presets_path = self.config_dir / "user_presets.json"
        
        # 擴充至 20 組預設主題
        self.default_themes = {
            # --- 經典深色系 ---
            "SATIN Dark": {"bg": "#1e1e1e", "panel": "#2d2d2d", "text": "#ffffff", "accent": "#007acc", "border": "#3e3e42"},
            "Midnight Blue": {"bg": "#0d1117", "panel": "#161b22", "text": "#c9d1d9", "accent": "#58a6ff", "border": "#30363d"},
            "Deep Space": {"bg": "#10101a", "panel": "#1a1a2e", "text": "#e0e0e0", "accent": "#0f3460", "border": "#16213e"},
            "Charcoal": {"bg": "#121212", "panel": "#1e1e1e", "text": "#f5f5f5", "accent": "#bb86fc", "border": "#333333"},
            
            # --- 自然與護眼系 ---
            "Forest Green": {"bg": "#1b2b1b", "panel": "#263d26", "text": "#e0e0e0", "accent": "#4caf50", "border": "#2e4d2e"},
            "Sepia Eye-Care": {"bg": "#f4ecd8", "panel": "#e8dfc4", "text": "#5b4636", "accent": "#8d6e63", "border": "#d7ccc8"},
            "Ocean Deep": {"bg": "#0f172a", "panel": "#1e293b", "text": "#f8fafc", "accent": "#38bdf8", "border": "#334155"},
            "Earth Tone": {"bg": "#3c3f41", "panel": "#4b5052", "text": "#dfdfdf", "accent": "#a97d5d", "border": "#54595b"},
            
            # --- 程式碼編輯器經典系 ---
            "Dracula": {"bg": "#282a36", "panel": "#44475a", "text": "#f8f8f2", "accent": "#bd93f9", "border": "#6272a4"},
            "Nord": {"bg": "#2e3440", "panel": "#3b4252", "text": "#d8dee9", "accent": "#88c0d0", "border": "#4c566a"},
            "Monokai": {"bg": "#272822", "panel": "#3e3d32", "text": "#f8f8f2", "accent": "#a6e22e", "border": "#49483e"},
            "One Dark": {"bg": "#282c34", "panel": "#21252b", "text": "#abb2bf", "accent": "#61afef", "border": "#3e4451"},
            "Gruvbox": {"bg": "#282828", "panel": "#3c3836", "text": "#ebdbb2", "accent": "#fabd2f", "border": "#504945"},
            
            # --- 明亮與簡潔系 ---
            "SATIN Light": {"bg": "#f3f3f3", "panel": "#ffffff", "text": "#333333", "accent": "#007acc", "border": "#dcdcdc"},
            "Paper White": {"bg": "#ffffff", "panel": "#f8f9fa", "text": "#202124", "accent": "#1a73e8", "border": "#dadce0"},
            "Lavender": {"bg": "#f5f3ff", "panel": "#ede9fe", "text": "#4c1d95", "accent": "#8b5cf6", "border": "#ddd6fe"},
            
            # --- 高對比與個性化 ---
            "Cyberpunk": {"bg": "#000000", "panel": "#1a1a1a", "text": "#00ff00", "accent": "#f0db4f", "border": "#333333"},
            "Neon Night": {"bg": "#0b0e14", "panel": "#151a24", "text": "#ffffff", "accent": "#ff007c", "border": "#2d333f"},
            "Crimson Red": {"bg": "#1a0000", "panel": "#330000", "text": "#ffebeb", "accent": "#ff4d4d", "border": "#4d0000"},
            "Slate Pro": {"bg": "#0f172a", "panel": "#1e293b", "text": "#94a3b8", "accent": "#64748b", "border": "#334155"}
        }
        
        self.user_presets = self._load_json(self.presets_path, {})
        self.settings = self._load_json(self.settings_path, {"current": "SATIN Dark"})
        
    def _load_json(self, path, default):
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: return default
        return default

    @property
    def current_theme_name(self):
        return self.settings.get("current", "SATIN Dark")

    @property
    def current_theme(self):
        return self.all_themes.get(self.current_theme_name, self.default_themes["SATIN Dark"])

    @property
    def all_themes(self):
        # 合併預設與使用者自定義主題
        return {**self.default_themes, **self.user_presets}

    def save_current(self, name):
        self.settings["current"] = name
        with open(self.settings_path, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=4)

    def add_user_preset(self, name, theme_dict):
        self.user_presets[name] = theme_dict
        with open(self.presets_path, 'w', encoding='utf-8') as f:
            json.dump(self.user_presets, f, indent=4, ensure_ascii=False)