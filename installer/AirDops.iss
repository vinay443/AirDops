; Inno Setup script - per-user install, no administrator rights needed.
; Built by CI:  ISCC /DAppVersion=0.3.0 installer\AirDops.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6B1E2A54-3C0E-4E7B-9A55-AD0B5A1F2C11}
AppName=AirDops
AppVersion={#AppVersion}
AppVerName=AirDops {#AppVersion}
AppPublisher=AirDops
AppPublisherURL=https://github.com/vinay443/AirDops
AppSupportURL=https://github.com/vinay443/AirDops/issues
DefaultDirName={localappdata}\Programs\AirDops
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AirDops-Setup
SetupIconFile=..\build\AirDops.ico
UninstallDisplayIcon={app}\AirDops.exe
UninstallDisplayName=AirDops
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Ask to close a running AirDops (it holds this mutex) before installing/uninstalling.
AppMutex=AirDops-single-instance
CloseApplications=yes
LicenseFile=..\LICENSE

[Tasks]
Name: "login"; Description: "Open AirDops when I sign in to Windows"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\AirDops\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\AirDops"; Filename: "{app}\AirDops.exe"
Name: "{userdesktop}\AirDops"; Filename: "{app}\AirDops.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AirDops"; ValueData: """{app}\AirDops.exe"" --background"; Tasks: login; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "AirDops"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\AirDops.exe"; Description: "Open AirDops now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Put Windows audio back exactly as it was before removing the app.
Filename: "{app}\AirDops.exe"; Parameters: "--uninstall --quiet"; RunOnceId: "RestoreAudio"; Flags: waituntilterminated runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\AirDops"
