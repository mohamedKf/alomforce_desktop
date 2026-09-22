; Windows installer for the AlomForce desktop app (Inno Setup).
;
; The point of shipping an installer rather than a zip is that an update has
; to replace the app, not sit beside it. Windows decides that by AppId: the
; GUID below is this product's identity forever. Every build carries the same
; one, so installing 1.2.0 over 1.1.0 upgrades in place -- one entry in Apps &
; features, one Start menu shortcut, one folder. Change the GUID and the next
; version installs as a second, unrelated program, which is exactly what we
; are avoiding. So: never change it.
;
; Built by .github/workflows/desktop-build.yml, which passes the version in:
;   iscc /DMyAppVersion=1.1.0 packaging\windows\alomforce.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "AlomForce"
#define MyAppPublisher "AlomForce"
#define MyAppExeName "AlomForce.exe"

[Setup]
; The product identity. See the note above -- this never changes.
AppId={{FC95CD32-0886-46AD-A11C-5677A20682F0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user by default so no administrator password is needed on a shop-floor
; PC; "lowest" keeps it out of Program Files unless the installer is run
; elevated, in which case it installs for everyone.
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest

OutputDir=..\..\dist
OutputBaseFilename=AlomForce-Setup-{#MyAppVersion}
SetupIconFile=..\..\app\assets\alomforce.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; QtWebEngine is 64-bit only.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Refuse to install an older build over a newer one, rather than silently
; downgrading a yard that already has the newer app.
[Code]
function InitializeSetup(): Boolean;
var
  Installed: String;
begin
  Result := True;
  if RegQueryStringValue(HKA, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1',
                         'DisplayVersion', Installed) then
  begin
    if CompareStr(Installed, '{#MyAppVersion}') > 0 then
    begin
      MsgBox('A newer AlomForce (' + Installed + ') is already installed.' + #13#10 +
             'Remove it first if you really want version {#MyAppVersion}.',
             mbInformation, MB_OK);
      Result := False;
    end;
  end;
end;

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "he"; MessagesFile: "compiler:Languages\Hebrew.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; The whole PyInstaller onedir output. recursesubdirs takes the Qt and
; Chromium runtime with it; the exe alone does not run.
Source: "..\..\dist\AlomForce\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

; The server address and language live in the registry under the app's own
; key, written by the app itself. Left alone on upgrade so the yard does not
; retype its server after every update; removed only on uninstall.
[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\AlomForce"
