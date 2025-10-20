import os
import shutil
import glob
import winreg

def get_desktop():
    # Get the path to the user's desktop
    return os.path.join(os.path.expanduser("~"), "Desktop")

def backup_files(inst_dir, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    for pattern in ["*.sqlite.enc", "*.sqlite", "*.json"]:
        for file in glob.glob(os.path.join(inst_dir, pattern)):
            shutil.copy2(file, backup_dir)

def move_folder(inst_dir, backup_dir, folder_name):
    src = os.path.join(inst_dir, folder_name)
    dst = os.path.join(backup_dir, folder_name)
    if os.path.isdir(src):
        shutil.move(src, dst)

def delete_files(inst_dir, patterns):
    for pattern in patterns:
        for file in glob.glob(os.path.join(inst_dir, pattern)):
            try:
                os.remove(file)
            except Exception:
                pass

def delete_file(path):
    try:
        os.remove(path)
    except Exception:
        pass

def remove_directory(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)

def delete_registry_key():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Bookworm")
    except FileNotFoundError:
        pass
    except Exception:
        pass

def main():
    inst_dir = os.path.abspath(os.path.dirname(__file__))  # Or set this explicitly
    desktop = get_desktop()
    backup_dir = os.path.join(desktop, "bookworm_backup")

    backup_files(inst_dir, backup_dir)
    for folder in ["themes", "settings", "book"]:
        move_folder(inst_dir, backup_dir, folder)

    # Delete executables (version-agnostic)
    delete_files(inst_dir, ["bookworm_gui_v*.exe", "updater_v*.exe", "themecreator_v*.exe"])
    delete_file(os.path.join(inst_dir, "LICENSE.txt"))
    delete_file(os.path.join(inst_dir, "Uninstall.exe"))

    # Delete desktop shortcut
    delete_file(os.path.join(desktop, "Bookworm.lnk"))

    # Remove install directory
    remove_directory(inst_dir)

    # Remove uninstall registry key
    delete_registry_key()

if __name__ == "__main__":
    main()
