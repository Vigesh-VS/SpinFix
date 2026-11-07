; SPDX-License-Identifier: MIT
; Copyright (c) 2026 Vigesh
;
; Spinfix per-user installer (no admin rights). Build after PyInstaller:
;   iscc /DAppVersion=0.1.0 installer\spinfix.iss
; Everything goes under %LOCALAPPDATA%\Programs\Spinfix and HKCU, and is removed on uninstall.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6F1E0C8B-5B7A-4C1E-9A43-5F1A2D7C9E21}
AppName=Spinfix
AppVersion={#AppVersion}
AppVerName=Spinfix {#AppVersion}
AppPublisher=Vigesh
AppPublisherURL=https://github.com/Vigesh-VS/SpinFix
AppSupportURL=https://github.com/Vigesh-VS/SpinFix/issues
AppCopyright=Copyright (c) 2026 Vigesh
LicenseFile=..\LICENSE
DefaultDirName={localappdata}\Programs\Spinfix
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=Spinfix-{#AppVersion}-setup
SetupIconFile=..\assets\spinfix.ico
UninstallDisplayIcon={app}\Spinfix.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
AppMutex=SpinfixAppMutex
CloseApplications=yes
ChangesAssociations=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "contextmenu"; Description: "Add ""Spinfix…"" to the right-click menu"; GroupDescription: "Explorer:"
Name: "sendto"; Description: "Add Spinfix to ""Send to"""; GroupDescription: "Explorer:"

[Files]
Source: "..\dist\Spinfix\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Spinfix"; Filename: "{app}\Spinfix.exe"
Name: "{userdesktop}\Spinfix"; Filename: "{app}\Spinfix.exe"; Tasks: desktopicon
Name: "{usersendto}\Spinfix"; Filename: "{app}\Spinfix.exe"; Parameters: "--open"; Tasks: sendto

[Registry]
; Right-click "Spinfix…" for files and folders (current user only).
Root: HKCU; Subkey: "Software\Classes\*\shell\Spinfix"; ValueType: string; ValueName: ""; ValueData: "Spinfix…"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\Spinfix"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\Spinfix.exe"",0"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\Spinfix\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Spinfix.exe"" --open ""%1"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\shell\Spinfix"; ValueType: string; ValueName: ""; ValueData: "Spinfix…"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\Spinfix"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\Spinfix.exe"",0"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\shell\Spinfix\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Spinfix.exe"" --open ""%1"""; Tasks: contextmenu
; "Start with Windows" is only written by the app when the user turns it on;
; this line just makes sure uninstall removes it.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Spinfix"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Spinfix.exe"; Description: "Start Spinfix now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Settings, logs and temp files — nothing is left behind.
Type: filesandordirs; Name: "{localappdata}\Spinfix"
Type: filesandordirs; Name: "{userappdata}\Spinfix"
