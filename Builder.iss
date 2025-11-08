; Modbus-Sim.iss -- Per-User installer (AppData\Local\Programs)
; Use the Unicode build of Inno Setup to compile this script.

[Setup]
; Basic app info
AppName=Modbus-Sim
AppVersion=0.2.1
AppPublisher=Lokesh
AppPublisherURL=https://github.com/lokie861
AppSupportURL=mailto:plokesh23.01@gmail.com
AppUpdatesURL=https://github.com/lokie861/Modbus-Sim

; Per-user install (no admin required)
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Modbus-Sim
DefaultGroupName=Modbus-Sim
OutputDir=Builds\Installer
OutputBaseFilename=Modbus-Sim-Setup
Compression=lzma
SolidCompression=yes

; IMPORTANT: AppId in [Setup] must use DOUBLE braces
AppId={{A3F7D9B2-8E5C-4A1D-9B6F-7C2E4D8A3F1B}}
CreateUninstallRegKey=yes
UninstallDisplayName=Modbus-Sim
UninstallDisplayIcon={app}\Modbus-Sim.exe

; allow replacing files in use (we also try to kill processes in code)
RestartIfNeededByRun=no

[Files]
; Install everything from your build output folder (recurses subdirs)
Source: "Builds\EXE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Modbus-Sim"; Filename: "{app}\Modbus-Sim.exe"; WorkingDir: "{app}"; IconFilename: "{app}\Modbus-Sim.exe"
Name: "{userdesktop}\Modbus-Sim"; Filename: "{app}\Modbus-Sim.exe"; WorkingDir: "{app}"; IconFilename: "{app}\Modbus-Sim.exe"; Tasks: desktopicon

[Registry]
; Add startup entry (HKCU - per-user)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueName: "Modbus-Sim"; ValueType: string; \
  ValueData: """{app}\Modbus-Sim_Startup.bat"""; Flags: uninsdeletevalue

; Per-user app metadata key
Root: HKCU; Subkey: "SOFTWARE\Modbus-Sim"; ValueType: string; ValueName: "version"; ValueData: "0.2.1"; Flags: uninsdeletekeyifempty uninsdeletevalue

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Run]
; Launch app after install directly (no cmd spawn) - avoids spawn-server issues
Filename: "{app}\Modbus-Sim.exe"; WorkingDir: "{app}"; Description: "Launch Modbus-Sim"; Flags: postinstall skipifsilent nowait

[Code]
// APPID constant here should be single-braced (used for string manipulation)
const
  APPID = '{A3F7D9B2-8E5C-4A1D-9B6F-7C2E4D8A3F1B}';

function GetUninstallString(): string;
var
  sUnInstPath: string;
  sUnInstallString: string;
begin
  // Build the uninstall registry path using the APPID constant above (remove braces)
  sUnInstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + Copy(APPID, 2, Length(APPID)-2) + '_is1';
  sUnInstallString := '';
  // Only check HKCU since this is a per-user installer
  if RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString) then
    Result := sUnInstallString
  else
    Result := '';
end;

function IsUpgrade(): Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

function UnInstallOldVersion(): Integer;
var
  sUnInstallString: string;
  iResultCode: Integer;
begin
  Result := 0;
  sUnInstallString := GetUninstallString();
  if sUnInstallString <> '' then
  begin
    sUnInstallString := RemoveQuotes(sUnInstallString);
    // Run the previous uninstaller silently if possible
    if Exec(sUnInstallString, '/SILENT /NORESTART /SUPPRESSMSGBOXES', '', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      Result := 3
    else
      Result := 2;
  end
  else
    Result := 1;
end;

// Create a batch file to make sure launching from startup uses the app folder as cwd
procedure CreateStartupBatch();
var
  BatchContent: AnsiString;
  BatchPath: string;
begin
  BatchPath := ExpandConstant('{app}\Modbus-Sim_Startup.bat');
  BatchContent :=
    '@echo off' + #13#10 +
    'cd /d "%~dp0"' + #13#10 +
    'start "" "%~dp0Modbus-Sim.exe"' + #13#10;

  SaveStringToFile(BatchPath, BatchContent, False);
end;

// Try to force-kill Modbus-Sim.exe before install/uninstall to avoid file locks
procedure ForceCleanup();
var
  ResultCode: Integer;
begin
  // /T kills child processes too, /F forces termination
  Exec('taskkill.exe', '/f /im "Modbus-Sim.exe"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1000);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssInstall) then
  begin
    ForceCleanup();

    if (IsUpgrade()) then
    begin
      // Attempt to uninstall old version
      UnInstallOldVersion();
      // allow some time for uninstaller to finish cleanup
      Sleep(2000);
      // Try cleanup again
      ForceCleanup();
    end;
  end;

  if (CurStep = ssPostInstall) then
  begin
    // create startup batch so registry Run entry points to it
    CreateStartupBatch();
  end;
end;

function InitializeSetup(): Boolean;
var
  Response: Integer;
  OldVersionFound: Boolean;
begin
  Result := True;
  OldVersionFound := IsUpgrade();

  if OldVersionFound then
  begin
    Response := MsgBox('A previous version of Modbus-Sim was detected on your system.' + #13#13 +
                       'The installer will attempt to remove the old version automatically before installing the new one.' + #13#13 +
                       'Click "Yes" to continue with the upgrade.' + #13 +
                       'Click "No" to cancel the installation.',
                       mbConfirmation, MB_YESNO);
    if Response = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  sUnInstPath: string;
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Kill any running processes prior to uninstall
    Exec('taskkill.exe', '/f /im "Modbus-Sim.exe"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1500);
  end;

  if CurUninstallStep = usPostUninstall then
  begin
    // Final cleanup - kill any remaining instances
    Exec('taskkill.exe', '/f /im "Modbus-Sim.exe"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1000);

    // Remove the entire installation folder (per-user)
    if DirExists(ExpandConstant('{app}')) then
    begin
      // Use DelTree to remove files and folders
      DelTree(ExpandConstant('{app}'), True, True, True);
    end;

    // Clean up uninstall registry key (HKCU only)
    sUnInstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + Copy(APPID, 2, Length(APPID)-2) + '_is1';
    if RegKeyExists(HKCU, sUnInstPath) then
    begin
      try
        RegDeleteKeyIncludingSubkeys(HKCU, sUnInstPath);
      except
        // ignore errors
      end;
    end;

    // Remove startup Run value if it exists
    if RegValueExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Modbus-Sim') then
      RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Modbus-Sim');

    // Remove per-user app key if exists
    if RegKeyExists(HKCU, 'SOFTWARE\Modbus-Sim') then
    begin
      try
        RegDeleteKeyIncludingSubkeys(HKCU, 'SOFTWARE\Modbus-Sim');
      except
        // ignore errors
      end;
    end;
  end;
end;
