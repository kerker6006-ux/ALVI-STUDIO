Unicode True

!ifndef BUNDLE_DIR
  !error "BUNDLE_DIR must point to the staged Alvi Studio folder"
!endif
!ifndef OUTPUT_DIR
  !define OUTPUT_DIR "artifacts"
!endif
!ifndef APP_VERSION
  !define APP_VERSION "0.1.1"
!endif

!include "MUI2.nsh"

Name "Alvi Studio"
OutFile "${OUTPUT_DIR}\Alvi-Studio-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\Alvi Studio"
InstallDirRegKey HKCU "Software\AlviStudio" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
ManifestDPIAware true

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${BUNDLE_DIR}\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\AlviStudio.exe"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Alvi Studio" SEC_MAIN
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  SetOverwrite on
  ; Remove the legacy marker that encoded Windows backslashes as invalid JSON.
  ; On first launch the app writes a correctly escaped marker beside itself.
  Delete "$INSTDIR\storage-root.json"
  Delete "$INSTDIR\DubStudio.exe"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\DubStudio"
  DeleteRegKey HKCU "Software\DubStudio"
  File /r "${BUNDLE_DIR}\*"

  CreateDirectory "$INSTDIR\models"
  CreateDirectory "$INSTDIR\cache"
  CreateDirectory "$INSTDIR\projects"
  CreateDirectory "$INSTDIR\exports"
  CreateDirectory "$INSTDIR\temp"
  CreateDirectory "$INSTDIR\logs"
  CreateDirectory "$INSTDIR\updates"

  WriteRegStr HKCU "Software\AlviStudio" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AlviStudio" "DisplayName" "Alvi Studio"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AlviStudio" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AlviStudio" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  Delete "$DESKTOP\DubStudio.lnk"
  RMDir /r "$SMPROGRAMS\DubStudio"
  CreateShortcut "$DESKTOP\Alvi Studio.lnk" "$INSTDIR\AlviStudio.exe"
  CreateDirectory "$SMPROGRAMS\Alvi Studio"
  CreateShortcut "$SMPROGRAMS\Alvi Studio\Alvi Studio.lnk" "$INSTDIR\AlviStudio.exe"
  CreateShortcut "$SMPROGRAMS\Alvi Studio\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$DESKTOP\Alvi Studio.lnk"
  Delete "$DESKTOP\DubStudio.lnk"
  RMDir /r "$SMPROGRAMS\Alvi Studio"
  RMDir /r "$SMPROGRAMS\DubStudio"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AlviStudio"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\DubStudio"
  DeleteRegKey HKCU "Software\AlviStudio"
  DeleteRegKey HKCU "Software\DubStudio"

  ; User projects, exports, downloaded models and caches are intentionally left
  ; intact. The uninstaller only removes program-controlled binaries.
  Delete "$INSTDIR\AlviStudio.exe"
  Delete "$INSTDIR\DubStudio.exe"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\THIRD_PARTY_NOTICES.md"
  RMDir /r "$INSTDIR\_internal"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\tools"
  RMDir /r "$INSTDIR\runtime"
  MessageBox MB_OK "Alvi Studio was removed. Your models, projects and exports remain in $INSTDIR so they can be recovered or deleted manually."
SectionEnd
