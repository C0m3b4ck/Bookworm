import tkinter as tk
from tkinter import colorchooser, simpledialog, messagebox
import json
import os

THEMES_FOLDER = "themes"
SETTINGS_FILE = "settings.json"

# Translations for English and Polish
TRANSLATIONS = {
    "EN": {
        "title": "Theme Creator",
        "BTN_BG": "Button Background",
        "BTN_FG": "Button Foreground",
        "BTN_HOVER_BG": "Button Hover Background",
        "BTN_HOVER_FG": "Button Hover Foreground",
        "button_preview": "Button Preview",
        "save_theme": "Save Theme",
        "exit": "Exit",
        "invalid_color_title": "Invalid Color",
        "invalid_color_msg": "Color {key} = '{val}' is not valid!",
        "theme_name_prompt": "Enter a name for your theme:",
        "saved_title": "Saved",
        "saved_msg": "Theme '{name}' saved successfully!",
        "save_error_title": "Error",
        "save_error_msg": "Failed to save theme:\n{error}"
    },
    "PL": {
        "title": "Kreator Motywów",
        "BTN_BG": "Tło Przycisku",
        "BTN_FG": "Kolor Napisu",
        "BTN_HOVER_BG": "Tło Przy Najedzie",
        "BTN_HOVER_FG": "Kolor Napisu Przy Najedzie",
        "button_preview": "Podgląd Przycisku",
        "save_theme": "Zapisz Motyw",
        "exit": "Wyjdź",
        "invalid_color_title": "Nieprawidłowy kolor",
        "invalid_color_msg": "Kolor {key} = '{val}' jest nieprawidłowy!",
        "theme_name_prompt": "Wpisz nazwę dla motywu:",
        "saved_title": "Zapisano",
        "saved_msg": "Motyw '{name}' został zapisany pomyślnie!",
        "save_error_title": "Błąd",
        "save_error_msg": "Nie udało się zapisać motywu:\n{error}"
    }
}


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Default settings if file missing or invalid
    return {"default_language": "EN", "theme": "classic_blue"}


class ThemeCreator(tk.Tk):
    def __init__(self, lang="EN"):
        super().__init__()
        self.lang = lang if lang in TRANSLATIONS else "EN"
        self.texts = TRANSLATIONS[self.lang]
        self.title(self.texts["title"])
        self.geometry("350x360")
        self.resizable(True, True)  # Window resizable

        # Configure grid to allow widgets to expand when resizing
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self.colors = {
            "BTN_BG": "#add8e6",
            "BTN_FG": "#333333",
            "BTN_HOVER_BG": "#6495ed",
            "BTN_HOVER_FG": "#f0f0f0",
        }
        self.create_widgets()
        self.update_preview()

        # Bind to window resize to adjust fonts (optional)
        self.bind("<Configure>", self.on_resize)

    def create_widgets(self):
        row = 0
        self.entries = {}
        # Use a common font for entries and buttons, modifiable
        self.base_font_size = 12
        self.font = ("Segoe UI", self.base_font_size)

        for key in self.colors:
            label_text = self.texts.get(key, key)
            tk.Label(self, text=label_text).grid(row=row, column=0, padx=10, pady=8, sticky='w')
            frame = tk.Frame(self)
            frame.grid(row=row, column=1, padx=10, pady=8, sticky='ew')
            frame.columnconfigure(0, weight=1)

            ent = tk.Entry(frame, width=15, font=self.font)
            ent.insert(0, self.colors[key])
            ent.pack(side='left', fill='x', expand=True)
            btn_color = tk.Button(frame, text="...", width=3,
                                  font=self.font,
                                  command=lambda k=key, e=ent: self.choose_color(k, e))
            btn_color.pack(side='right')
            ent.bind("<KeyRelease>", lambda e, k=key, ent=ent: self.on_color_entry(k, ent))
            self.entries[key] = ent
            row += 1

        self.preview_btn = tk.Button(self, text=self.texts["button_preview"], width=20,
                                     font=(self.font[0], self.base_font_size, "bold"))
        self.preview_btn.grid(row=row, column=0, columnspan=2, pady=15, sticky='ew')
        row += 1

        self.btn_save = tk.Button(self, text=self.texts["save_theme"],
                                  command=self.save_theme,
                                  font=self.font)
        self.btn_save.grid(row=row, column=0, columnspan=2, pady=12, sticky='ew')
        row += 1

        self.btn_exit = tk.Button(self, text=self.texts["exit"],
                                  command=self.destroy,
                                  font=self.font)
        self.btn_exit.grid(row=row, column=0, columnspan=2, pady=10, sticky='ew')

    def choose_color(self, key, entry_widget):
        color = colorchooser.askcolor()[1]
        if color:
            self.colors[key] = color
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, color)
            self.update_preview()

    def on_color_entry(self, key, entry_widget):
        val = entry_widget.get()
        if self.is_valid_color(val):
            self.colors[key] = val
            self.update_preview()

    @staticmethod
    def is_valid_color(color):
        if not color:
            return False
        if color.startswith('#') and (len(color) == 7 or len(color) == 4):
            try:
                int(color[1:], 16)
                return True
            except ValueError:
                return False
        return False

    def update_preview(self):
        self.preview_btn.config(bg=self.colors["BTN_BG"], fg=self.colors["BTN_FG"])

        def on_enter(e):
            e.widget.config(bg=self.colors["BTN_HOVER_BG"], fg=self.colors["BTN_HOVER_FG"])

        def on_leave(e):
            e.widget.config(bg=self.colors["BTN_BG"], fg=self.colors["BTN_FG"])

        self.preview_btn.bind('<Enter>', on_enter)
        self.preview_btn.bind('<Leave>', on_leave)

    def save_theme(self):
        for key, val in self.colors.items():
            if not self.is_valid_color(val):
                messagebox.showerror(
                    self.texts["invalid_color_title"],
                    self.texts["invalid_color_msg"].format(key=key, val=val),
                )
                return
        name = simpledialog.askstring(self.texts["save_theme"], self.texts["theme_name_prompt"])
        if not name:
            return
        if not os.path.exists(THEMES_FOLDER):
            os.makedirs(THEMES_FOLDER)
        filename = os.path.join(THEMES_FOLDER, f"{name}.json")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(self.colors, f, indent=4)
            messagebox.showinfo(
                self.texts["saved_title"],
                self.texts["saved_msg"].format(name=name)
            )
        except Exception as e:
            messagebox.showerror(
                self.texts["save_error_title"],
                self.texts["save_error_msg"].format(error=e)
            )

    def on_resize(self, event):
        # Optionally adjust font size with window width (simple approach)
        new_size = max(8, int(event.width / 25))
        if new_size != self.font[1]:
            self.font = (self.font[0], new_size)
            for ent in self.entries.values():
                ent.config(font=self.font)
            self.preview_btn.config(font=(self.font[0], new_size, "bold"))
            self.btn_save.config(font=self.font)
            self.btn_exit.config(font=self.font)


if __name__ == "__main__":
    settings = load_settings()
    app = ThemeCreator(lang=settings.get("default_language", "EN"))
    app.mainloop()
