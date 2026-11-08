Unicode true
!include "MUI2.nsh"
Name "${TITLE}"
OutFile "${OUTPUT}"
InstallDir "$APPDATA\${PACKAGE}"
RequestExecutionLevel user
SetCompressor /SOLID lzma
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
Function .onInit
  SetShellVarContext current
  IfFileExists "$APPDATA\${OTHER}\Launcher.exe" 0 done
  MessageBox MB_ICONSTOP "Please uninstall ${OTHER} before installing ${PACKAGE}."
  Abort
  done:
FunctionEnd
Section "Emulator"
  SetShellVarContext current
  SetOutPath "$INSTDIR\versions\${PAYLOAD_SHA}"
  File /r "${PAYLOAD_DIR}/*"
  SetOutPath "$INSTDIR"
  File "${HARNESS_DIR}/Launcher.exe"
  File "${HARNESS_DIR}/emulator.ico"
  File "${HARNESS_DIR}/updater.ps1"
  File "${HARNESS_DIR}/install.json"
  File "${HARNESS_DIR}/current.json"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortcut "$SMPROGRAMS\${TITLE}.lnk" "$INSTDIR\Launcher.exe" "" "$INSTDIR\emulator.ico" 0
  CreateShortcut "$DESKTOP\${TITLE}.lnk" "$INSTDIR\Launcher.exe" "" "$INSTDIR\emulator.ico" 0
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PACKAGE}" "DisplayName" "${TITLE}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PACKAGE}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PACKAGE}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PACKAGE}" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PACKAGE}" "NoRepair" 1
SectionEnd
Section "Uninstall"
  SetShellVarContext current
  Delete "$SMPROGRAMS\${TITLE}.lnk"
  Delete "$DESKTOP\${TITLE}.lnk"
  Delete "$INSTDIR\Launcher.exe"
  Delete "$INSTDIR\emulator.ico"
  Delete "$INSTDIR\updater.ps1"
  Delete "$INSTDIR\install.json"
  Delete "$INSTDIR\current.json"
  RMDir /r "$INSTDIR\versions"
  Delete "$INSTDIR\Uninstall.exe"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PACKAGE}"
  RMDir "$INSTDIR"
SectionEnd
