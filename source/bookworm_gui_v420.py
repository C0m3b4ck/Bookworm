import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import hashlib
import base64
import os
import subprocess
import re
import time
import datetime
import json

SETTINGS_FILE = "settings.json"
THEMES_FOLDER = "themes"
DEFAULT_SETTINGS = {
    "default_language": None,
    "theme": "classic_blue",
}

DEFAULT_THEMES = {
    "classic_blue": {
        "BG": "#e6f0ff",
        "FG": "#000000",
        "BTN_BG": "#0059b3",
        "BTN_FG": "#ffffff",
        "BTN_HOVER_BG": "#666666",
        "BTN_HOVER_FG": "#ffff00",
    }
}

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60


def generate_key(username: str, password: str) -> bytes:
    combined = (username + password).encode("utf-8")
    hash_digest = hashlib.sha256(combined).digest()
    return base64.urlsafe_b64encode(hash_digest)


def encrypt_file(input_path: str, output_path: str, key: bytes):
    from cryptography.fernet import Fernet

    with open(input_path, "rb") as file:
        data = file.read()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(data)
    with open(output_path, "wb") as file:
        file.write(encrypted)


def decrypt_file(input_path: str, output_path: str, key: bytes) -> bool:
    from cryptography.fernet import Fernet, InvalidToken

    try:
        with open(input_path, "rb") as file:
            encrypted = file.read()
        fernet = Fernet(key)
        data = fernet.decrypt(encrypted)
        with open(output_path, "wb") as file:
            file.write(data)
        return True
    except (InvalidToken, FileNotFoundError):
        return False


def find_book_by_id_sql(conn, book_id):
    cur = conn.cursor()
    cur.execute("SELECT rowid, * FROM Books WHERE ID = ?", (book_id,))
    row = cur.fetchone()
    if row:
        rowid = row[0]
        data = row[1:]
        return rowid, data
    return None, None


def find_latest_version_executable(prefix):
    best_version = -1
    best_path = None
    for root, dirs, files in os.walk("."):
        for file in files:
            m = re.match(rf"^{prefix}_v(\d+)\.exe$", file, re.IGNORECASE)
            if m:
                ver = int(m.group(1))
                if ver > best_version:
                    best_version = ver
                    best_path = os.path.join(root, file)
    return best_path, best_version


class BookwormApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bookworm")
        self.geometry("900x600")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.settings = DEFAULT_SETTINGS.copy()
        self.themes = DEFAULT_THEMES.copy()
        self.lang = "EN"
        self.username = None
        self.password = None
        self.conn = None
        self.cursor = None
        self.db_encrypted_path = "bookworm.db.enc"
        self.db_decrypted_path = "bookworm.db"
        self.failed_login_attempts = 0
        self.last_failed_login_time = None
        self.is_admin = False

        # Check if settings.json exists before loading settings
        if not os.path.exists(SETTINGS_FILE):
            self.create_language_selection()
        else:
            self.settings = self.load_settings()
            self.load_custom_themes()
            self.set_theme(self.settings.get("theme", "classic_blue"))
            # Set language from settings if available, fallback to EN if not set
            self.lang = self.settings.get("default_language", "EN")
            if self.lang not in ["EN", "PL"]:
                self.lang = "EN"
            self.prompt_login_register()

    def on_close(self):
        self.close_db()
        self.destroy()

    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return DEFAULT_SETTINGS.copy()
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return DEFAULT_SETTINGS.copy()

    def save_settings(self, settings):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)

    def load_custom_themes(self):
        if not os.path.exists(THEMES_FOLDER):
            os.makedirs(THEMES_FOLDER)
            return
        for file in os.listdir(THEMES_FOLDER):
            if file.endswith(".json"):
                try:
                    path = os.path.join(THEMES_FOLDER, file)
                    with open(path, "r", encoding="utf-8") as f:
                        theme_data = json.load(f)
                    keys = {"BTN_BG", "BTN_FG", "BTN_HOVER_BG", "BTN_HOVER_FG"}
                    if keys.issubset(theme_data.keys()):
                        name = os.path.splitext(file)[0]
                        self.themes[name] = theme_data
                except Exception:
                    pass

    def set_theme(self, theme_name):
        theme = self.themes.get(theme_name, DEFAULT_THEMES["classic_blue"])
        self.BG = theme["BG"]
        self.FG = theme["FG"]
        self.BTN_BG = theme["BTN_BG"]
        self.BTN_FG = theme["BTN_FG"]
        self.BTN_HOVER_BG = theme["BTN_HOVER_BG"]
        self.BTN_HOVER_FG = theme["BTN_HOVER_FG"]

    def create_high_contrast_button(self, parent, text, command=None):
        btn = tk.Button(
            parent,
            text=text,
            bg=self.BTN_BG,
            fg=self.BTN_FG,
            activebackground=self.BTN_HOVER_BG,
            activeforeground=self.BTN_HOVER_FG,
            font=("Segoe UI", 12, "bold"),
            command=command,
            relief="raised",
            bd=3,
        )
        btn.bind(
            "<Enter>", lambda e: btn.config(bg=self.BTN_HOVER_BG, fg=self.BTN_HOVER_FG)
        )
        btn.bind("<Leave>", lambda e: btn.config(bg=self.BTN_BG, fg=self.BTN_FG))
        return btn

    def create_language_selection(self):
        for widget in self.winfo_children():
            widget.destroy()
        # Ensure theme is set before creating buttons
        self.set_theme(
            self.settings.get("theme", "classic_blue")
            if hasattr(self, "settings")
            else "classic_blue"
        )
        tk.Label(self, text="Select language / wybierz język", font=("Arial", 18)).grid(
            row=0, column=0, columnspan=2, pady=20
        )
        btn_en = self.create_high_contrast_button(
            self, "English", lambda: self.set_language_and_prompt_login("EN", save=True)
        )
        btn_en.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        btn_pl = self.create_high_contrast_button(
            self, "Polski", lambda: self.set_language_and_prompt_login("PL", save=True)
        )
        btn_pl.grid(row=1, column=1, sticky="nsew", padx=10, pady=5)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

    def set_language_and_prompt_login(self, lang, save=False):
        self.lang = lang if lang in ["EN", "PL"] else "EN"
        if save:
            # Save the selected language as default and create settings.json
            self.settings["default_language"] = self.lang
            self.save_settings(self.settings)
            self.load_custom_themes()
            self.set_theme(self.settings.get("theme", "classic_blue"))
        self.prompt_login_register()

    def prompt_login_register(self):
        for widget in self.winfo_children():
            widget.destroy()
        label_login = (
            "Login / Register" if self.lang == "EN" else "Logowanie / Rejestracja"
        )
        label_username = "Username:" if self.lang == "EN" else "Nazwa użytkownika:"
        label_password = "Password:" if self.lang == "EN" else "Hasło:"
        tk.Label(self, text=label_login, font=("Arial", 18)).grid(
            row=0, column=0, columnspan=2, pady=20
        )
        tk.Label(self, text=label_username).grid(
            row=1, column=0, padx=10, pady=5, sticky="w"
        )
        username_entry = tk.Entry(self)
        username_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        tk.Label(self, text=label_password).grid(
            row=2, column=0, padx=10, pady=5, sticky="w"
        )
        password_entry = tk.Entry(self, show="*")
        password_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        # Enter in username moves to password, Enter in password triggers login
        def focus_password(event):
            password_entry.focus_set()

        username_entry.bind("<Return>", focus_password)
        password_entry.bind("<Return>", lambda event: try_login())

        def try_login():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            if not username or not password:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "Username and password required"
                    if self.lang == "EN"
                    else "Wymagana nazwa użytkownika i hasło",
                )
                return
            now = time.time()
            if self.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
                if (
                    self.last_failed_login_time
                    and now - self.last_failed_login_time < LOGIN_LOCKOUT_SECONDS
                ):
                    messagebox.showerror(
                        "Locked Out" if self.lang == "EN" else "Zablokowano",
                        (
                            f"Too many failed attempts. Try again in {int(LOGIN_LOCKOUT_SECONDS - (now - self.last_failed_login_time))} seconds."
                            if self.lang == "EN"
                            else f"Zbyt wiele nieudanych prób. Spróbuj ponownie za {int(LOGIN_LOCKOUT_SECONDS - (now - self.last_failed_login_time))} sekund."
                        ),
                    )
                    return
                else:
                    self.failed_login_attempts = 0
            self.load_or_create_encrypted_db()
            self.cursor.execute(
                "SELECT id, password, is_admin FROM users WHERE username=?", (username,)
            )
            row = self.cursor.fetchone()
            if row and row[1] == password:
                self.username = username
                self.is_admin = bool(row[2])
                self.failed_login_attempts = 0
                # Ensure language is set correctly before showing main menu
                self.lang = self.settings.get("default_language", "EN")
                if self.lang not in ["EN", "PL"]:
                    self.lang = "EN"
                self.log_action(row[0], f"login (user: {username})")
                self.create_main_menu()
            else:
                self.failed_login_attempts += 1
                self.last_failed_login_time = now
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "Invalid username or password"
                    if self.lang == "EN"
                    else "Nieprawidłowa nazwa użytkownika lub hasło",
                )
                if row:
                    self.log_action(row[0], f"failed_login (user: {username})")

        def try_register():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            if not username or not password:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "Username and password required"
                    if self.lang == "EN"
                    else "Wymagana nazwa użytkownika i hasło",
                )
                return
            self.load_or_create_encrypted_db()
            self.cursor.execute("SELECT COUNT(*) FROM users")
            user_count = self.cursor.fetchone()[0]
            if user_count == 0:
                # First account is admin
                if messagebox.askyesno(
                    "Admin Account" if self.lang == "EN" else "Konto administratora",
                    "You are creating the ONLY admin account. The password is irrecoverable. Proceed?"
                    if self.lang == "EN"
                    else "Tworzysz JEDYNE konto administratora. Hasło nie będzie możliwe do odzyskania. Kontynuować?",
                ):
                    self.cursor.execute(
                        "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)",
                        (username, password),
                    )
                    self.conn.commit()
                    self.username = username
                    self.is_admin = True
                    self.log_action(
                        self.get_user_id(username), f"admin_created (user: {username})"
                    )
                    self.create_main_menu()
                else:
                    return
            else:
                try:
                    self.cursor.execute(
                        "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 0)",
                        (username, password),
                    )
                    self.conn.commit()
                    self.username = username
                    self.is_admin = False
                    self.log_action(
                        self.get_user_id(username), f"user_created (user: {username})"
                    )
                    self.create_main_menu()
                except sqlite3.IntegrityError:
                    messagebox.showerror(
                        "Error" if self.lang == "EN" else "Błąd",
                        "User already exists"
                        if self.lang == "EN"
                        else "Użytkownik już istnieje",
                    )

        btn_register = self.create_high_contrast_button(
            self, "Register" if self.lang == "EN" else "Zarejestruj", try_register
        )
        btn_register.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)
        btn_login = self.create_high_contrast_button(
            self, "Login" if self.lang == "EN" else "Zaloguj", try_login
        )
        btn_login.grid(row=3, column=1, sticky="nsew", padx=10, pady=10)
        btn_exit = self.create_high_contrast_button(
            self, "Exit" if self.lang == "EN" else "Zakończ", self.quit
        )
        btn_exit.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=10, pady=10)
        self.grid_columnconfigure(1, weight=1)

    def db_encrypted_file_exists(self):
        return os.path.exists(self.db_encrypted_path)

    def load_or_create_encrypted_db(self):
        if not self.conn:
            # Use admin-selected db file if present, else default
            db_file = self.settings.get("db_file", "bookworm.db")
            self.db_decrypted_path = db_file
            if not os.path.exists(self.db_decrypted_path):
                if self.db_encrypted_file_exists():
                    key = generate_key(self.username, self.password)
                    if not decrypt_file(
                        self.db_encrypted_path, self.db_decrypted_path, key
                    ):
                        raise Exception("Failed to decrypt database")
            self.conn = sqlite3.connect(self.db_decrypted_path)
            self.cursor = self.conn.cursor()
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS Books (
                    ID INTEGER PRIMARY KEY,
                    Title TEXT,
                    Author TEXT,
                    Year INTEGER,
                    Genre TEXT,
                    Status TEXT,
                    BookRow TEXT
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS RemovedBooks (
                    ID INTEGER PRIMARY KEY,
                    Title TEXT,
                    Author TEXT,
                    Year INTEGER,
                    Genre TEXT,
                    Status TEXT
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    is_admin INTEGER DEFAULT 0,
                    is_superadmin INTEGER DEFAULT 0,
                    privileges TEXT DEFAULT ''
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS readers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    surname TEXT NOT NULL,
                    grade TEXT NOT NULL
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS borrowed_books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    reader_id INTEGER NOT NULL,
                    borrow_date TEXT NOT NULL,
                    return_date TEXT,
                    status TEXT NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books (ID),
                    FOREIGN KEY (reader_id) REFERENCES readers (id)
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT,
                    timestamp TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            self.conn.commit()

    def create_new_encrypted_db(self):
        self.conn = sqlite3.connect(self.db_decrypted_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Books (
                ID INTEGER PRIMARY KEY,
                Title TEXT,
                Author TEXT,
                Year INTEGER,
                Genre TEXT,
                Status TEXT,
                BookRow TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS RemovedBooks (
                ID INTEGER PRIMARY KEY,
                Title TEXT,
                Author TEXT,
                Year INTEGER,
                Genre TEXT,
                Status TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                privileges TEXT DEFAULT ''
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS readers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                surname TEXT NOT NULL,
                grade TEXT NOT NULL
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS borrowed_books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                reader_id INTEGER NOT NULL,
                borrow_date TEXT NOT NULL,
                return_date TEXT,
                status TEXT NOT NULL,
                FOREIGN KEY (book_id) REFERENCES Books (ID),
                FOREIGN KEY (reader_id) REFERENCES readers (id)
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                timestamp TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        self.conn.commit()

    def close_db(self):
        if self.conn:
            self.conn.close()
            self.conn = None
        if (
            self.db_decrypted_path
            and self.db_encrypted_path
            and self.username
            and self.password
        ):
            key = generate_key(self.username, self.password)
            encrypt_file(self.db_decrypted_path, self.db_encrypted_path, key)
            try:
                # Prevent deletion of .db.enc file (like system32)
                if (
                    self.db_decrypted_path
                    and self.db_decrypted_path.endswith(".db")
                    and not self.db_decrypted_path.endswith(".db.enc")
                ):
                    os.remove(self.db_decrypted_path)
                # Do NOT delete .db.enc under any circumstances
            except Exception:
                pass

    def get_user_id(self, username):
        self.cursor.execute("SELECT id FROM users WHERE username=?", (username,))
        row = self.cursor.fetchone()
        return row[0] if row else None

    def log_action(self, user_id, action):
        import datetime

        now = datetime.datetime.now().isoformat()
        self.cursor.execute(
            "INSERT INTO logs (user_id, action, timestamp) VALUES (?, ?, ?)",
            (user_id, action, now),
        )
        self.conn.commit()

    def logout(self):
        self.close_db()
        self.username = None
        self.password = None
        self.create_language_selection()

    def run_updater(self):
        updater_file, ver = find_latest_version_executable("updater")
        if not updater_file:
            messagebox.showinfo(
                "Updater Not Found" if self.lang == "EN" else "Updater nie znaleziony",
                "Updater executable not found. Please install/update manually."
                if self.lang == "EN"
                else "Nie znaleziono programu aktualizującego. Proszę zainstalować/zaktualizować ręcznie.",
            )
            return
        try:
            subprocess.Popen([os.path.abspath(updater_file)], shell=True)
        except Exception as e:
            messagebox.showerror(
                "Error" if self.lang == "EN" else "Błąd",
                f"Failed to launch updater:\n{e}"
                if self.lang == "EN"
                else f"Nie udało się uruchomić aktualizatora:\n{e}",
            )

    def add_new_book_form(self):
        # Ensure language is set correctly before showing form
        if not hasattr(self, "lang") or self.lang not in ["EN", "PL"]:
            self.lang = self.settings.get("default_language", "EN")
            if self.lang not in ["EN", "PL"]:
                self.lang = "EN"
        form = tk.Toplevel(self)
        form.title("Add New Book" if self.lang == "EN" else "Dodaj nową książkę")
        form.geometry("460x390")
        form.grab_set()
        labels = {
            "EN": [
                "ID (0 may repeat)",
                "Title",
                "Author",
                "Year",
                "Genre",
                "Status",
                "Book Row",
            ],
            "PL": [
                "ID (0 może się powtarzać)",
                "Tytuł",
                "Autor",
                "Rok",
                "Gatunek",
                "Status",
                "Regał książkowy",
            ],
        }
        status_options = {
            "EN": ["borrowed", "available", "missing", "returned", "other"],
            "PL": ["wypożyczona", "dostępna", "brak", "zwrócona", "inne"],
        }
        entries = {}
        for i, text in enumerate(labels[self.lang]):
            lbl = tk.Label(form, text=text, anchor="w")
            lbl.grid(row=i, column=0, padx=10, pady=8, sticky="w")
            if text == "Status" or text == "Status":
                cmb = ttk.Combobox(
                    form, values=status_options[self.lang], state="readonly"
                )
                cmb.grid(row=i, column=1, padx=10, pady=8, sticky="ew")
                cmb.current(1)  # Default to "available"
                entries[text] = cmb
            else:
                ent = tk.Entry(form)
                ent.grid(row=i, column=1, padx=10, pady=8, sticky="ew")
                entries[text] = ent
                ent.bind(
                    "<Return>",
                    lambda e, i=i: self.entry_return_key(entries, labels[self.lang], i),
                )
                ent.bind(
                    "<BackSpace>",
                    lambda e, i=i: self.entry_backspace_key(
                        e, entries, labels[self.lang], i
                    ),
                )
                ent.bind(
                    "<Left>",
                    lambda e, i=i: self.entry_arrow_key(
                        e, entries, labels[self.lang], i, direction="left"
                    ),
                )
                ent.bind(
                    "<Right>",
                    lambda e, i=i: self.entry_arrow_key(
                        e, entries, labels[self.lang], i, direction="right"
                    ),
                )
                ent.bind(
                    "<Up>",
                    lambda e, i=i: self.entry_arrow_key(
                        e, entries, labels[self.lang], i, direction="up"
                    ),
                )
                ent.bind(
                    "<Down>",
                    lambda e, i=i: self.entry_arrow_key(
                        e, entries, labels[self.lang], i, direction="down"
                    ),
                )
        form.grid_columnconfigure(1, weight=1)
        form.after(100, lambda: entries[labels[self.lang][0]].focus_set())

        def submit():
            try:
                id_val = int(entries[labels[self.lang][0]].get())
                if id_val < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "ID must be a number >= 0"
                    if self.lang == "EN"
                    else "ID musi być liczbą >= 0",
                )
                return
            existing_ids = self.get_existing_ids()
            if id_val != 0 and id_val in existing_ids:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "ID already exists or input 0 which may repeat"
                    if self.lang == "EN"
                    else "ID już istnieje lub wpisz 0, który może się powtarzać",
                )
                return
            title = entries[labels[self.lang][1]].get().strip()
            if not title:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "Title is required" if self.lang == "EN" else "Tytuł jest wymagany",
                )
                return
            author = entries[labels[self.lang][2]].get().strip()
            year = entries[labels[self.lang][3]].get().strip()
            genre = entries[labels[self.lang][4]].get().strip()
            status = entries[labels[self.lang][5]].get().strip()
            # Ensure status is 'available' unless user explicitly chooses otherwise
            if not status or status.lower() not in [
                "available",
                "dostępna",
                "borrowed",
                "wypożyczona",
                "missing",
                "brak",
                "other",
                "inne",
            ]:
                status = "available"
            book_row = entries[labels[self.lang][6]].get().strip()
            try:
                cur = self.conn.cursor()
                # SQLite upsert workaround: Try insert, if fail update
                cur.execute(
                    "INSERT OR REPLACE INTO Books (ID, Title, Author, Year, Genre, Status, BookRow) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (id_val, title, author, year, genre, status, book_row),
                )
                self.conn.commit()
            except Exception as e:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd", f"Failed to add book: {e}"
                )
                return
            messagebox.showinfo(
                "Success" if self.lang == "EN" else "Sukces",
                "Book added successfully."
                if self.lang == "EN"
                else "Książka dodana pomyślnie.",
            )
            form.destroy()
            # --- Refresh lending tab's books table if open ---
            # If open_reader_panel is open, call its load_readers_books to refresh tables
            for win in self.winfo_children():
                if isinstance(win, tk.Toplevel) and (
                    "Reader Panel" in win.title() or "Panel Czytelnika" in win.title()
                ):
                    # Try to call load_readers_books if present
                    try:
                        win.load_readers_books()
                    except Exception:
                        # Fallback: manually refresh tables as before
                        for child in win.winfo_children():
                            if isinstance(child, ttk.Notebook):
                                for tab in child.winfo_children():
                                    if hasattr(tab, "winfo_children"):
                                        for widget in tab.winfo_children():
                                            if isinstance(
                                                widget, ttk.Treeview
                                            ) and widget["columns"] == (
                                                "ID",
                                                "Title",
                                                "Author",
                                                "Year",
                                                "Genre",
                                                "Status",
                                            ):
                                                widget.delete(*widget.get_children())
                                                self.cursor.execute(
                                                    "SELECT ID, Title, Author, Year, Genre, Status FROM Books WHERE Status='available'"
                                                )
                                                for row in self.cursor.fetchall():
                                                    widget.insert("", "end", values=row)

        submit_btn = tk.Button(
            form,
            text="Submit" if self.lang == "EN" else "Zatwierdź",
            bg=self.BTN_BG,
            fg=self.BTN_FG,
            activebackground=self.BTN_HOVER_BG,
            activeforeground=self.BTN_HOVER_FG,
            font=("Segoe UI", 12, "bold"),
            command=submit,
        )
        submit_btn.grid(
            row=len(labels[self.lang]), column=0, columnspan=2, pady=15, sticky="ew"
        )
        submit_btn.bind("<Return>", lambda e: submit())

    def get_existing_ids(self):
        cur = self.conn.cursor()
        cur.execute("SELECT ID FROM Books")
        ids = [row[0] for row in cur.fetchall() if row[0] is not None]
        return ids

    def entry_return_key(self, entries, label_list, current_index):
        next_index = current_index + 1
        if next_index < len(label_list):
            entries[label_list[next_index]].focus_set()
        else:
            entries[label_list[current_index]].master.children["!button"].invoke()

    def entry_backspace_key(self, event, entries, label_list, current_index):
        entry = event.widget
        if entry.get() == "" and current_index > 0:
            entries[label_list[current_index - 1]].focus_set()
        return "break"

    def entry_arrow_key(self, event, entries, label_list, current_index, direction):
        if direction in ("left", "up") and current_index > 0:
            entries[label_list[current_index - 1]].focus_set()
        elif direction in ("right", "down") and current_index < len(label_list) - 1:
            entries[label_list[current_index + 1]].focus_set()
        return "break"

    def see_modify_books(self):
        top = tk.Toplevel(self)
        top.title("Books" if self.lang == "EN" else "Książki")
        top.geometry("900x520")
        search_frame = tk.Frame(top)
        search_frame.pack(fill="x", padx=5, pady=5)

        search_labels_en = [
            "Search by ID",
            "Search by Title",
            "Search by Author",
            "Search by Year",
            "Search by Genre",
            "Search by Status",
            "Search",
        ]
        search_labels_pl = [
            "Szukaj po ID",
            "Szukaj po tytule",
            "Szukaj po autorze",
            "Szukaj po roku",
            "Szukaj po gatunku",
            "Szukaj po statusie",
            "Szukaj",
        ]
        search_labels = search_labels_en if self.lang == "EN" else search_labels_pl
        self.search_vars = {key: tk.StringVar() for key in search_labels[:-1]}
        self.sort_directions = {
            key: True for key in search_labels[:-1]
        }  # All ascending start

        entries_order = []
        for idx, label in enumerate(search_labels[:-1]):
            tk.Label(search_frame, text=label).grid(row=0, column=idx * 2, sticky="w")
            ent = tk.Entry(search_frame, textvariable=self.search_vars[label], width=15)
            ent.grid(row=0, column=idx * 2 + 1, padx=(0, 10), sticky="ew")
            entries_order.append(ent)
            # Bindings for enter key in search fields to run filter_tree
            ent.bind("<Return>", lambda e: filter_tree())

            search_frame.grid_columnconfigure(idx * 2, weight=0)
            search_frame.grid_columnconfigure(idx * 2 + 1, weight=1)

        btn_search = tk.Button(
            search_frame,
            text=search_labels[-1],
            bg=self.BTN_BG,
            fg=self.BTN_FG,
            activebackground=self.BTN_HOVER_BG,
            activeforeground=self.BTN_HOVER_FG,
            font=("Segoe UI", 11, "bold"),
            command=lambda: filter_tree(),
        )
        btn_search.grid(row=0, column=14, padx=(0, 10))
        search_frame.grid_columnconfigure(14, weight=0)

        cols = ("ID", "Title", "Author", "Year", "Genre", "Status")
        if self.lang == "EN":
            col_headings = ["ID", "Title", "Author", "Year", "Genre", "Status"]
        else:
            col_headings = ["ID", "Tytuł", "Autor", "Rok", "Gatunek", "Status"]

        tree = ttk.Treeview(top, columns=cols, show="headings")

        for col, heading in zip(cols, col_headings):
            tree.heading(
                col, text=heading, command=lambda c=col: self.sort_by_column(tree, c)
            )
            tree.column(
                col, width=150 if col not in ("Year", "Status") else 80, stretch=True
            )
        tree.pack(expand=True, fill="both", padx=5, pady=5)
        top.grid_columnconfigure(0, weight=1)
        top.grid_rowconfigure(1, weight=1)  # not mandatory here since using pack

        btn_frame = tk.Frame(top)
        btn_frame.pack(fill="x", pady=5)
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        btn_frame.grid_columnconfigure(2, weight=1)

        def load_tree_data(filter_criteria=None, sort_by=None, ascending=True):
            tree.delete(*tree.get_children())
            try:
                cur = self.conn.cursor()
                base_query = "SELECT ID, Title, Author, Year, Genre, Status FROM Books"
                params = []
                where_clauses = []
                if filter_criteria:
                    for key, val in filter_criteria.items():
                        # For ID and Year exact match, others LIKE match insensitive
                        if key in ("ID", "Year"):
                            where_clauses.append(f"{key} = ?")
                            params.append(val)
                        else:
                            where_clauses.append(f"{key} LIKE ?")
                            params.append(f"%{val}%")
                if where_clauses:
                    base_query += " WHERE " + " AND ".join(where_clauses)
                if sort_by:
                    base_query += (
                        f" ORDER BY {sort_by} {'ASC' if ascending else 'DESC'}"
                    )
                cur.execute(base_query, params)
                rows = cur.fetchall()
                for row in rows:
                    vals = list(row)
                    if len(vals) < 6:
                        vals += [""] * (6 - len(vals))
                    tree.insert("", "end", values=vals)
            except Exception as e:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    f"Failed to load data: {e}",
                )

        def filter_tree():
            crit = {}
            cleared_all = True
            for key in self.search_vars:
                val = self.search_vars[key].get().strip()
                if val != "":
                    cleared_all = False
                    crit_key = key if self.lang == "EN" else key
                    crit[crit_key] = val
            if cleared_all:
                load_tree_data()
            else:
                keys_map_pl_en = {
                    "Szukaj po ID": "ID",
                    "Szukaj po tytule": "Title",
                    "Szukaj po autorze": "Author",
                    "Szukaj po roku": "Year",
                    "Szukaj po gatunku": "Genre",
                    "Szukaj po statusie": "Status",
                    "Search by ID": "ID",
                    "Search by Title": "Title",
                    "Search by Author": "Author",
                    "Search by Year": "Year",
                    "Search by Genre": "Genre",
                    "Search by Status": "Status",
                }
                crit_en = {keys_map_pl_en.get(k, k): v for k, v in crit.items()}
                load_tree_data(crit_en)

        filter_tree()

        def on_edit():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning(
                    "Warning" if self.lang == "EN" else "Uwaga",
                    "Select a book to edit"
                    if self.lang == "EN"
                    else "Wybierz książkę do edycji",
                )
                return
            item = tree.item(selected[0])
            values = item["values"]
            self.edit_book(values[0])
            top.destroy()

        def on_remove():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning(
                    "Warning" if self.lang == "EN" else "Uwaga",
                    "Select a book to remove"
                    if self.lang == "EN"
                    else "Wybierz książkę do usunięcia",
                )
                return
            item = tree.item(selected[0])
            values = item["values"]
            book_id = values[0]
            book_data = values[:6]

            confirmed = messagebox.askyesno(
                "Confirm removal" if self.lang == "EN" else "Potwierdź usunięcie",
                "Are you sure you want to remove the selected book?"
                if self.lang == "EN"
                else "Czy na pewno chcesz usunąć wybraną książkę?",
            )
            if not confirmed:
                return
            try:
                cur = self.conn.cursor()
                # delete from Books
                cur.execute("DELETE FROM Books WHERE ID = ?", (book_id,))
                # add to RemovedBooks
                cur.execute(
                    """INSERT OR REPLACE INTO RemovedBooks
                            (ID, Title, Author, Year, Genre, Status)
                            VALUES (?, ?, ?, ?, ?, ?)""",
                    tuple(book_data),
                )
                self.conn.commit()
            except Exception as e:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    f"Failed to remove book: {e}",
                )
                return
            messagebox.showinfo(
                "Removed" if self.lang == "EN" else "Usunięto",
                "Book removed and saved in removed list."
                if self.lang == "EN"
                else "Książka usunięta i zapisana na liście usuniętych.",
            )
            tree.delete(selected[0])
            filter_tree()

        btn_edit = tk.Button(
            btn_frame,
            text="Edit Book" if self.lang == "EN" else "Edytuj książkę",
            bg=self.BTN_BG,
            fg=self.BTN_FG,
            activebackground=self.BTN_HOVER_BG,
            activeforeground=self.BTN_HOVER_FG,
            font=("Segoe UI", 11, "bold"),
            command=on_edit,
        )
        btn_edit.pack(side="left", padx=10)

        btn_remove = tk.Button(
            btn_frame,
            text="Remove Book" if self.lang == "EN" else "Usuń książkę",
            bg=self.BTN_BG,
            fg=self.BTN_FG,
            activebackground=self.BTN_HOVER_BG,
            activeforeground=self.BTN_HOVER_FG,
            font=("Segoe UI", 11, "bold"),
            command=on_remove,
        )
        btn_remove.pack(side="left", padx=10)

        btn_close = tk.Button(
            btn_frame,
            text="Close" if self.lang == "EN" else "Zamknij",
            command=top.destroy,
        )
        btn_close.pack(side="bottom", fill="x", pady=(10, 0), padx=10)

    def sort_by_column(self, tree, col):
        ascending = self.sort_directions[col]
        self.sort_directions[col] = not ascending
        crit = {}
        cleared_all = True
        for key in self.search_vars:
            val = self.search_vars[key].get().strip()
            if val != "":
                cleared_all = False
                keys_map_pl_en = {
                    "Szukaj po ID": "ID",
                    "Szukaj po tytule": "Title",
                    "Szukaj po autorze": "Author",
                    "Szukaj po roku": "Year",
                    "Szukaj po gatunku": "Genre",
                    "Szukaj po statusie": "Status",
                    "Search by ID": "ID",
                    "Search by Title": "Title",
                    "Search by Author": "Author",
                    "Search by Year": "Year",
                    "Search by Genre": "Genre",
                    "Search by Status": "Status",
                }
                crit[keys_map_pl_en.get(key, key)] = val
        filter_criteria = None if cleared_all else crit
        tree.delete(*tree.get_children())
        try:
            cur = self.conn.cursor()
            base_query = "SELECT ID, Title, Author, Year, Genre, Status FROM Books"
            params = []
            where_clauses = []
            if filter_criteria:
                for key, val in filter_criteria.items():
                    if key in ("ID", "Year"):
                        where_clauses.append(f"{key} = ?")
                        params.append(val)
                    else:
                        where_clauses.append(f"{key} LIKE ?")
                        params.append(f"%{val}%")
            if where_clauses:
                base_query += " WHERE " + " AND ".join(where_clauses)
            if col:
                base_query += f" ORDER BY {col} {'ASC' if ascending else 'DESC'}"
            cur.execute(base_query, params)
            rows = cur.fetchall()
            for row in rows:
                vals = list(row)
                if len(vals) < 6:
                    vals += [""] * (6 - len(vals))
                tree.insert("", "end", values=vals)
        except Exception as e:
            messagebox.showerror(
                "Error" if self.lang == "EN" else "Błąd", f"Failed to sort data: {e}"
            )

    def edit_book(self, book_id):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT ID, Title, Author, Year, Genre, Status, BookRow FROM Books WHERE ID = ?",
            (book_id,),
        )
        row = cur.fetchone()
        if not row:
            messagebox.showerror(
                "Error" if self.lang == "EN" else "Błąd",
                "Book not found" if self.lang == "EN" else "Książka nie znaleziona",
            )
            return self.create_main_menu()
        current = {
            "ID": row[0],
            "Title": row[1],
            "Author": row[2],
            "Year": row[3],
            "Genre": row[4],
            "Status": row[5],
            "BookRow": row[6] if len(row) > 6 else "",
        }
        form = tk.Toplevel(self)
        form.title("Edit Book" if self.lang == "EN" else "Edytuj książkę")
        form.geometry("440x360")
        form.grab_set()
        labels = {
            "EN": ["ID (0 may repeat)", "Title", "Author", "Year", "Genre", "Status"],
            "PL": [
                "ID (0 może się powtarzać)",
                "Tytuł",
                "Autor",
                "Rok",
                "Gatunek",
                "Status",
            ],
        }
        status_options = {
            "EN": ["borrowed", "available", "missing", "other"],
            "PL": ["wypożyczona", "dostępna", "brak", "inne"],
        }
        entries = {}
        values_current = [
            current["ID"],
            current["Title"],
            current["Author"],
            current["Year"],
            current["Genre"],
            current["Status"],
        ]
        for i, text in enumerate(labels[self.lang]):
            lbl = tk.Label(form, text=text, anchor="w")
            lbl.grid(row=i, column=0, padx=10, pady=8, sticky="w")
            if text == "Status" or text == "Status":
                cmb = ttk.Combobox(
                    form, values=status_options[self.lang], state="readonly"
                )
                cmb.grid(row=i, column=1, padx=10, pady=8, sticky="ew")
                try:
                    cmb.current(
                        status_options[self.lang].index(
                            str(values_current[i]).casefold()
                        )
                    )
                except Exception:
                    cmb.current(1)  # default to "available"
                entries[text] = cmb
            else:
                ent = tk.Entry(form)
                ent.grid(row=i, column=1, padx=10, pady=8, sticky="ew")
                ent.insert(0, values_current[i])
                entries[text] = ent
                ent.bind(
                    "<Return>",
                    lambda e, i=i: self.entry_return_key(entries, labels[self.lang], i),
                )
                ent.bind(
                    "<BackSpace>",
                    lambda e, i=i: self.entry_backspace_key(
                        e, entries, labels[self.lang], i
                    ),
                )
                ent.bind(
                    "<Left>",
                    lambda e, i=i: self.entry_arrow_key(
                        e, entries, labels[self.lang], i, direction="left"
                    ),
                )
                ent.bind(
                    "<Right>",
                    lambda e, i=i: self.entry_arrow_key(
                        e, entries, labels[self.lang], i, direction="right"
                    ),
                )
                ent.bind(
                    "<Up>",
                    lambda e, i=i: self.entry_arrow_key(
                        e, entries, labels[self.lang], i, direction="up"
                    ),
                )
                ent.bind(
                    "<Down>",
                    lambda e, i=i: self.entry_arrow_key(
                        e, entries, labels[self.lang], i, direction="down"
                    ),
                )
        form.grid_columnconfigure(1, weight=1)

        def submit():
            try:
                id_val = int(entries[labels[self.lang][0]].get())
                if id_val < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "ID must be a number >= 0"
                    if self.lang == "EN"
                    else "ID musi być liczbą >= 0",
                )
                return
            existing_ids = self.get_existing_ids()
            if id_val != 0 and id_val in existing_ids and id_val != current["ID"]:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "ID already exists or input 0 which may repeat"
                    if self.lang == "EN"
                    else "ID już istnieje lub wpisz 0, który może się powtarzać",
                )
                return
            title = entries[labels[self.lang][1]].get().strip()
            if not title:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "Title is required" if self.lang == "EN" else "Tytuł jest wymagany",
                )
                return
            author = entries[labels[self.lang][2]].get().strip()
            year = entries[labels[self.lang][3]].get().strip()
            genre = entries[labels[self.lang][4]].get().strip()
            status = entries[labels[self.lang][5]].get().strip()
            try:
                cur = self.conn.cursor()
                # Update by rowid primary key - we use ID as primary key but update by ID
                cur.execute(
                    """UPDATE Books SET ID=?, Title=?, Author=?, Year=?, Genre=?, Status=?
                            WHERE ID=?""",
                    (id_val, title, author, year, genre, status, current["ID"]),
                )
                self.conn.commit()
            except Exception as e:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    f"Failed to update book: {e}",
                )
                return
            messagebox.showinfo(
                "Success" if self.lang == "EN" else "Sukces",
                "Book updated successfully."
                if self.lang == "EN"
                else "Książka zaktualizowana pomyślnie.",
            )
            form.destroy()

        submit_btn = tk.Button(
            form,
            text="Submit" if self.lang == "EN" else "Zatwierdź",
            bg=self.BTN_BG,
            fg=self.BTN_FG,
            activebackground=self.BTN_HOVER_BG,
            activeforeground=self.BTN_HOVER_FG,
            font=("Segoe UI", 12, "bold"),
            command=submit,
        )
        submit_btn.grid(
            row=len(labels[self.lang]), column=0, columnspan=2, pady=15, sticky="ew"
        )
        submit_btn.bind("<Return>", lambda e: submit())

    def show_help(self):
        help_text_en = (
            "Bookworm Help:\n\n"
            "1. Add New Book: Add a new book with details.\n"
            "2. See/Modify Books: View and edit existing books.\n"
            "3. Help: Show this help message.\n"
            "4. Update: looks for the new program version. "
            "5. Settings: Change theme and default language, allows for custom themes.\n"
            "6. Logout: Log out of the current user.\n"
            "7. Exit: Close the program."
        )
        help_text_pl = (
            "Pomoc Bookworm:\n\n"
            "1. Dodaj książkę: Dodaj nową książkę z danymi.\n"
            "2. Obejrzyj/modyfikuj książki: Przeglądaj i edytuj książki.\n"
            "3. Pomoc: Wyświetl tę pomoc.\n"
            "4. Aktualizuj: wyszukuje nową wersję programu.\n"
            "5. Ustawienia: Zmień motyw i język domyślny, stwórz własny motyw.\n"
            "6. Wyloguj: Wyloguj się z bieżącego użytkownika.\n"
            "7. Zakończ: Zamknij program."
        )
        messagebox.showinfo(
            "Help" if self.lang == "EN" else "Pomoc",
            help_text_en if self.lang == "EN" else help_text_pl,
        )
        self.create_main_menu()

    def create_main_menu(self):
        for widget in self.winfo_children():
            widget.destroy()
        # Ensure language is set correctly before showing main menu
        if not hasattr(self, "lang") or self.lang not in ["EN", "PL"]:
            self.lang = self.settings.get("default_language", "EN")
            if self.lang not in ["EN", "PL"]:
                self.lang = "EN"
        lang = self.lang
        credits_text = (
            "Made by C0m3b4ck under APL 2.0 license"
            if lang == "EN"
            else "Stworzone przez C0m3b4ck pod licencją APL 2.0"
        )
        label_text = "Main Menu" if lang == "EN" else "Menu główne"
        tk.Label(self, text=label_text, font=("Arial", 20)).grid(
            row=0, column=0, columnspan=3, pady=10
        )
        tk.Label(self, text=credits_text, font=("Arial", 10, "italic")).grid(
            row=1, column=0, columnspan=3, pady=5
        )

        options = {
            "EN": [
                "Add New Book",
                "See/Modify Books",
                "Help",
                "Update",
                "Settings",
                "Logout",
            ],
            "PL": [
                "Dodaj książkę",
                "Przeglądaj/Modyfikuj książki",
                "Pomoc",
                "Aktualizuj",
                "Ustawienia",
                "Wyloguj",
            ],
        }
        exit_option = {"EN": "Exit", "PL": "Zakończ"}
        commands = [
            lambda: self.add_new_book_form(),
            lambda: self.see_modify_books(),
            lambda: self.show_help(),
            lambda: self.run_updater(),
            lambda: self.show_settings(),
            lambda: self.logout(),
        ]
        # Main menu buttons (except Exit)
        for i, (option, command) in enumerate(zip(options[lang], commands), start=2):
            btn = self.create_high_contrast_button(self, option, command=command)
            btn.grid(row=i, column=0, columnspan=3, sticky="nsew", padx=50, pady=7)
        next_row = len(options[lang]) + 2
        # Admin Panel button
        if getattr(self, "is_admin", False):
            btn_admin = self.create_high_contrast_button(
                self,
                "Admin Panel" if lang == "EN" else "Panel Admina",
                command=self.open_admin_panel,
            )
            btn_admin.grid(
                row=next_row, column=0, columnspan=3, sticky="nsew", padx=50, pady=7
            )
            self.grid_rowconfigure(next_row, weight=1)
            next_row += 1
        # Reader Panel button
        if getattr(self, "is_admin", False):
            btn_reader = self.create_high_contrast_button(
                self,
                "Reader Panel" if lang == "EN" else "Panel Czytelnika",
                command=self.open_reader_panel,
            )
            btn_reader.grid(
                row=next_row, column=0, columnspan=3, sticky="nsew", padx=50, pady=7
            )
            self.grid_rowconfigure(next_row, weight=1)
            next_row += 1
        # Exit button at the bottom
        btn_exit = self.create_high_contrast_button(
            self, exit_option[lang], command=self.quit
        )
        btn_exit.grid(row=99, column=0, columnspan=3, sticky="nsew", padx=50, pady=7)
        self.grid_rowconfigure(99, weight=1)
        # Row/column configs
        for i in range(2, next_row):
            self.grid_rowconfigure(i, weight=1)
        for j in range(3):
            self.grid_columnconfigure(j, weight=1)

    def open_admin_panel(self):
        import tkinter.ttk as ttk

        admin_win = tk.Toplevel(self)
        admin_win.title("Admin Panel" if self.lang == "EN" else "Panel Admina")
        admin_win.geometry("800x550")
        notebook = ttk.Notebook(admin_win)
        notebook.pack(fill="both", expand=True)

        # --- User Management Tab ---
        user_frame = tk.Frame(notebook)
        notebook.add(
            user_frame,
            text="User Management"
            if self.lang == "EN"
            else "Zarządzanie użytkownikami",
        )

        # --- Database Selection Tab (Admin only) ---
        import platform

        db_select_frame = tk.Frame(notebook)
        notebook.add(
            db_select_frame,
            text="Database File" if self.lang == "EN" else "Plik bazy danych",
        )
        tk.Label(
            db_select_frame,
            text="Current DB file:" if self.lang == "EN" else "Aktualny plik bazy:",
        ).grid(row=0, column=0, padx=10, pady=10, sticky="w")
        db_file_var = tk.StringVar(value=self.settings.get("db_file", "bookworm.db"))
        db_file_entry = tk.Entry(db_select_frame, textvariable=db_file_var, width=50)
        db_file_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        def select_db_file():
            from tkinter import filedialog

            filetypes = [("Database Files", "*.db"), ("All Files", "*.*")]
            selected = filedialog.askopenfilename(
                title="Select database file", filetypes=filetypes
            )
            if selected:
                db_file_var.set(selected)

        tk.Button(
            db_select_frame,
            text="Browse" if self.lang == "EN" else "Przeglądaj",
            command=select_db_file,
        ).grid(row=0, column=2, padx=10, pady=10)

        def save_db_file():
            self.settings["db_file"] = db_file_var.get()
            self.save_settings(self.settings)
            self._show_info_popup(
                "Database file changed" if self.lang == "EN" else "Zmieniono plik bazy",
                "Restart the app to use the new database file."
                if self.lang == "EN"
                else "Uruchom ponownie aplikację, aby użyć nowej bazy danych.",
                parent=admin_win,
            )

        tk.Button(
            db_select_frame,
            text="Save" if self.lang == "EN" else "Zapisz",
            command=save_db_file,
        ).grid(row=1, column=0, columnspan=3, padx=10, pady=10, sticky="ew")
        db_select_frame.grid_columnconfigure(1, weight=1)

        user_tree = ttk.Treeview(
            user_frame,
            columns=("id", "username", "is_admin", "privileges"),
            show="headings",
        )
        user_tree.heading("id", text="ID")
        user_tree.heading(
            "username", text="Username" if self.lang == "EN" else "Nazwa użytkownika"
        )
        user_tree.heading("is_admin", text="Admin" if self.lang == "EN" else "Admin")
        user_tree.heading(
            "privileges", text="Privileges" if self.lang == "EN" else "Uprawnienia"
        )
        user_tree.pack(fill="both", expand=True, padx=10, pady=10)

        def refresh_users():
            for row in user_tree.get_children():
                user_tree.delete(row)
            self.cursor.execute("SELECT id, username, is_admin, privileges FROM users")
            for row in self.cursor.fetchall():
                # Parse privileges for display
                privs = row[3] if row[3] else ""
                privs_disp = []
                if "db" in privs:
                    privs_disp.append("DB" if self.lang == "EN" else "Baza")
                if "reader" in privs:
                    privs_disp.append("Reader" if self.lang == "EN" else "Czytelnik")
                privs_str = (
                    ", ".join(privs_disp)
                    if privs_disp
                    else ("None" if self.lang == "EN" else "Brak")
                )
                user_tree.insert(
                    "",
                    "end",
                    values=(
                        row[0],
                        row[1],
                        ("Yes" if self.lang == "EN" else "Tak")
                        if row[2]
                        else ("No" if self.lang == "EN" else "Nie"),
                        privs_str,
                    ),
                )

        def demote_user():
            selected = user_tree.selection()
            if not selected:
                return
            user_id = user_tree.item(selected[0])["values"][0]
            self.cursor.execute(
                "SELECT is_superadmin FROM users WHERE id=?", (user_id,)
            )
            result = self.cursor.fetchone()
            if result and result[0] == 1:
                tk.messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "Cannot demote SUPERADMIN user."
                    if self.lang == "EN"
                    else "Nie można zdegradować użytkownika SUPERADMIN.",
                )
                return
            self.cursor.execute("UPDATE users SET is_admin=0 WHERE id=?", (user_id,))
            self.conn.commit()
            self.log_action(
                self.get_user_id(self.username), f"promoted user_id={user_id} to admin"
            )
            refresh_users()

        def delete_user():
            selected = user_tree.selection()
            if not selected:
                return
            user_id = user_tree.item(selected[0])["values"][0]
            self.cursor.execute(
                "SELECT is_superadmin FROM users WHERE id=?", (user_id,)
            )
            result = self.cursor.fetchone()
            if result and result[0] == 1:
                tk.messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "Cannot delete SUPERADMIN user."
                    if self.lang == "EN"
                    else "Nie można usunąć użytkownika SUPERADMIN.",
                )
                return
            self.cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
            self.conn.commit()
            self.log_action(
                self.get_user_id(self.username), f"demoted user_id={user_id} from admin"
            )
            refresh_users()

        def delete_user():
            selected = user_tree.selection()
            if not selected:
                return
            user_id = user_tree.item(selected[0])["values"][0]
            if user_id == self.get_user_id(self.username):
                tk.messagebox.showwarning(
                    "Warning" if self.lang == "EN" else "Ostrzeżenie",
                    "You cannot delete your own account while logged in."
                    if self.lang == "EN"
                    else "Nie możesz usunąć własnego konta podczas zalogowania.",
                )
                return
            self.cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
            self.conn.commit()
            self.log_action(
                self.get_user_id(self.username), f"deleted user_id={user_id}"
            )
            refresh_users()

        btn_frame = tk.Frame(user_frame)
        btn_frame.pack(pady=5)
        tk.Button(
            btn_frame,
            text="Promote to Admin"
            if self.lang == "EN"
            else "Nadaj uprawnienia admina",
            command=promote_user,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Demote from Admin"
            if self.lang == "EN"
            else "Odbierz uprawnienia admina",
            command=demote_user,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Delete User" if self.lang == "EN" else "Usuń użytkownika",
            command=delete_user,
        ).pack(side="left", padx=5)

        # --- Privilege management buttons ---
        def grant_db():
            selected = user_tree.selection()
            if not selected:
                return
            user_id = user_tree.item(selected[0])["values"][0]
            self.cursor.execute("SELECT privileges FROM users WHERE id=?", (user_id,))
            privs = self.cursor.fetchone()[0] or ""
            if "db" not in privs:
                privs = (privs + ",db").strip(",")
                self.cursor.execute(
                    "UPDATE users SET privileges=? WHERE id=?", (privs, user_id)
                )
                self.conn.commit()
                self.log_action(
                    self.get_user_id(self.username), f"granted db to user_id={user_id}"
                )
            refresh_users()

        def revoke_db():
            selected = user_tree.selection()
            if not selected:
                return
            user_id = user_tree.item(selected[0])["values"][0]
            self.cursor.execute("SELECT privileges FROM users WHERE id=?", (user_id,))
            privs = self.cursor.fetchone()[0] or ""
            privs = ",".join([p for p in privs.split(",") if p and p != "db"])
            self.cursor.execute(
                "UPDATE users SET privileges=? WHERE id=?", (privs, user_id)
            )
            self.conn.commit()
            self.log_action(
                self.get_user_id(self.username), f"revoked db from user_id={user_id}"
            )
            refresh_users()

        def grant_reader():
            selected = user_tree.selection()
            if not selected:
                return
            user_id = user_tree.item(selected[0])["values"][0]
            self.cursor.execute("SELECT privileges FROM users WHERE id=?", (user_id,))
            privs = self.cursor.fetchone()[0] or ""
            if "reader" not in privs:
                privs = (privs + ",reader").strip(",")
                self.cursor.execute(
                    "UPDATE users SET privileges=? WHERE id=?", (privs, user_id)
                )
                self.conn.commit()
                self.log_action(
                    self.get_user_id(self.username),
                    f"granted reader to user_id={user_id}",
                )
            refresh_users()

        def revoke_reader():
            selected = user_tree.selection()
            if not selected:
                return
            user_id = user_tree.item(selected[0])["values"][0]
            self.cursor.execute("SELECT privileges FROM users WHERE id=?", (user_id,))
            privs = self.cursor.fetchone()[0] or ""
            privs = ",".join([p for p in privs.split(",") if p and p != "reader"])
            self.cursor.execute(
                "UPDATE users SET privileges=? WHERE id=?", (privs, user_id)
            )
            self.conn.commit()
            self.log_action(
                self.get_user_id(self.username),
                f"revoked reader from user_id={user_id}",
            )
            refresh_users()

        tk.Button(
            btn_frame,
            text="Grant DB" if self.lang == "EN" else "Nadaj bazę",
            command=grant_db,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Revoke DB" if self.lang == "EN" else "Odbierz bazę",
            command=revoke_db,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Grant Reader" if self.lang == "EN" else "Nadaj czytelnika",
            command=grant_reader,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Revoke Reader" if self.lang == "EN" else "Odbierz czytelnika",
            command=revoke_reader,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Refresh" if self.lang == "EN" else "Odśwież",
            command=refresh_users,
        ).pack(side="left", padx=5)
        refresh_users()

        # --- Database Management Tab ---
        db_frame = tk.Frame(notebook)
        notebook.add(
            db_frame,
            text="Database Management"
            if self.lang == "EN"
            else "Zarządzanie bazą danych",
        )

        def backup_db():
            import shutil
            from tkinter import filedialog

            db_path = self.db_path if hasattr(self, "db_path") else "bookworm.db"
            dest = filedialog.asksaveasfilename(
                defaultextension=".db", filetypes=[("Database Files", "*.db")]
            )
            if dest:
                shutil.copyfile(db_path, dest)
                tk.messagebox.showinfo("Backup", "Database backup successful.")

        def restore_db():
            import shutil
            from tkinter import filedialog

            src = filedialog.askopenfilename(filetypes=[("Database Files", "*.db")])
            db_path = self.db_path if hasattr(self, "db_path") else "bookworm.db"
            if src:
                shutil.copyfile(src, db_path)
                tk.messagebox.showinfo(
                    "Restore", "Database restored. Please restart the application."
                )

        tk.Button(
            db_frame,
            text="Backup Database" if self.lang == "EN" else "Utwórz kopię zapasową",
            command=backup_db,
        ).pack(pady=10)
        tk.Button(
            db_frame,
            text="Restore Database" if self.lang == "EN" else "Przywróć bazę danych",
            command=restore_db,
        ).pack(pady=10)

        # --- Logs Tab ---
        logs_frame = tk.Frame(notebook)
        notebook.add(
            logs_frame, text="Logs" if self.lang == "EN" else "Dziennik zdarzeń"
        )

        logs_tree = ttk.Treeview(
            logs_frame,
            columns=("id", "user_id", "action", "timestamp"),
            show="headings",
        )
        logs_tree.heading("id", text="ID")
        logs_tree.heading("user_id", text="User ID")
        logs_tree.heading("action", text="Action")
        logs_tree.heading("timestamp", text="Timestamp")
        logs_tree.pack(fill="both", expand=True, padx=10, pady=10)

        def refresh_logs():
            for row in logs_tree.get_children():
                logs_tree.delete(row)
            self.cursor.execute(
                "SELECT id, user_id, action, timestamp FROM logs ORDER BY id DESC"
            )
            for row in self.cursor.fetchall():
                logs_tree.insert("", "end", values=row)

        tk.Button(
            logs_frame,
            text="Refresh Logs" if self.lang == "EN" else "Odśwież dziennik",
            command=refresh_logs,
        ).pack(pady=5)
        refresh_logs()

        # --- Close Button ---
        tk.Button(
            admin_win,
            text="Close" if self.lang == "EN" else "Zamknij",
            command=admin_win.destroy,
        ).pack(side="bottom", pady=8)

    def open_reader_panel(self):
        import tkinter.ttk as ttk
        import platform

        reader_win = tk.Toplevel(self)
        reader_win.title("Reader Panel" if self.lang == "EN" else "Panel Czytelnika")
        reader_win.geometry("900x600")
        notebook = ttk.Notebook(reader_win)
        notebook.pack(fill="both", expand=True)

        # --- Add Reader Tab ---
        add_reader_frame = tk.Frame(notebook)
        notebook.add(
            add_reader_frame,
            text="Add Reader" if self.lang == "EN" else "Dodaj czytelnika",
        )

        tk.Label(add_reader_frame, text="Name:" if self.lang == "EN" else "Imię:").grid(
            row=0, column=0, padx=5, pady=5, sticky="e"
        )
        reader_name_var = tk.StringVar()
        tk.Entry(add_reader_frame, textvariable=reader_name_var).grid(
            row=0, column=1, padx=5, pady=5, sticky="w"
        )
        tk.Label(
            add_reader_frame, text="Surname:" if self.lang == "EN" else "Nazwisko:"
        ).grid(row=1, column=0, padx=5, pady=5, sticky="e")
        reader_surname_var = tk.StringVar()
        tk.Entry(add_reader_frame, textvariable=reader_surname_var).grid(
            row=1, column=1, padx=5, pady=5, sticky="w"
        )
        tk.Label(
            add_reader_frame, text="Grade:" if self.lang == "EN" else "Klasa:"
        ).grid(row=2, column=0, padx=5, pady=5, sticky="e")
        reader_grade_var = tk.StringVar()
        tk.Entry(add_reader_frame, textvariable=reader_grade_var).grid(
            row=2, column=1, padx=5, pady=5, sticky="w"
        )

        def add_reader():
            name = reader_name_var.get().strip()
            surname = reader_surname_var.get().strip()
            grade = reader_grade_var.get().strip()
            if not name or not surname or not grade:
                tk.messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "All fields are required"
                    if self.lang == "EN"
                    else "Wszystkie pola są wymagane",
                )
                return
            self.cursor.execute(
                "INSERT INTO readers (name, surname, grade) VALUES (?, ?, ?)",
                (name, surname, grade),
            )
            self.conn.commit()
            self.log_action(
                self.get_user_id(self.username),
                f"added reader: {name} {surname}, grade: {grade}",
            )
            self._show_info_popup(
                "Reader Added" if self.lang == "EN" else "Dodano czytelnika",
                "Reader has been added."
                if self.lang == "EN"
                else "Czytelnik został dodany.",
                parent=reader_win,
            )
            reader_name_var.set("")
            reader_surname_var.set("")
            reader_grade_var.set("")
            load_readers_books()

        tk.Button(
            add_reader_frame,
            text="Add Reader" if self.lang == "EN" else "Dodaj czytelnika",
            command=add_reader,
        ).grid(row=3, column=0, columnspan=2, pady=10)

        # --- Search/Filter Readers ---
        search_label = tk.Label(
            add_reader_frame, text="Search:" if self.lang == "EN" else "Szukaj:"
        )
        search_label.grid(row=4, column=0, padx=5, pady=5, sticky="e")
        search_var = tk.StringVar()
        search_entry = tk.Entry(add_reader_frame, textvariable=search_var)
        search_entry.grid(row=4, column=1, padx=5, pady=5, sticky="w")

        # Readers List
        readers_tree = ttk.Treeview(
            add_reader_frame,
            columns=("id", "name", "surname", "grade"),
            show="headings",
        )
        readers_tree.heading("id", text="ID")
        readers_tree.heading("name", text="Name" if self.lang == "EN" else "Imię")
        readers_tree.heading(
            "surname", text="Surname" if self.lang == "EN" else "Nazwisko"
        )
        readers_tree.heading("grade", text="Grade" if self.lang == "EN" else "Klasa")
        readers_tree.grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
        add_reader_frame.grid_rowconfigure(5, weight=1)
        add_reader_frame.grid_columnconfigure(1, weight=1)

        def refresh_readers_list(filter_text=""):
            readers_tree.delete(*readers_tree.get_children())
            self.cursor.execute("SELECT id, name, surname, grade FROM readers")
            all_readers = self.cursor.fetchall()
            filter_text = filter_text.lower()
            for r in all_readers:
                # Allow search in both EN and PL fields
                values = [str(x).lower() for x in r]
                if filter_text in "".join(values):
                    readers_tree.insert("", "end", values=r)

        def on_search_readers(*args):
            refresh_readers_list(search_var.get())

        search_var.trace_add("write", on_search_readers)
        refresh_readers_list()

        # --- Assign Books Tab ---
        assign_frame = tk.Frame(notebook)
        notebook.add(
            assign_frame,
            text="Assign Book" if self.lang == "EN" else "Przypisz książkę",
        )

        # Readers dropdown
        tk.Label(
            assign_frame,
            text="Select Reader:" if self.lang == "EN" else "Wybierz czytelnika:",
        ).grid(row=0, column=0, padx=5, pady=5, sticky="e")
        # Replace reader dropdown with table for selection
        readers_tree = ttk.Treeview(
            assign_frame,
            columns=("ID", "Name", "Surname", "Grade"),
            show="headings",
            height=8,
        )
        if self.lang == "PL":
            readers_tree.heading("ID", text="ID")
            readers_tree.heading("Name", text="Imię")
            readers_tree.heading("Surname", text="Nazwisko")
            readers_tree.heading("Grade", text="Klasa")
        else:
            readers_tree.heading("ID", text="ID")
            readers_tree.heading("Name", text="Name")
            readers_tree.heading("Surname", text="Surname")
            readers_tree.heading("Grade", text="Grade")
        for col in ("ID", "Name", "Surname", "Grade"):
            readers_tree.column(col, width=120)
        readers_tree.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.cursor.execute("SELECT id, name, surname, grade FROM readers")
        for row in self.cursor.fetchall():
            readers_tree.insert("", "end", values=row)

        # Books dropdown
        tk.Label(
            assign_frame,
            text="Select Book:" if self.lang == "EN" else "Wybierz książkę:",
        ).grid(row=1, column=0, padx=5, pady=5, sticky="e")
        # Replace book dropdown with table for selection
        books_tree = ttk.Treeview(
            assign_frame,
            columns=("ID", "Title", "Author", "Year", "Genre", "Status"),
            show="headings",
            height=8,
        )
        if self.lang == "PL":
            books_tree.heading("ID", text="ID")
            books_tree.heading("Title", text="Tytuł")
            books_tree.heading("Author", text="Autor")
            books_tree.heading("Year", text="Rok")
            books_tree.heading("Genre", text="Gatunek")
            books_tree.heading("Status", text="Status")
        else:
            books_tree.heading("ID", text="ID")
            books_tree.heading("Title", text="Title")
            books_tree.heading("Author", text="Author")
            books_tree.heading("Year", text="Year")
            books_tree.heading("Genre", text="Genre")
            books_tree.heading("Status", text="Status")
        for col in ("ID", "Title", "Author", "Year", "Genre", "Status"):
            books_tree.column(col, width=100)
        books_tree.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.cursor.execute("SELECT ID, Title, Author, Year, Genre, Status FROM Books")
        for row in self.cursor.fetchall():
            # Localize status for Polish
            if self.lang == "PL":
                status_map = {
                    "borrowed": "pożyczone",
                    "returned": "zwrócone",
                    "missing": "brak",
                    "available": "dostępna",
                    "lost": "zagubione",
                    "other": "inne",
                }
                localized_row = list(row)
                status_val = str(localized_row[5]).lower()
                localized_row[5] = status_map.get(status_val, localized_row[5])
                books_tree.insert("", "end", values=localized_row)
            else:
                books_tree.insert("", "end", values=row)

        def load_readers_books():
            # Refresh tables for readers and books
            readers_tree.delete(*readers_tree.get_children())
            self.cursor.execute("SELECT id, name, surname, grade FROM readers")
            for row in self.cursor.fetchall():
                readers_tree.insert("", "end", values=row)
            # Localize book table headers
            if self.lang == "PL":
                books_tree.heading("ID", text="ID")
                books_tree.heading("Title", text="Tytuł")
                books_tree.heading("Author", text="Autor")
                books_tree.heading("Year", text="Rok")
                books_tree.heading("Genre", text="Gatunek")
                books_tree.heading("Status", text="Status")
            else:
                books_tree.heading("ID", text="ID")
                books_tree.heading("Title", text="Title")
                books_tree.heading("Author", text="Author")
                books_tree.heading("Year", text="Year")
                books_tree.heading("Genre", text="Genre")
                books_tree.heading("Status", text="Status")
            books_tree.delete(*books_tree.get_children())
            self.cursor.execute(
                "SELECT ID, Title, Author, Year, Genre, Status FROM Books"
            )
            for row in self.cursor.fetchall():
                books_tree.insert("", "end", values=row)
            # Also refresh readers list in add_reader tab
            if (
                "refresh_readers_list" in locals()
                or "refresh_readers_list" in globals()
            ):
                refresh_readers_list(search_var.get())

        def assign_book():
            selected_reader = readers_tree.selection()
            selected_book = books_tree.selection()
            if not selected_reader or not selected_book:
                tk.messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "Select both reader and book."
                    if self.lang == "EN"
                    else "Wybierz czytelnika i książkę.",
                )
                return
            reader_id = readers_tree.item(selected_reader[0])["values"][0]
            book_id = books_tree.item(selected_book[0])["values"][0]
            now = datetime.datetime.now().isoformat()
            self.cursor.execute(
                "INSERT INTO borrowed_books (book_id, reader_id, borrow_date, status) VALUES (?, ?, ?, ?)",
                (book_id, reader_id, now, "borrowed"),
            )
            self.conn.commit()
            self.log_action(
                self.get_user_id(self.username),
                f"assigned book_id={book_id} to reader_id={reader_id}",
            )
            self._show_info_popup(
                "Assigned" if self.lang == "EN" else "Przypisano",
                "Book assigned to reader."
                if self.lang == "EN"
                else "Książka przypisana do czytelnika.",
                parent=reader_win,
            )
            refresh_loans()

        tk.Button(
            assign_frame,
            text="Assign Book" if self.lang == "EN" else "Przypisz książkę",
            command=assign_book,
        ).grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(
            assign_frame,
            text="Refresh Lists" if self.lang == "EN" else "Odśwież listy",
            command=load_readers_books,
        ).grid(row=3, column=0, columnspan=2, pady=5)
        load_readers_books()

        # --- Manage Loans Tab ---
        loans_frame = tk.Frame(notebook)
        notebook.add(
            loans_frame,
            text="Manage Loans" if self.lang == "EN" else "Zarządzaj wypożyczeniami",
        )

        loans_tree = ttk.Treeview(
            loans_frame,
            columns=(
                "id",
                "book_id",
                "reader_id",
                "borrow_date",
                "return_date",
                "status",
            ),
            show="headings",
        )
        col_titles = {
            "id": "ID",
            "book_id": "Book ID" if self.lang == "EN" else "ID książki",
            "reader_id": "Reader ID" if self.lang == "EN" else "ID czytelnika",
            "borrow_date": "Borrow Date" if self.lang == "EN" else "Data wypożyczenia",
            "return_date": "Return Date" if self.lang == "EN" else "Data zwrotu",
            "status": "Status" if self.lang == "EN" else "Status",
        }
        for col in (
            "id",
            "book_id",
            "reader_id",
            "borrow_date",
            "return_date",
            "status",
        ):
            loans_tree.heading(col, text=col_titles[col])
        loans_tree.pack(fill="both", expand=True, padx=10, pady=10)

        def refresh_loans():
            for row in loans_tree.get_children():
                loans_tree.delete(row)
            self.cursor.execute(
                "SELECT id, book_id, reader_id, borrow_date, return_date, status FROM borrowed_books ORDER BY id DESC"
            )
            for row in self.cursor.fetchall():
                # Localize status for Polish
                if self.lang == "PL":
                    status_map = {
                        "borrowed": "pożyczone",
                        "returned": "zwrócone",
                        "missing": "brak",
                        "available": "dostępna",
                        "lost": "zagubione",
                        "other": "inne",
                    }
                    localized_row = list(row)
                    status_val = str(localized_row[5]).lower()
                    localized_row[5] = status_map.get(status_val, localized_row[5])
                    loans_tree.insert("", "end", values=localized_row)
                else:
                    loans_tree.insert("", "end", values=row)

        def mark_returned():
            selected = loans_tree.selection()
            if not selected:
                return
            loan_id = loans_tree.item(selected[0])["values"][0]
            import datetime

            now = datetime.datetime.now().isoformat()
            status_returned = "returned" if self.lang == "EN" else "zwrócona"
            self.cursor.execute(
                "UPDATE borrowed_books SET status=?, return_date=? WHERE id=?",
                (status_returned, now, loan_id),
            )
            self.conn.commit()
            self.log_action(
                self.get_user_id(self.username), f"marked loan_id={loan_id} as returned"
            )
            refresh_loans()

        def mark_lost():
            selected = loans_tree.selection()
            if not selected:
                return
            loan_id = loans_tree.item(selected[0])["values"][0]
            self.cursor.execute(
                "UPDATE borrowed_books SET status=? WHERE id=?",
                ("lost", loan_id),
            )
            self.conn.commit()
            self.log_action(
                self.get_user_id(self.username), f"marked loan_id={loan_id} as lost"
            )
            refresh_loans()

        btn_frame = tk.Frame(loans_frame)
        btn_frame.pack(pady=5)
        tk.Button(
            btn_frame,
            text="Mark as Returned" if self.lang == "EN" else "Oznacz jako zwrócone",
            command=mark_returned,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Mark as Lost" if self.lang == "EN" else "Oznacz jako zagubione",
            command=mark_lost,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Refresh Loans" if self.lang == "EN" else "Odśwież wypożyczenia",
            command=refresh_loans,
        ).pack(side="left", padx=5)
        refresh_loans()

        # --- Close Button ---
        tk.Button(
            reader_win,
            text="Close" if self.lang == "EN" else "Zamknij",
            command=reader_win.destroy,
        ).pack(side="bottom", pady=8)

    def _show_info_popup(self, title, message, parent=None):
        import platform

        is_linux = platform.system().lower() == "linux"
        popups = self.settings.get("popups", True)
        if is_linux and not popups:
            return
        # Always bring popup to front
        info = tk.Toplevel(parent or self)
        info.title(title)
        info.geometry("350x120")
        info.grab_set()
        info.lift()
        info.attributes("-topmost", True)
        tk.Label(info, text=message, font=("Arial", 12)).pack(pady=20)
        tk.Button(info, text="OK", command=info.destroy).pack(pady=5)
        info.after(100, lambda: info.lift())

    def show_settings(self):
        win = tk.Toplevel(self)
        win.title("Settings" if self.lang == "EN" else "Ustawienia")
        win.geometry("400x400")
        win.grab_set()
        lbl_theme = tk.Label(
            win, text="Select Theme:" if self.lang == "EN" else "Wybierz motyw:"
        )
        lbl_theme.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        theme_var = tk.StringVar(value=self.settings.get("theme", "classic_blue"))
        theme_names = list(self.themes.keys())
        theme_cb = ttk.Combobox(
            win, values=theme_names, state="readonly", textvariable=theme_var
        )
        theme_cb.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        lbl_lang = tk.Label(
            win, text="Default Language:" if self.lang == "EN" else "Język domyślny:"
        )
        lbl_lang.grid(row=1, column=0, padx=10, pady=10, sticky="w")
        lang_var = tk.StringVar(value=self.settings.get("default_language", "EN"))
        lang_cb = ttk.Combobox(
            win, values=["EN", "PL"], state="readonly", textvariable=lang_var
        )
        lang_cb.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        # Add database import button
        def import_db():
            import shutil
            from tkinter import filedialog
            import os

            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            src = filedialog.askopenfilename(
                initialdir=desktop,
                filetypes=[("Encrypted Database Files", "*.db.enc")],
                title="Import encrypted database file",
            )
            db_path = (
                self.db_decrypted_path
                if hasattr(self, "db_decrypted_path")
                else "bookworm.db"
            )
            if src:
                shutil.copyfile(src, db_path)
                tk.messagebox.showinfo(
                    "Restore", "Database imported. Please restart the application."
                )

        tk.Button(
            win,
            text="Import Database" if self.lang == "EN" else "Importuj bazę danych",
            command=import_db,
        ).grid(row=5, column=0, columnspan=2, pady=10, sticky="ew")

        # Popups toggle for Linux
        import platform

        is_linux = platform.system().lower() == "linux"
        popups_var = tk.BooleanVar(value=self.settings.get("popups", True))
        if is_linux:
            lbl_popups = tk.Label(
                win,
                text="Show popups (info/warning):"
                if self.lang == "EN"
                else "Pokazuj okienka (info/ostrzeżenia):",
            )
            lbl_popups.grid(row=2, column=0, padx=10, pady=10, sticky="w")
            popups_cb = ttk.Checkbutton(win, variable=popups_var)
            popups_cb.grid(row=2, column=1, padx=10, pady=10, sticky="w")

        def save_settings():
            self.settings["theme"] = theme_var.get()
            self.settings["default_language"] = lang_var.get()
            if is_linux:
                self.settings["popups"] = popups_var.get()
            self.save_settings(self.settings)
            self.load_custom_themes()
            self.set_theme(self.settings["theme"])
            messagebox.showinfo(
                "Settings Saved" if self.lang == "EN" else "Zapisano ustawienia",
                "Settings have been saved. Restart app to apply changes."
                if self.lang == "EN"
                else "Ustawienia zostały zapisane. Uruchom ponownie aplikację, aby zastosować zmiany.",
            )
            win.destroy()

        def run_theme_creator():
            themecreator_file, ver = find_latest_version_executable("themecreator")
            if not themecreator_file:
                messagebox.showinfo(
                    "Not Found" if self.lang == "EN" else "Nie znaleziono",
                    "Theme creator executable not found. Please install it."
                    if self.lang == "EN"
                    else "Nie znaleziono programu do tworzenia motywów. Proszę zainstalować.",
                )
                return
            try:
                subprocess.Popen([os.path.abspath(themecreator_file)], shell=True)
            except Exception as e:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    f"Failed to launch theme creator:\n{e}"
                    if self.lang == "EN"
                    else f"Nie udało się uruchomić programu do tworzenia motywów:\n{e}",
                )

        btn_save = tk.Button(
            win,
            text="Save" if self.lang == "EN" else "Zapisz",
            bg=self.BTN_BG,
            fg=self.BTN_FG,
            activebackground=self.BTN_HOVER_BG,
            activeforeground=self.BTN_HOVER_FG,
            font=("Segoe UI", 12, "bold"),
            command=save_settings,
        )
        btn_save.grid(row=3, column=0, columnspan=2, pady=30, sticky="ew")

        btn_theme_creator = tk.Button(
            win,
            text="Create New Theme" if self.lang == "EN" else "Nowy motyw",
            bg=self.BTN_BG,
            fg=self.BTN_FG,
            activebackground=self.BTN_HOVER_BG,
            activeforeground=self.BTN_HOVER_FG,
            font=("Segoe UI", 11, "bold"),
            command=run_theme_creator,
        )
        btn_theme_creator.grid(row=4, column=0, columnspan=2, pady=0, sticky="ew")

        win.grid_columnconfigure(1, weight=1)


if __name__ == "__main__":
    app = BookwormApp()
    app.mainloop()
