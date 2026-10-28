; Inno Setup script for Lyridan (Windows x64 installer)
; Build:  iscc /DAppVersion=2.0.0 packaging\windows\lyridan.iss
; Expects the PyInstaller output in dist\Lyridan\

#ifndef AppVersion
  #define AppVersion "2.0.0"
#endif
#define AppName "Lyridan"
#define AppPublisher "Elevatorisbest"
#define AppURL "https://github.com/Elevatorisbest/Lyridan"
#define AppExe "Lyridan.exe"

[Setup]
AppId={{6F1B7C2E-5A43-4C8E-9C1E-7E1D2B5A9F31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
OutputBaseFilename=Lyridan-{#AppVersion}-Windows-x64-Setup
SetupIconFile=..\..\assets\lyridanlogo.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "assocproject"; Description: "Open .lyridan project files with Lyridan"; GroupDescription: "File associations:"

[Files]
Source: "..\..\dist\Lyridan\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.lyridan"; ValueType: string; ValueName: ""; ValueData: "Lyridan.Project"; Flags: uninsdeletevalue; Tasks: assocproject
Root: HKA; Subkey: "Software\Classes\Lyridan.Project"; ValueType: string; ValueName: ""; ValueData: "Lyridan project"; Flags: uninsdeletekey; Tasks: assocproject
Root: HKA; Subkey: "Software\Classes\Lyridan.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assocproject
Root: HKA; Subkey: "Software\Classes\Lyridan.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assocproject

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
