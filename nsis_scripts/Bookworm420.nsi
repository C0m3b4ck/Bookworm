; Bookworm420.nsi
Outfile "Bookworm420_installer.exe"
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
  File "bookworm_gui_v420.exe"
  File "updater_v200.exe"
  File "themecreator_v100.exe"
  File "LICENSE.txt"
  
  CreateShortcut "$DESKTOP\Bookworm.lnk" "$INSTDIR\bookworm_gui_v420.exe"

  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Bookworm" "DisplayName" "Bookworm"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Bookworm" "UninstallString" "$INSTDIR\uninstaller_v100.exe"
SectionEnd
