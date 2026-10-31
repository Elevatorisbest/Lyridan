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
; held by the running app (lyridan/update_channels.py APP_MUTEX)
#define AppMutexName "LyridanAppMutex"

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
; Installing over an existing copy (older or newer, by hand or by the auto-updater):
;  * same folder as before, no folder page (UsePreviousAppDir / DisableDirPage=auto)
;  * waits for / asks to close a running Lyridan ([Code] InitializeSetup) and closes
;    anything else holding its files (Restart Manager)
;  * the old _internal folder is removed first ([InstallDelete]) so files from another
;    version can't be mixed in - this is what makes downgrades safe
UsePreviousAppDir=yes
DisableDirPage=auto
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
SetupMutex=LyridanSetupMutex,Global\LyridanSetupMutex

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "assocproject"; Description: "Open .lyridan project files with Lyridan"; GroupDescription: "File associations:"

[Files]
Source: "..\..\dist\Lyridan\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

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
; auto-update (silent, started by Lyridan with /LYRIDANUPDATE=1): start Lyridan again
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: IsLyridanUpdate

[Code]
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F1B7C2E-5A43-4C8E-9C1E-7E1D2B5A9F31}_is1';

function IsLyridanUpdate: Boolean;
begin
  Result := ExpandConstant('{param:LYRIDANUPDATE|0}') = '1';
end;

function WaitForLyridanToClose(Seconds: Integer): Boolean;
var
  I: Integer;
begin
  I := 0;
  while CheckForMutexes('{#AppMutexName}') and (I < Seconds * 4) do
  begin
    Sleep(250);
    I := I + 1;
  end;
  Result := not CheckForMutexes('{#AppMutexName}');
end;

{ Lyridan installed in the other scope (per user vs. all users)? }
function OtherScopeInstallDir(var Dir: String): Boolean;
begin
  if IsAdminInstallMode then
    Result := RegQueryStringValue(HKCU, UninstallKey, 'InstallLocation', Dir)
  else
  begin
    Result := RegQueryStringValue(HKLM64, UninstallKey, 'InstallLocation', Dir);
    if not Result then
      Result := RegQueryStringValue(HKLM32, UninstallKey, 'InstallLocation', Dir);
  end;
end;

function InitializeSetup(): Boolean;
var
  Dir, Msg: String;
begin
  Result := True;
  if IsLyridanUpdate then
  begin
    { Lyridan started this installer and is quitting right now }
    if not WaitForLyridanToClose(30) then
    begin
      Log('Lyridan is still running - update cancelled.');
      Result := False;
    end;
    exit;
  end;
  while not WaitForLyridanToClose(2) do
  begin
    if SuppressibleMsgBox('Lyridan is running.' + #13#10#13#10 +
        'Save your work and close Lyridan, then click Retry.' + #13#10 +
        'Click Cancel to exit Setup.', mbError, MB_RETRYCANCEL, IDCANCEL) = IDCANCEL then
    begin
      Result := False;
      exit;
    end;
  end;
  if (not WizardSilent) and OtherScopeInstallDir(Dir) then
  begin
    if IsAdminInstallMode then
      Msg := 'Lyridan is also installed just for your account in:' + #13#10 + Dir + #13#10#13#10 +
             'Installing for all users leaves that copy in place (you can remove it in Settings > Apps).' +
             #13#10#13#10 + 'Continue?'
    else
      Msg := 'Lyridan is already installed for all users in:' + #13#10 + Dir + #13#10#13#10 +
             'Installing only for you creates a second copy. To update the existing copy instead, click No ' +
             'and run Setup again choosing "Install for all users".' + #13#10#13#10 + 'Continue anyway?';
    if MsgBox(Msg, mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;
