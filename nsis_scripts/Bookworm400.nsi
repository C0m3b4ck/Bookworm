; Bookworm400.nsi
Outfile "Bookworm400_installer.exe"
InstallDir "$LOCALAPPDATA\Programs\Bookworm"
RequestExecutionLevel user

Function .onInit
  SetShellVarContext current
FunctionEnd

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File "bookworm_gui_v400.exe"
  File "updater_v100.exe"
  File "themecreator_v100.exe"
  File "LICENSE.txt"
  
  CreateShortcut "$DESKTOP\Bookworm.lnk" "$INSTDIR\bookworm_gui_v400.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Bookworm" "DisplayName" "Bookworm"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Bookworm" "UninstallString" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  CreateDirectory "$DESKTOP\bookworm_backup"

  ; Backup .xlsx and .json files
  CopyFiles /SILENT "$INSTDIR\*.sqlite.enc" "$DESKTOP\bookworm_backup\"
  CopyFiles /SILENT "$INSTDIR\*.sqlite" "$DESKTOP\bookworm_backup\"
  CopyFiles /SILENT "$INSTDIR\*.json" "$DESKTOP\bookworm_backup\"

  ; Move folders with content if exist
  IfFileExists "$INSTDIR\themes\" 0 +3
    Rename "$INSTDIR\themes" "$DESKTOP\bookworm_backup\themes"

  IfFileExists "$INSTDIR\settings\" 0 +3
    Rename "$INSTDIR\settings" "$DESKTOP\bookworm_backup\settings"

  IfFileExists "$INSTDIR\book\" 0 +3
    Rename "$INSTDIR\book" "$DESKTOP\bookworm_backup\book"

  ; Delete executables, LICENSE, and uninstall files
  Delete "$INSTDIR\bookworm_gui_v400.exe"
  Delete "$INSTDIR\updater_v100.exe"
  Delete "$INSTDIR\themecreator_v100.exe"
  Delete "$INSTDIR\LICENSE.txt"
  Delete "$INSTDIR\Uninstall.exe"

  ; Delete desktop shortcut
  Delete "$DESKTOP\Bookworm.lnk"

  ; Remove install directory recursively (should be mostly empty)
  RMDir /r "$INSTDIR"

  ; Remove uninstall registry key
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Bookworm"
SectionEnd
