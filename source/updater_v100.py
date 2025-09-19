import os
import re
import requests
import tkinter as tk
import json

THEMES_FOLDER = "themes"
SETTINGS_FILE = "settings.json"
DOWNLOAD_TIMEOUT = 15  # seconds

TRANSLATIONS = {
    "EN": {
        "title": "Updater",
        "check_version": "Check Version",
        "exit_program": "Exit Program",
        "local_version": "Local version: {}",
        "latest_version": "Latest GitHub release: {}",
        "cannot_determine_local": "Could not determine local version from executable filename.\nExpected *_vXYZ.exe format.",
        "cannot_fetch_latest": "Could not fetch latest version from GitHub.",
        "update_available": "Update available! Downloading...",
        "no_update": "You have the latest version.",
        "download_failed": "Download failed: {}",
        "download_success": "Downloaded new version successfully.",
        "remove_old_failed": "Failed to remove old executable: {}",
        "removed_old": "Removed old executable: {}",
        "checking": "Checking versions...",
    },
    "PL": {
        "title": "Aktualizator",
        "check_version": "Sprawdź Wersję",
        "exit_program": "Zamknij Program",
        "local_version": "Lokalna wersja: {}",
        "latest_version": "Najnowsza wersja GitHub: {}",
        "cannot_determine_local": "Nie można określić lokalnej wersji z nazwy pliku.\nOczekiwano formatu *_vXYZ.exe.",
        "cannot_fetch_latest": "Nie można pobrać najnowszej wersji z GitHub.",
        "update_available": "Dostępna aktualizacja! Pobieranie...",
        "no_update": "Posiadasz najnowszą wersję.",
        "download_failed": "Pobieranie nieudane: {}",
        "download_success": "Nowa wersja została pobrana pomyślnie.",
        "remove_old_failed": "Nie udało się usunąć starego pliku: {}",
        "removed_old": "Usunięto stary plik: {}",
        "checking": "Sprawdzanie wersji...",
    },
}

def parse_version_from_filename(filename):
    m = re.search(r'_v(\d+)\.exe$', filename, re.IGNORECASE)
    if m:
        num = m.group(1)
        if len(num) == 3:
            return f"{int(num[0])}.{int(num[1])}.{int(num[2])}"
        elif len(num) == 2:
            return f"{int(num[0])}.{int(num[1])}.0"
        elif len(num) == 1:
            return f"0.{int(num[0])}.0"
    return None

def get_local_executable_and_version():
    for fname in os.listdir('.'):
        if fname.lower().endswith('.exe') and '_v' in fname.lower():
            ver = parse_version_from_filename(fname)
            if ver:
                return fname, ver
    return None, None

def get_latest_github_version_and_asset_url():
    url = "https://api.github.com/repos/C0m3b4ck/Bookworm/releases/latest"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        tag_name = data.get('tag_name', '')
        m = re.match(r'version_(\d+\.\d+\.\d+)', tag_name)
        if m:
            version = m.group(1)
            assets = data.get('assets', [])
            for asset in assets:
                if asset['name'].lower().endswith('.exe'):
                    return version, asset['browser_download_url']
    except Exception as e:
        print(f"Error checking latest GitHub release: {e}")
    return None, None

def version_tuple(v):
    return tuple(int(x) for x in v.split('.'))

class UpdaterApp(tk.Tk):
    def __init__(self, lang="EN"):
        super().__init__()
        self.lang = lang if lang in TRANSLATIONS else "EN"
        self.texts = TRANSLATIONS[self.lang]
        self.title(self.texts["title"])
        self.geometry("440x230")
        self.resizable(False, False)
        self.local_exe = None
        self.local_ver = None
        self.latest_ver = None
        self.latest_url = None

        self.status_label = tk.Label(self, text="", justify="left")
        self.status_label.pack(pady=15, padx=15, fill="x")

        self.check_button = tk.Button(self, text=self.texts["check_version"], command=self.check_update)
        self.check_button.pack(pady=10, ipadx=10, ipady=5)

        self.exit_button = tk.Button(self, text=self.texts["exit_program"], command=self.exit_program)
        self.exit_button.pack(pady=10, ipadx=10, ipady=5)

    def append_status(self, text):
        current = self.status_label.cget("text")
        new_text = text if not current else current + "\n" + text
        self.status_label.config(text=new_text)

    def check_update(self):
        self.status_label.config(text=self.texts["checking"])
        self.update_idletasks()
        self.local_exe, self.local_ver = get_local_executable_and_version()
        if not self.local_ver:
            self.status_label.config(text=self.texts["cannot_determine_local"])
            return

        self.append_status(self.texts["local_version"].format(self.local_ver))

        self.latest_ver, self.latest_url = get_latest_github_version_and_asset_url()

        if self.latest_ver is None:
            if self.local_ver is None:
                self.append_status(self.texts["cannot_fetch_latest"])
            else:
                self.append_status(self.texts["no_update"])
            return

        self.append_status(self.texts["latest_version"].format(self.latest_ver))

        if version_tuple(self.latest_ver) > version_tuple(self.local_ver):
            self.append_status(self.texts["update_available"])
            self.download_and_replace()
        else:
            self.append_status(self.texts["no_update"])

    def download_and_replace(self):
        try:
            response = requests.get(self.latest_url, stream=True, timeout=DOWNLOAD_TIMEOUT)
            response.raise_for_status()
            base_name = "bookworm"
            new_exe_name = f"{base_name}_v{self.latest_ver.replace('.', '')}.exe"
            with open(new_exe_name, "wb") as f:
                for chunk in response.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            self.append_status(self.texts["download_success"])
            if self.local_exe and os.path.exists(self.local_exe):
                try:
                    os.remove(self.local_exe)
                    self.append_status(self.texts["removed_old"].format(self.local_exe))
                except Exception as e:
                    self.append_status(self.texts["remove_old_failed"].format(e))
        except Exception as e:
            self.append_status(self.texts["download_failed"].format(e))

    def exit_program(self):
        self.destroy()

if __name__ == "__main__":
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        settings = {"default_language": "EN"}
    lang = settings.get("default_language", "EN")
    app = UpdaterApp(lang=lang)
    app.mainloop()
