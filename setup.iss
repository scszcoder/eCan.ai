; 定义应用程序的基本信息
[Setup]
AppName=ECBot            ; 应用程序名称
AppVersion=1.0.0               ; 应用程序版本
WizardStyle=modern
DefaultDirName={pf}\ECBot ; 默认的安装目录 ({pf} 是系统 Program Files 目录)
DefaultGroupName=ECBot   ; 开始菜单文件夹名称
UninstallDisplayIcon={app}\ECBot.exe
SetupIconFile=installer.ico
OutputBaseFilename=ECBotInstaller ; 输出的安装程序文件名称
OutputDir=dist              ; 定义输出路径，可以是相对路径或绝对路径
Compression=lzma               ; 压缩方式
SolidCompression=yes           ; 使用固体压缩

DisableWelcomePage=no
LicenseFile=license.txt
;#define Password 'password'
;Password={#Password}
;InfoBeforeFile=readme.txt
;UserInfoPage=yes
PrivilegesRequired=lowest
DisableDirPage=no
DisableProgramGroupPage=no
InfoAfterFile=readme.txt

; Tell Windows Explorer to reload the environment
ChangesEnvironment=yes

; 定义安装包中包含的文件
[Files]
Source: "dist\ECBot.exe"; DestDir: "{app}"; Flags: ignoreversion

; 定义快捷方式
[Icons]
Name: "{group}\ECBot"; Filename: "{app}\ECBot.exe"
Name: "{group}\Uninstall ECBot"; Filename: "{uninstallexe}"

; 安装完成后自动运行应用程序
[Run]
Filename: "{app}\ECBot.exe"; Description: "Run ECBot"; Flags: nowait postinstall skipifsilent
