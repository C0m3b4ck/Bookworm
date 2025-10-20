import os
import re
import requests
import tkinter as tk
import json

import psutil  # Requires: pip install psutil

THEMES_FOLDER = "themes"
SETTINGS_FILE = "settings.json"

TRANSLATIONS = {
    "EN": {
        "title": "Updater",
        "check_version": "Check Version",
        "local_version": "Local version: {}",
        "latest_version": "Latest GitHub release: {}",
        "cannot_determine_local": "Could not determine local version from executable filename.\nExpected *_vXYZ.exe format.",
        "cannot_fetch_latest": "Could not fetch latest version from GitHub.",
        "update_available": "Update available! Downloading...",
        "no_update": "You have the latest version.",
        "download_failed": "Download failed: {}",
        "download_success": "Downloaded new files successfully.",
        "replace_failed": "Failed to replace file: {}",
        "replace_success": "Replaced file: {}",
        "checking": "Checking versions...",
        "skipped_file": "Skipped file: {}",
        "removed_old": "Removed old file: {}",
        "old_running": "Old file is running, not removed: {}",
    },
    "PL": {
        "title": "Aktualizator",
        "check_version": "Sprawdź Wersję",
        "local_version": "Lokalna wersja: {}",
        "latest_version": "Najnowsza wersja GitHub: {}",
        "cannot_determine_local": "Nie można określić lokalnej wersji z nazwy pliku.\nOczekiwano formatu *_vXYZ.exe.",
        "cannot_fetch_latest": "Nie można pobrać najnowszej wersji z GitHub.",
        "update_available": "Dostępna aktualizacja! Pobieranie...",
        "no_update": "Posiadasz najnowszą wersję.",
        "download_failed": "Pobieranie nieudane: {}",
        "download_success": "Nowe pliki zostały pobrane pomyślnie.",
        "replace_failed": "Nie udało się zastąpić pliku: {}",
        "replace_success": "Zastąpiono plik: {}",
        "checking": "Sprawdzanie wersji...",
        "skipped_file": "Pominięto plik: {}",
        "removed_old": "Usunięto stary plik: {}",
        "old_running": "Stary plik jest uruchomiony, nie usunięto: {}",
    },
}


def parse_version_from_filename(filename):
    m = re.search(r"_v(\d+)\.exe$", filename, re.IGNORECASE)
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
    for fname in os.listdir("."):
        if fname.lower().endswith(".exe") and "_v" in fname.lower():
            ver = parse_version_from_filename(fname)
            if ver:
                return fname, ver
    return None, None


def get_latest_github_version_and_assets():
    url = "https://api.github.com/repos/C0m3b4ck/Bookworm/releases"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        releases = r.json()
        latest_version = None
        latest_assets = []
        for release in releases:
            if release.get("prerelease") or release.get("draft"):
                continue
            tag_name = release.get("tag_name", "")
            m = re.match(r"version_(\d+\.\d+\.\d+)", tag_name)
            if m:
                version = m.group(1)
                assets = release.get("assets", [])
                if (latest_version is None) or (
                    version_tuple(version) > version_tuple(latest_version)
                ):
                    latest_version = version
                    latest_assets = assets
        if latest_version:
            return latest_version, latest_assets
    except Exception as e:
        print(f"Error checking latest GitHub release: {e}")
    return None, []


def version_tuple(v):
    return tuple(int(x) for x in v.split("."))


def is_exe_running(exe_name):
    exe_name = exe_name.lower()
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            pname = proc.info["name"]
            pexe = proc.info["exe"]
            if pname and pname.lower() == exe_name:
                return True
            if pexe and os.path.basename(pexe).lower() == exe_name:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def remove_old_exe_files(new_exe_name):
    # Find all bookworm_gui_v*.exe files except the new one
    pattern = re.compile(r"(bookworm_gui_v\d+)\.exe$", re.IGNORECASE)
    for fname in os.listdir("."):
        if fname.lower().endswith(".exe") and fname != new_exe_name:
            if pattern.match(fname):
                # Only remove if not running
                if not is_exe_running(fname):
                    try:
                        os.remove(fname)
                        return fname, True
                    except Exception:
                        return fname, False
                else:
                    return fname, None
    return None, None


class UpdaterApp(tk.Tk):
    def __init__(self, lang="EN", download_timeout=60):
        super().__init__()
        self.lang = lang if lang in TRANSLATIONS else "EN"
        self.texts = TRANSLATIONS[self.lang]
        self.download_timeout = download_timeout
        self.title(self.texts["title"])
        self.geometry("440x220")
        self.resizable(False, False)
        self.local_exe = None
        self.local_ver = None
        self.latest_ver = None
        self.latest_assets = []
        self.status_label = tk.Label(self, text="", justify="left")
        self.status_label.pack(pady=15, padx=15, fill="x")
        self.check_button = tk.Button(
            self, text=self.texts["check_version"], command=self.check_update
        )
        self.check_button.pack(pady=10, ipadx=10, ipady=5)

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

        self.latest_ver, self.latest_assets = get_latest_github_version_and_assets()

        if self.latest_ver is None:
            if self.local_ver is None:
                self.append_status(self.texts["cannot_fetch_latest"])
            else:
                self.append_status(self.texts["no_update"])
            return

        self.append_status(self.texts["latest_version"].format(self.latest_ver))

        if version_tuple(self.latest_ver) > version_tuple(self.local_ver):
            self.append_status(self.texts["update_available"])
            self.download_and_replace_files()
        else:
            self.append_status(self.texts["no_update"])

    def download_and_replace_files(self):
        try:
            new_exe_name = None
            for asset in self.latest_assets:
                asset_name = asset["name"]
                # Skip installer and .py files
                if "installer" in asset_name.lower() or asset_name.lower().endswith(
                    ".py"
                ):
                    self.append_status(self.texts["skipped_file"].format(asset_name))
                    continue
                asset_url = asset["browser_download_url"]
                response = requests.get(
                    asset_url, stream=True, timeout=self.download_timeout
                )
                response.raise_for_status()
                with open(asset_name, "wb") as f:
                    for chunk in response.iter_content(8192):
                        if chunk:
                            f.write(chunk)
                self.append_status(self.texts["replace_success"].format(asset_name))
                # If this is a bookworm_gui_v*.exe, remember it
                if re.match(r"bookworm_gui_v\d+\.exe$", asset_name, re.IGNORECASE):
                    new_exe_name = asset_name
            self.append_status(self.texts["download_success"])
            # Remove old exe files after new one is downloaded
            if new_exe_name:
                removed, status = remove_old_exe_files(new_exe_name)
                if removed and status is True:
                    self.append_status(self.texts["removed_old"].format(removed))
                elif removed and status is None:
                    self.append_status(self.texts["old_running"].format(removed))
                elif removed and status is False:
                    self.append_status(self.texts["replace_failed"].format(removed))
        except Exception as e:
            self.append_status(self.texts["download_failed"].format(e))


if __name__ == "__main__":
    # Load settings and get timeout
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        settings = {"default_language": "EN"}
    lang = settings.get("default_language", "EN")
    download_timeout = settings.get("download_timeout", 60)
    app = UpdaterApp(lang=lang, download_timeout=download_timeout)
    app.mainloop()
