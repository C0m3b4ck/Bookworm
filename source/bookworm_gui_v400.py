import os
import json
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import re
import subprocess
import sqlite3
import tempfile
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken

SETTINGS_FILE = "settings.json"
THEMES_FOLDER = "themes"

DEFAULT_SETTINGS = {
    "default_language": None,  # if None, prompt each time
    "theme": "classic_blue"
}

DEFAULT_THEMES = {
    "classic_blue": {
        "BTN_BG": "#add8e6",  # light blue
        "BTN_FG": "#333333",  # dark grey
        "BTN_HOVER_BG": "#6495ed",  # cornflower blue
        "BTN_HOVER_FG": "#f0f0f0",  # lighter text
    },
    "dark_mode": {
        "BTN_BG": "#444444",
        "BTN_FG": "#ffffff",
        "BTN_HOVER_BG": "#666666",
        "BTN_HOVER_FG": "#ffff00",
    }
}

# Helper functions for encryption key from username+password
def generate_key(username: str, password: str) -> bytes:
    # Use SHA256 to hash username+password, then base64 encode for Fernet key
    combined = (username + password).encode("utf-8")
    hash_digest = hashlib.sha256(combined).digest()
    return base64.urlsafe_b64encode(hash_digest)

# Encrypt a file content with the key, write to file
def encrypt_file(input_path: str, output_path: str, key: bytes):
    fernet = Fernet(key)
    with open(input_path, "rb") as file:
        data = file.read()
    encrypted = fernet.encrypt(data)
    with open(output_path, "wb") as file:
        file.write(encrypted)

# Decrypt a file content with the key, write to file
def decrypt_file(input_path: str, output_path: str, key: bytes) -> bool:
    fernet = Fernet(key)
    try:
        with open(input_path, "rb") as file:
            encrypted = file.read()
        decrypted = fernet.decrypt(encrypted)
        with open(output_path, "wb") as file:
            file.write(decrypted)
        return True
    except (InvalidToken, FileNotFoundError):
        return False

# SQLite schema creation for books
BOOKS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS Books (
    ID INTEGER,
    Title TEXT NOT NULL,
    Author TEXT,
    Year TEXT,
    Genre TEXT,
    Status TEXT,
    BookRow TEXT,
    PRIMARY KEY(ID)
);
"""

REMOVED_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS RemovedBooks (
    ID INTEGER,
    Title TEXT,
    Author TEXT,
    Year TEXT,
    Genre TEXT,
    Status TEXT,
    BookRow TEXT,
    PRIMARY KEY(ID)
);
"""

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
    pattern = re.compile(rf"^{prefix}_v(\d+)\.exe$", re.IGNORECASE)
    best_version = -1
    best_path = None
    for root, dirs, files in os.walk("."):
        for file in files:
            match = pattern.match(file)
            if match:
                ver = int(match.group(1))
                if ver > best_version:
                    best_version = ver
                    best_path = os.path.join(root, file)
    return best_path, best_version

class BookwormApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bookworm")
        self.geometry("750x520")
        self.minsize(600, 450)
        self.settings = self.load_settings()
        self.themes = DEFAULT_THEMES.copy()
        self.load_custom_themes()
        theme_name = self.settings.get("theme", "classic_blue")
        self.set_theme(theme_name)
        self.lang = self.settings.get("default_language")
        self.db_encrypted_path = None  # encrypted sqlite file path
        self.db_decrypted_path = None  # temporary decrypted sqlite path
        self.conn = None  # sqlite3 connection
        self.username = None
        self.password = None
        if self.lang not in ("EN", "PL"):
            self.create_language_selection()
        else:
            self.prompt_login_register()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.close_db()
        self.destroy()

    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            self.save_settings(DEFAULT_SETTINGS)
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

    def set_theme(self, name):
        theme = self.themes.get(name, self.themes["classic_blue"])
        self.BTN_BG = theme["BTN_BG"]
        self.BTN_FG = theme["BTN_FG"]
        self.BTN_HOVER_BG = theme["BTN_HOVER_BG"]
        self.BTN_HOVER_FG = theme["BTN_HOVER_FG"]

    def create_high_contrast_button(self, parent, text, command=None):
        btn = tk.Button(parent, text=text, bg=self.BTN_BG, fg=self.BTN_FG,
                        activebackground=self.BTN_HOVER_BG, activeforeground=self.BTN_HOVER_FG,
                        font=("Segoe UI", 12, "bold"), command=command, relief="raised", bd=3)
        btn.bind("<Enter>", lambda e: btn.config(bg=self.BTN_HOVER_BG, fg=self.BTN_HOVER_FG))
        btn.bind("<Leave>", lambda e: btn.config(bg=self.BTN_BG, fg=self.BTN_FG))
        return btn

    def create_language_selection(self):
        for widget in self.winfo_children():
            widget.destroy()
        tk.Label(self, text="Select language / wybierz język", font=("Arial", 18)).grid(row=0, column=0, columnspan=2, pady=20)
        btn_en = self.create_high_contrast_button(self, "English", lambda: self.set_language_and_prompt_login("EN"))
        btn_en.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        btn_pl = self.create_high_contrast_button(self, "Polski", lambda: self.set_language_and_prompt_login("PL"))
        btn_pl.grid(row=1, column=1, sticky="nsew", padx=10, pady=5)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

    def set_language_and_prompt_login(self, lang):
        self.lang = lang
        self.settings["default_language"] = lang
        self.save_settings(self.settings)
        self.prompt_login_register()

    def prompt_login_register(self):
        # Clear widgets
        for widget in self.winfo_children():
            widget.destroy()
        tk.Label(self, text="Login / Register", font=("Arial", 18)).grid(row=0, column=0, columnspan=2, pady=20)

        tk.Label(self, text="Username:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        username_entry = tk.Entry(self)
        username_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        tk.Label(self, text="Password:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        password_entry = tk.Entry(self, show="*")
        password_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        def try_login():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            if not username or not password:
                messagebox.showerror("Error" if self.lang == "EN" else "Błąd",
                                     "Username and password required" if self.lang == "EN" else "Wymagane są nazwa użytkownika i hasło")
                return
            self.username = username
            self.password = password
            success = self.load_or_create_encrypted_db()
            if success:
                self.create_main_menu()
            else:
                messagebox.showerror("Error" if self.lang == "EN" else "Błąd",
                                     "Invalid username or password" if self.lang == "EN" else "Nieprawidłowa nazwa użytkownika lub hasło")
                self.username = None
                self.password = None

        def try_register():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            if not username or not password:
                messagebox.showerror("Error" if self.lang == "EN" else "Błąd",
                                     "Username and password required" if self.lang == "EN" else "Wymagane są nazwa użytkownika i hasło")
                return
            self.username = username
            self.password = password
            if self.db_encrypted_file_exists():
                messagebox.showerror("Error" if self.lang == "EN" else "Błąd",
                                     "User already exists" if self.lang == "EN" else "Użytkownik już istnieje")
                return
            self.create_new_encrypted_db()
            self.create_main_menu()

        btn_login = self.create_high_contrast_button(self, "Login" if self.lang == "EN" else "Zaloguj", try_login)
        btn_login.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)

        btn_register = self.create_high_contrast_button(self, "Register" if self.lang == "EN" else "Zarejestruj", try_register)
        btn_register.grid(row=3, column=1, sticky="nsew", padx=10, pady=10)

        self.grid_columnconfigure(1, weight=1)

    def db_encrypted_file_exists(self):
        self.db_encrypted_path = f"books_{self.lang.lower()}_{self.username}.sqlite.enc"
        return os.path.exists(self.db_encrypted_path)

    def load_or_create_encrypted_db(self):
        # Decide encrypted path from username
        self.db_encrypted_path = f"books_{self.lang.lower()}_{self.username}.sqlite.enc"
        self.db_decrypted_path = tempfile.mktemp(suffix=".sqlite")
        if not os.path.exists(self.db_encrypted_path):
            # No encrypted DB, create new unencrypted SQLite DB file and encrypt it
            self.create_new_encrypted_db()
            return True
        # Try decrypt file with given username+password
        key = generate_key(self.username, self.password)
        if not decrypt_file(self.db_encrypted_path, self.db_decrypted_path, key):
            # Failed decryption
            if os.path.exists(self.db_decrypted_path):
                os.remove(self.db_decrypted_path)
            return False
        try:
            self.conn = sqlite3.connect(self.db_decrypted_path)
            cur = self.conn.cursor()
            # Check if Books table exists by running a dummy query
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Books';")
            if not cur.fetchone():
                cur.execute(BOOKS_TABLE_SCHEMA)
                self.conn.commit()
            # Also ensure RemovedBooks table
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='RemovedBooks';")
            if not cur.fetchone():
                cur.execute(REMOVED_TABLE_SCHEMA)
                self.conn.commit()
            return True
        except Exception:
            return False

    def create_new_encrypted_db(self):
        # Create new SQLite DB file in temporary path
        self.db_decrypted_path = tempfile.mktemp(suffix=".sqlite")
        if os.path.exists(self.db_decrypted_path):
            os.remove(self.db_decrypted_path)
        self.conn = sqlite3.connect(self.db_decrypted_path)
        cur = self.conn.cursor()
        cur.execute(BOOKS_TABLE_SCHEMA)
        cur.execute(REMOVED_TABLE_SCHEMA)
        self.conn.commit()
        # Encrypt DB to encrypted path file
        key = generate_key(self.username, self.password)
        self.db_encrypted_path = f"books_{self.lang.lower()}_{self.username}.sqlite.enc"
        encrypt_file(self.db_decrypted_path, self.db_encrypted_path, key)
        # Remove decrypted temp file after encrypting
        if os.path.exists(self.db_decrypted_path):
            os.remove(self.db_decrypted_path)
        # Reopen connection on decrypted file for use (decrypt again to file)
        self.db_decrypted_path = tempfile.mktemp(suffix=".sqlite")
        decrypt_file(self.db_encrypted_path, self.db_decrypted_path, key)
        self.conn = sqlite3.connect(self.db_decrypted_path)

    def close_db(self):
        if self.conn:
            self.conn.commit()
            self.conn.close()
            self.conn = None
        # Encrypt decrypted database back before closing app
        if self.db_decrypted_path and self.db_encrypted_path and self.username and self.password:
            key = generate_key(self.username, self.password)
            encrypt_file(self.db_decrypted_path, self.db_encrypted_path, key)
            try:
                os.remove(self.db_decrypted_path)
            except Exception:
                pass

    def create_main_menu(self):
        for widget in self.winfo_children():
            widget.destroy()
        credits_text = ("Made by C0m3b4ck under APL 2.0 license"
                        if self.lang == "EN" else "Stworzone przez C0m3b4ck pod licencją APL 2.0")
        label_text = "Main Menu" if self.lang == "EN" else "Menu główne"
        tk.Label(self, text=label_text, font=("Arial", 20)).grid(row=0, column=0, columnspan=3, pady=10)
        tk.Label(self, text=credits_text, font=("Arial", 10, "italic")).grid(row=1, column=0, columnspan=3, pady=5)

        options = {
            "EN": ["Add New Book", "See/Modify Books", "Help", "Update", "Settings", "Logout", "Exit"],
            "PL": ["Dodaj książkę", "Obejrzyj/modyfikuj książki", "Pomoc", "Aktualizuj", "Ustawienia", "Wyloguj", "Zakończ"]
        }
        commands = [
            lambda: self.add_new_book_form(),
            lambda: self.see_modify_books(),
            lambda: self.show_help(),
            lambda: self.run_updater(),
            lambda: self.show_settings(),
            lambda: self.logout(),
            lambda: self.quit()
        ]
        for i, (option, command) in enumerate(zip(options[self.lang], commands), start=2):
            btn = self.create_high_contrast_button(self, option, command=command)
            btn.grid(row=i, column=0, columnspan=3, sticky="nsew", padx=50, pady=7)
        for i in range(2, 9):
            self.grid_rowconfigure(i, weight=1)
        for j in range(3):
            self.grid_columnconfigure(j, weight=1)

    def logout(self):
        self.close_db()
        self.username = None
        self.password = None
        self.create_language_selection()

    def run_updater(self):
        updater_file, ver = find_latest_version_executable("updater")
        if not updater_file:
            messagebox.showinfo("Updater Not Found" if self.lang == "EN" else "Updater nie znaleziony",
                                "Updater executable not found. Please install/update manually."
                                if self.lang == "EN" else "Nie znaleziono programu aktualizującego. Proszę zainstalować/zaktualizować ręcznie.")
            return
        try:
            subprocess.Popen([os.path.abspath(updater_file)], shell=True)
        except Exception as e:
            messagebox.showerror("Error" if self.lang == "EN" else "Błąd",
                                 f"Failed to launch updater:\n{e}" if self.lang == "EN" else f"Nie udało się uruchomić aktualizatora:\n{e}")

    def add_new_book_form(self):
        form = tk.Toplevel(self)
        form.title("Add New Book" if self.lang == "EN" else "Dodaj nową książkę")
        form.geometry("460x390")
        form.grab_set()
        labels = {
            "EN": ["ID (0 may repeat)", "Title", "Author", "Year", "Genre", "Status", "Book Row"],
            "PL": ["ID (0 może się powtarzać)", "Tytuł", "Autor", "Rok", "Gatunek", "Status", "Regał książkowy"],
        }
        status_options = {
            "EN": ["borrowed", "available", "missing", "other"],
            "PL": ["wypożyczona", "dostępna", "brak", "inne"],
        }
        entries = {}
        for i, text in enumerate(labels[self.lang]):
            lbl = tk.Label(form, text=text, anchor="w")
            lbl.grid(row=i, column=0, padx=10, pady=8, sticky="w")
            if text == "Status" or text == "Status":
                cmb = ttk.Combobox(form, values=status_options[self.lang], state="readonly")
                cmb.grid(row=i, column=1, padx=10, pady=8, sticky="ew")
                cmb.current(1)  # Default to "available"
                entries[text] = cmb
            else:
                ent = tk.Entry(form)
                ent.grid(row=i, column=1, padx=10, pady=8, sticky="ew")
                entries[text] = ent
                ent.bind("<Return>", lambda e, i=i: self.entry_return_key(entries, labels[self.lang], i))
                ent.bind("<BackSpace>", lambda e, i=i: self.entry_backspace_key(e, entries, labels[self.lang], i))
                ent.bind("<Left>", lambda e, i=i: self.entry_arrow_key(e, entries, labels[self.lang], i, direction="left"))
                ent.bind("<Right>", lambda e, i=i: self.entry_arrow_key(e, entries, labels[self.lang], i, direction="right"))
                ent.bind("<Up>", lambda e, i=i: self.entry_arrow_key(e, entries, labels[self.lang], i, direction="up"))
                ent.bind("<Down>", lambda e, i=i: self.entry_arrow_key(e, entries, labels[self.lang], i, direction="down"))
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
                    "ID must be a number >= 0" if self.lang == "EN" else "ID musi być liczbą >= 0",
                )
                return
            existing_ids = self.get_existing_ids()
            if id_val != 0 and id_val in existing_ids:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "ID already exists or input 0 which may repeat" if self.lang == "EN" else "ID już istnieje lub wpisz 0, który może się powtarzać",
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
            book_row = entries[labels[self.lang][6]].get().strip()
            try:
                cur = self.conn.cursor()
                # SQLite upsert workaround: Try insert, if fail update
                cur.execute("INSERT OR REPLACE INTO Books (ID, Title, Author, Year, Genre, Status, BookRow) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (id_val, title, author, year, genre, status, book_row))
                self.conn.commit()
            except Exception as e:
                messagebox.showerror("Error" if self.lang == "EN" else "Błąd",
                                     f"Failed to add book: {e}")
                return
            messagebox.showinfo(
                "Success" if self.lang == "EN" else "Sukces",
                "Book added successfully." if self.lang == "EN" else "Książka dodana pomyślnie.",
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
        submit_btn.grid(row=len(labels[self.lang]), column=0, columnspan=2, pady=15, sticky="ew")
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
            "Search by ID", "Search by Title", "Search by Author", "Search by Year", "Search by Genre", "Search by Status", "Search"
        ]
        search_labels_pl = [
            "Szukaj po ID", "Szukaj po tytule", "Szukaj po autorze", "Szukaj po roku", "Szukaj po gatunku", "Szukaj po statusie", "Szukaj"
        ]
        search_labels = search_labels_en if self.lang == "EN" else search_labels_pl
        self.search_vars = {key: tk.StringVar() for key in search_labels[:-1]}
        self.sort_directions = {key: True for key in search_labels[:-1]}  # All ascending start

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
            tree.heading(col, text=heading, command=lambda c=col: self.sort_by_column(tree, c))
            tree.column(col, width=150 if col not in ("Year", "Status") else 80, stretch=True)
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
                    base_query += f" ORDER BY {sort_by} {'ASC' if ascending else 'DESC'}"
                cur.execute(base_query, params)
                rows = cur.fetchall()
                for row in rows:
                    vals = list(row)
                    if len(vals) < 6:
                        vals += [""] * (6 - len(vals))
                    tree.insert("", "end", values=vals)
            except Exception as e:
                messagebox.showerror("Error" if self.lang == "EN" else "Błąd", f"Failed to load data: {e}")

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
                messagebox.showwarning("Warning" if self.lang == "EN" else "Uwaga",
                                       "Select a book to edit" if self.lang == "EN" else "Wybierz książkę do edycji")
                return
            item = tree.item(selected[0])
            values = item["values"]
            self.edit_book(values[0])
            top.destroy()

        def on_remove():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Warning" if self.lang == "EN" else "Uwaga",
                                       "Select a book to remove" if self.lang == "EN" else "Wybierz książkę do usunięcia")
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
                cur.execute("""INSERT OR REPLACE INTO RemovedBooks
                            (ID, Title, Author, Year, Genre, Status)
                            VALUES (?, ?, ?, ?, ?, ?)""",
                            tuple(book_data))
                self.conn.commit()
            except Exception as e:
                messagebox.showerror("Error" if self.lang == "EN" else "Błąd",
                                     f"Failed to remove book: {e}")
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

        btn_close = tk.Button(btn_frame, text="Close" if self.lang == "EN" else "Zamknij", command=top.destroy)
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
            messagebox.showerror("Error" if self.lang == "EN" else "Błąd", f"Failed to sort data: {e}")

    def edit_book(self, book_id):
        cur = self.conn.cursor()
        cur.execute("SELECT ID, Title, Author, Year, Genre, Status, BookRow FROM Books WHERE ID = ?", (book_id,))
        row = cur.fetchone()
        if not row:
            messagebox.showerror("Error" if self.lang == "EN" else "Błąd", "Book not found" if self.lang == "EN" else "Książka nie znaleziona")
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
            "PL": ["ID (0 może się powtarzać)", "Tytuł", "Autor", "Rok", "Gatunek", "Status"],
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
                cmb = ttk.Combobox(form, values=status_options[self.lang], state="readonly")
                cmb.grid(row=i, column=1, padx=10, pady=8, sticky="ew")
                try:
                    cmb.current(status_options[self.lang].index(str(values_current[i]).casefold()))
                except Exception:
                    cmb.current(1)  # default to "available"
                entries[text] = cmb
            else:
                ent = tk.Entry(form)
                ent.grid(row=i, column=1, padx=10, pady=8, sticky="ew")
                ent.insert(0, values_current[i])
                entries[text] = ent
                ent.bind("<Return>", lambda e, i=i: self.entry_return_key(entries, labels[self.lang], i))
                ent.bind("<BackSpace>", lambda e, i=i: self.entry_backspace_key(e, entries, labels[self.lang], i))
                ent.bind("<Left>", lambda e, i=i: self.entry_arrow_key(e, entries, labels[self.lang], i, direction="left"))
                ent.bind("<Right>", lambda e, i=i: self.entry_arrow_key(e, entries, labels[self.lang], i, direction="right"))
                ent.bind("<Up>", lambda e, i=i: self.entry_arrow_key(e, entries, labels[self.lang], i, direction="up"))
                ent.bind("<Down>", lambda e, i=i: self.entry_arrow_key(e, entries, labels[self.lang], i, direction="down"))
        form.grid_columnconfigure(1, weight=1)

        def submit():
            try:
                id_val = int(entries[labels[self.lang][0]].get())
                if id_val < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "ID must be a number >= 0" if self.lang == "EN" else "ID musi być liczbą >= 0",
                )
                return
            existing_ids = self.get_existing_ids()
            if id_val != 0 and id_val in existing_ids and id_val != current["ID"]:
                messagebox.showerror(
                    "Error" if self.lang == "EN" else "Błąd",
                    "ID already exists or input 0 which may repeat" if self.lang == "EN" else "ID już istnieje lub wpisz 0, który może się powtarzać",
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
                cur.execute("""UPDATE Books SET ID=?, Title=?, Author=?, Year=?, Genre=?, Status=?
                            WHERE ID=?""",
                            (id_val, title, author, year, genre, status, current["ID"]))
                self.conn.commit()
            except Exception as e:
                messagebox.showerror("Error" if self.lang == "EN" else "Błąd",
                                     f"Failed to update book: {e}")
                return
            messagebox.showinfo(
                "Success" if self.lang == "EN" else "Sukces",
                "Book updated successfully." if self.lang == "EN" else "Książka zaktualizowana pomyślnie.",
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
        submit_btn.grid(row=len(labels[self.lang]), column=0, columnspan=2, pady=15, sticky="ew")
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
        messagebox.showinfo("Help" if self.lang == "EN" else "Pomoc",
                            help_text_en if self.lang == "EN" else help_text_pl)
        self.create_main_menu()

    def show_settings(self):
        win = tk.Toplevel(self)
        win.title("Settings" if self.lang == "EN" else "Ustawienia")
        win.geometry("400x300")
        win.grab_set()
        lbl_theme = tk.Label(win, text="Select Theme:" if self.lang == "EN" else "Wybierz motyw:")
        lbl_theme.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        theme_var = tk.StringVar(value=self.settings.get("theme", "classic_blue"))
        theme_names = list(self.themes.keys())
        theme_cb = ttk.Combobox(win, values=theme_names, state="readonly", textvariable=theme_var)
        theme_cb.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        lbl_lang = tk.Label(win, text="Default Language:" if self.lang == "EN" else "Język domyślny:")
        lbl_lang.grid(row=1, column=0, padx=10, pady=10, sticky="w")
        lang_var = tk.StringVar(value=self.settings.get("default_language", "EN"))
        lang_cb = ttk.Combobox(win, values=["EN", "PL"], state="readonly", textvariable=lang_var)
        lang_cb.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        def save_settings():
            self.settings["theme"] = theme_var.get()
            self.settings["default_language"] = lang_var.get()
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

