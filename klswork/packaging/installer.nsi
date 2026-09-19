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

Name "Kolbo Live Studio Preview"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\KolboLiveStudio"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "Kolbo Live Studio - Preview 0.1.8"
VIProductVersion "0.1.8.0"
VIAddVersionKey "ProductName" "Kolbo Live Studio"
VIAddVersionKey "FileDescription" "Kolbo Live Studio Preview Installer"
VIAddVersionKey "FileVersion" "0.1.8-preview"
VIAddVersionKey "LegalCopyright" "Kolbo Live Studio contributors"

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Kolbo Live Studio"
!define MUI_WELCOMEPAGE_TEXT "Audio, karaoke-video and YouTube playback sources, MR816X REV-X validation, optional phone video and native resizable Windows UI. Recordings are stored separately and are not deleted during uninstall."
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

  ; A previous preview may still be running. Close it before replacing files,
  ; then install into a clean application directory. Recordings are stored elsewhere.
  nsExec::ExecToLog '"$SYSDIR\taskkill.exe" /IM Kolbo.Live.Windows.exe /F'
  Sleep 500
  RMDir /r "$INSTDIR"

  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*"
  FileOpen $0 "$INSTDIR\VERSION.txt" w
  FileWrite $0 "Kolbo Live Studio Preview 0.1.8$$
"
  FileClose $0
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\Kolbo Live Studio"
  CreateShortcut "$SMPROGRAMS\Kolbo Live Studio\Kolbo Live Studio.lnk" "$INSTDIR\Kolbo.Live.Windows.exe"
  CreateShortcut "$SMPROGRAMS\Kolbo Live Studio\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\Kolbo Live Studio.lnk" "$INSTDIR\Kolbo.Live.Windows.exe"

  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "DisplayName" "Kolbo Live Studio Preview"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "DisplayVersion" "0.1.8-preview"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "DisplayIcon" "$INSTDIR\Kolbo.Live.Windows.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  !include "uninstall-files.generated.nsh"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\Kolbo Live Studio.lnk"
  Delete "$SMPROGRAMS\Kolbo Live Studio\Kolbo Live Studio.lnk"
  Delete "$SMPROGRAMS\Kolbo Live Studio\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Kolbo Live Studio"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KolboLiveStudio"
SectionEnd
