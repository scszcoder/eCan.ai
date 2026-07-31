; Inno Setup Script Overrides for CN Version
; Customizes Windows installer branding for Chinese market

[Setup]
AppName=eCan · 中国版
AppVersion=1.0.0
AppPublisher=fastprecisiontech.com
AppPublisherURL=https://fastprecisiontech.com
AppSupportURL=https://fastprecisiontech.com/support
AppUpdatesURL=https://fastprecisiontech.com/updates
DefaultDirName={autopf}\eCan.cn
DefaultGroupName=eCan · 中国版
OutputBaseFilename=eCan_CN_Setup_v1.0.0
SetupIconFile=..\branding\icon.ico
UninstallDisplayIcon={app}\eCan.cn.exe
WizardStyle=modern
WizardSizePercent=100
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
Source: "..\dist\eCan.cn.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\eCan · 中国版"; Filename: "{app}\eCan.cn.exe"
Name: "{group}\{cm:UninstallProgram,eCan · 中国版}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\eCan · 中国版"; Filename: "{app}\eCan.cn.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\eCan.cn.exe"; Description: "{cm:LaunchProgram,eCan · 中国版}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\fastprecisiontech.com\eCan.cn"; Flags: uninsdeletekeyifempty
Root: HKCU; Subkey: "Software\fastprecisiontech.com\eCan.cn"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"
Root: HKCU; Subkey: "Software\fastprecisiontech.com\eCan.cn"; ValueType: string; ValueName: "Version"; ValueData: "1.0.0"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Post-installation tasks for CN version
  end;
end;

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{localappdata}\eCan.cn"
