[Setup]
AppName=ECBot
AppVersion=1.0.0
DefaultDirName={pf}\ECBot
DefaultGroupName=ECBot
OutputBaseFilename=ECBot
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\ECBot.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ECBot"; Filename: "{app}\ECBot.exe"
Name: "{group}\Uninstall ECBot"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\ECBot.exe"; Description: "Run YourApp"; Flags: nowait postinstall skipifsilent
