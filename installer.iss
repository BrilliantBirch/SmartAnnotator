; -*- coding: utf-8 -*-
; ============================================================================
; VAI_E_SmartAnnotator Inno Setup 安装脚本
;
; 用途: 将 PyInstaller 打包产物制作成带安装向导的 Setup.exe
; 编译: ISCC.exe installer.iss
;
; 作者: BaiBinnan
; 日期: 2026-08-11
; ============================================================================

#define MyAppName          "VAI_E_SmartAnnotator"
#define MyAppVersion       "1.2.0"
#define MyAppPublisher     "武汉川丰软件"
#define MyAppExeName       "VAI_E_SmartAnnotator.exe"
#define MyAppDescription   "VAI_E Smart Annotator"

; 支持命令行 /D 参数覆盖（build.py 传递 /DMyDistDir=... /DOutputSuffix=... /DMyMode=...）
; 默认路径指向 build/dist/（独立编译时使用，build.py 会通过 /D 覆盖为 build/dist_cpu/... 等）
#ifndef MyDistDir
  #define MyDistDir          "build\dist\VAI_E_SmartAnnotator"
#endif
#ifndef OutputSuffix
  #define OutputSuffix       ""
#endif
#ifndef MyMode
  #define MyMode             ""
#endif

[Setup]
; 应用信息
AppId={{CFSoft-VAI-E-SmartAnnotator}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments={#MyAppDescription}{#MyMode}

; 安装目录（按用户/全局安装自动选择 Program Files）
DefaultDirName={autopf}\{#MyAppPublisher}\{#MyAppName}
DefaultGroupName={#MyAppPublisher}\{#MyAppName}

; 不允许在用户层安装（保证快捷方式路径一致），允许自定义目录
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequiredOverridesAllowed=dialog

; 卸载信息
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

; 输出配置（安装程序输出到 build/installer_output/）
OutputDir=build\installer_output
OutputBaseFilename=VAI_E_SmartAnnotator_Setup{#OutputSuffix}
SetupIconFile=app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; 版本信息（与 version_manager.py 一致）
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppDescription}
VersionInfoProductName=VAI_E
VersionInfoProductVersion=1.2.0.0
VersionInfoVersion=1.2.0.0

[Languages]
; 中文语言文件未内置 Inno Setup 6.7.3，如需中文安装界面：
; 1. 从 https://github.com/jrsoftware/issrc 下载 ChineseSimplified.isl
; 2. 放入 Inno Setup 安装目录的 Languages\ 子目录
; 3. 取消下一行注释
; Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"; Flags: checkedonce
Name: "quicklaunchicon"; Description: "创建快速启动栏快捷方式"; GroupDescription: "附加选项:"; Flags: checkedonce

[Files]
; 打包产物全部复制（递归包含子目录）
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单快捷方式
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

; 桌面快捷方式（可选）
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

; 快速启动栏快捷方式（可选）
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
; 安装完成后可选启动程序
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; 卸载时尝试关闭运行中的程序（通过 taskkill）
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
; 卸载时清理用户配置与日志（Type: filesandordirs 会删除目录及内容）
Type: filesandordirs; Name: "{userappdata}\{#MyAppPublisher}\{#MyAppName}"

[Code]
// 安装前初始化（预留扩展点：版本检测、旧版卸载检查等）
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

// 卸载前初始化
function InitializeUninstall(): Boolean;
begin
  Result := True;
end;
