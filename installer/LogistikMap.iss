; Logistik Map – Windows-Installer (Inno Setup 6)
;
; Wird von installer\build.ps1 gebaut:
;   ISCC.exe /DAppVersion=0.1.0 /DStageDir=<build\stage> LogistikMap.iss
;
; Aufbau der Installation:
;   {app}\LogistikMap.exe, {app}\_internal\   Programm (wird bei jedem Update ersetzt)
;   {app}\service\                            Windows-Dienst "LogistikMap" (WinSW)
;   C:\ProgramData\Logistik Map\              Datenbank, PDF-Pläne, Kacheln, Protokolle, config.json
;                                             – bleibt bei Update und Deinstallation erhalten
;
; Unbeaufsichtigt: LogistikMap-Setup-x.y.z.exe /VERYSILENT [/PORT=8470] [/TASKS="firewall"]
;   Bei einem Update ohne /PORT bleibt der bisherige Port.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef StageDir
  #define StageDir "build\stage"
#endif
#ifndef OutputDir
  #define OutputDir "build\output"
#endif

#define AppName     "Logistik Map"
#define ServiceName "LogistikMap"
#define RepoUrl     "https://github.com/phillhf/logistik-map"
#define DefaultPort "8470"

[Setup]
AppId={{B6E4D2A1-5C3F-4E8B-9A71-2D0F6C8E4B19}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Logistik Map Contributors
AppPublisherURL={#RepoUrl}
AppSupportURL={#RepoUrl}/issues
AppUpdatesURL={#RepoUrl}/releases
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
LicenseFile={#StageDir}\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename=LogistikMap-Setup-{#AppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\LogistikMap.exe
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
MinVersion=10.0
WizardStyle=modern
CloseApplications=no
SetupLogging=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Messages]
de.WelcomeLabel2=Dieser Assistent installiert [name/ver] auf diesem Server.%n%nLogistik Map läuft anschließend als Windows-Dienst und ist im Netzwerk per Browser erreichbar.%n%nBei einem Update bleiben alle Daten (Pläne, Benutzer, Einstellungen) erhalten.

[Tasks]
Name: "firewall"; Description: "Port in der Windows-Firewall freigeben (Zugriff von anderen Rechnern im Netzwerk)"

[Dirs]
Name: "{commonappdata}\{#AppName}"; Flags: uninsneveruninstall

[InstallDelete]
; Programmdateien vollständig ersetzen, damit keine veralteten Dateien liegen bleiben.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#StageDir}\app\*";     DestDir: "{app}";         Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\service\*"; DestDir: "{app}\service"; Flags: ignoreversion recursesubdirs
Source: "{#StageDir}\LICENSE";   DestDir: "{app}";         Flags: ignoreversion
Source: "{#StageDir}\README.md"; DestDir: "{app}";         Flags: ignoreversion
Source: "{#StageDir}\README.de.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\THIRD_PARTY_LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion

[INI]
Filename: "{app}\Logistik Map.url"; Section: "InternetShortcut"; Key: "URL"; String: "{code:GetScheme}://localhost:{code:GetPort}"
Filename: "{app}\Logistik Map.url"; Section: "InternetShortcut"; Key: "IconFile"; String: "{app}\LogistikMap.exe"
Filename: "{app}\Logistik Map.url"; Section: "InternetShortcut"; Key: "IconIndex"; String: "0"

[Icons]
Name: "{group}\Logistik Map öffnen";       Filename: "{app}\Logistik Map.url"; IconFilename: "{app}\LogistikMap.exe"
Name: "{group}\Protokolle";                Filename: "{commonappdata}\{#AppName}\logs"
Name: "{group}\Logistik Map deinstallieren"; Filename: "{uninstallexe}"

[Run]
Filename: "{code:GetScheme}://localhost:{code:GetPort}"; Description: "Logistik Map jetzt im Browser öffnen"; Flags: postinstall shellexec nowait skipifsilent

[UninstallRun]
Filename: "{app}\service\LogistikMap-Dienst.exe"; Parameters: "stop";      Flags: runhidden waituntilterminated; RunOnceId: "StopService"
Filename: "{app}\service\LogistikMap-Dienst.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveService"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveFirewall"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""LogistikMap Update"" /F"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveTask"

[UninstallDelete]
Type: files; Name: "{app}\Logistik Map.url"
Type: filesandordirs; Name: "{app}\_internal"

[Code]
var
  PortPage: TInputQueryWizardPage;
  SetupFailed: Boolean;

function ConfigFile: String;
begin
  Result := ExpandConstant('{commonappdata}\{#AppName}\config.json');
end;

function IsUpgrade: Boolean;
begin
  Result := FileExists(ConfigFile);
end;

{ Liest "port": N aus config.json }
function ReadConfigPort(const Default: String): String;
var
  S: AnsiString;
  T: String;
  P, I: Integer;
begin
  Result := Default;
  if not LoadStringFromFile(ConfigFile, S) then exit;
  T := String(S);
  P := Pos('"port"', T);
  if P = 0 then exit;
  T := Copy(T, P + 6, 40);
  P := Pos(':', T);
  if P = 0 then exit;
  T := Trim(Copy(T, P + 1, 40));
  I := 1;
  while (I <= Length(T)) and (T[I] >= '0') and (T[I] <= '9') do I := I + 1;
  if I > 1 then Result := Copy(T, 1, I - 1);
end;

{ HTTPS, wenn in config.json ein Zertifikat eingetragen ist }
function GetScheme(Param: String): String;
var
  S: AnsiString;
  T: String;
  P: Integer;
begin
  Result := 'http';
  if not LoadStringFromFile(ConfigFile, S) then exit;
  T := String(S);
  P := Pos('"zertifikat": "', T);
  if (P > 0) and (Copy(T, P + 15, 1) <> '"') then Result := 'https';
end;

function IsValidPort(const S: String): Boolean;
var
  N: Integer;
begin
  N := StrToIntDef(Trim(S), 0);
  Result := (N >= 1) and (N <= 65535);
end;

function GetPort(Param: String): String;
begin
  Result := Trim(PortPage.Values[0]);
  if WizardSilent and IsUpgrade and (ExpandConstant('{param:PORT|}') = '') then
    Result := ReadConfigPort(Result);
  if not IsValidPort(Result) then Result := '{#DefaultPort}';
end;

function ServiceExists: Boolean;
var
  RC: Integer;
begin
  Result := Exec(ExpandConstant('{sys}\sc.exe'), 'query {#ServiceName}', '', SW_HIDE, ewWaitUntilTerminated, RC) and (RC = 0);
end;

procedure InitializeWizard;
begin
  PortPage := CreateInputQueryPage(wpSelectDir,
    'Netzwerk',
    'Unter welchem Port soll Logistik Map erreichbar sein?',
    'Logistik Map ist danach im Netzwerk unter http://<Servername>:<Port> erreichbar.' + #13#10 +
    'Der Port darf nicht von einem anderen Programm belegt sein. Standard: {#DefaultPort}.');
  PortPage.Add('&Port:', False);
  PortPage.Values[0] := ExpandConstant('{param:PORT|{#DefaultPort}}');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { Bei erneuter Installation den bisherigen Port vorschlagen }
  if (CurPageID = PortPage.ID) and IsUpgrade and (ExpandConstant('{param:PORT|}') = '') then
    PortPage.Values[0] := ReadConfigPort(PortPage.Values[0]);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = PortPage.ID) and not IsValidPort(PortPage.Values[0]) then
  begin
    MsgBox('Bitte einen Port zwischen 1 und 65535 eingeben.', mbError, MB_OK);
    Result := False;
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine +
            'Port:' + NewLine + Space + GetPort('') + NewLine + NewLine +
            'Daten:' + NewLine + Space + ExpandConstant('{commonappdata}\{#AppName}') + NewLine;
  if IsUpgrade then
    Result := Result + NewLine + 'Update einer bestehenden Installation (Daten bleiben erhalten)' + NewLine;
  if MemoTasksInfo <> '' then
    Result := Result + NewLine + MemoTasksInfo + NewLine;
end;

{ Laufenden Dienst vor dem Kopieren stoppen, sonst ist LogistikMap.exe gesperrt }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  RC: Integer;
  Svc: String;
begin
  Result := '';
  if ServiceExists then
  begin
    Svc := ExpandConstant('{app}\service\LogistikMap-Dienst.exe');
    if FileExists(Svc) then
      Exec(Svc, 'stop', '', SW_HIDE, ewWaitUntilTerminated, RC)
    else
      Exec(ExpandConstant('{sys}\sc.exe'), 'stop {#ServiceName}', '', SW_HIDE, ewWaitUntilTerminated, RC);
    Sleep(3000);
  end;
end;

procedure Fail(const Msg: String);
begin
  SetupFailed := True;
  Log('FEHLER: ' + Msg);
  SuppressibleMsgBox(Msg + #13#10#13#10 + 'Protokolle: ' + ExpandConstant('{commonappdata}\{#AppName}\logs'),
    mbCriticalError, MB_OK, IDOK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  RC: Integer;
  Svc: String;
begin
  if CurStep <> ssPostInstall then exit;

  { 1. Konfiguration schreiben und Datenbank anlegen bzw. aktualisieren }
  WizardForm.StatusLabel.Caption := 'Konfiguration und Datenbank werden eingerichtet …';
  if not Exec(ExpandConstant('{app}\LogistikMap.exe'), 'config --port ' + GetPort(''), ExpandConstant('{app}'),
              SW_HIDE, ewWaitUntilTerminated, RC) or (RC <> 0) then
  begin
    Fail('Die Konfiguration konnte nicht geschrieben werden (Code ' + IntToStr(RC) + ').');
    exit;
  end;

  { 2. Firewall }
  Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="{#AppName}"', '', SW_HIDE, ewWaitUntilTerminated, RC);
  if WizardIsTaskSelected('firewall') then
    Exec(ExpandConstant('{sys}\netsh.exe'),
      'advfirewall firewall add rule name="{#AppName}" dir=in action=allow protocol=TCP localport=' + GetPort(''),
      '', SW_HIDE, ewWaitUntilTerminated, RC);

  { 3. Windows-Dienst installieren und starten }
  WizardForm.StatusLabel.Caption := 'Windows-Dienst "{#ServiceName}" wird gestartet …';
  Svc := ExpandConstant('{app}\service\LogistikMap-Dienst.exe');
  if not ServiceExists then
  begin
    if not Exec(Svc, 'install', '', SW_HIDE, ewWaitUntilTerminated, RC) or (RC <> 0) then
    begin
      Fail('Der Windows-Dienst konnte nicht installiert werden (Code ' + IntToStr(RC) + ').');
      exit;
    end;
  end;
  if not Exec(Svc, 'start', '', SW_HIDE, ewWaitUntilTerminated, RC) or (RC <> 0) then
    Fail('Der Windows-Dienst konnte nicht gestartet werden (Code ' + IntToStr(RC) + '). Ist der Port ' + GetPort('') + ' bereits belegt?');

  { 4. Einmalige Aufgabe der Update-Funktion entfernen (falls das Update aus Logistik Map gestartet wurde) }
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/Delete /TN "LogistikMap Update" /F', '', SW_HIDE, ewWaitUntilTerminated, RC);
end;

function GetCustomSetupExitCode: Integer;
begin
  if SetupFailed then Result := 10 else Result := 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    SuppressibleMsgBox('Logistik Map wurde entfernt.' + #13#10#13#10 +
      'Datenbank, PDF-Pläne und Einstellungen wurden NICHT gelöscht:' + #13#10 +
      ExpandConstant('{commonappdata}\{#AppName}'), mbInformation, MB_OK, IDOK);
end;
