Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

!ifndef PAYLOAD
!error "PAYLOAD must name the verified self-contained publish directory"
!endif
!ifndef OUTPUT
!error "OUTPUT must name the output installer"
!endif
!ifndef UNINSTALL_FILES
!error "UNINSTALL_FILES must name the generated owned-files deletion script"
!endif

Name "Kolbo Live Studio Preview"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\KolboLiveStudio"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "Kolbo Live Studio - Preview 0.1.5"
VIProductVersion "0.1.5.0"
VIAddVersionKey "ProductName" "Kolbo Live Studio"
VIAddVersionKey "FileDescription" "Kolbo Live Studio Preview Installer"
VIAddVersionKey "FileVersion" "0.1.5-preview"
VIAddVersionKey "LegalCopyright" "Kolbo Live Studio contributors"

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Kolbo Live Studio"
!define MUI_WELCOMEPAGE_TEXT "Professional live recording preview with ASIO duplex audio and phone-camera workflow.$\r$\n$\r$\nThis is a preview build. Install the official ASIO driver for your audio interface before first use.$\r$\n$\r$\nRecordings are stored separately and are not deleted when the application is uninstalled."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\Kolbo.Live.Windows.exe"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Hebrew"
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "Windows 10 or later is required."
    Abort
  ${EndIf}
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "This build requires 64-bit Windows."
    Abort
  ${EndIf}
FunctionEnd

Section "Kolbo Live Studio"
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Kolbo Live Studio"
  CreateShortcut "$SMPROGRAMS\Kolbo Live Studio\Kolbo Live Studio.lnk" "$INSTDIR\Kolbo.Live.Windows.exe"
  CreateShortcut "$SMPROGRAMS\Kolbo Live Studio\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\Kolbo Live Studio.lnk" "$INSTDIR\Kolbo.Live.Windows.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "DisplayName" "Kolbo Live Studio Preview"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "DisplayVersion" "0.1.5-preview"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "DisplayIcon" "$INSTDIR\Kolbo.Live.Windows.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  !include "${UNINSTALL_FILES}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\Kolbo Live Studio.lnk"
  Delete "$SMPROGRAMS\Kolbo Live Studio\Kolbo Live Studio.lnk"
  Delete "$SMPROGRAMS\Kolbo Live Studio\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Kolbo Live Studio"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio"
SectionEnd
