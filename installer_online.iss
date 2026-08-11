; -*- coding: utf-8 -*-
; ============================================================================
; VAI_E_SmartAnnotator 在线安装器 Inno Setup 脚本
;
; 用途: 生成轻量级在线安装器（约 3 MB），安装时从 Gitee Release 下载
;       CPU 版或 GPU 版压缩包并自动解压安装。
;
; 编译: ISCC.exe installer_online.iss
; 自定义 URL: ISCC.exe /DCPU_DOWNLOAD_URL="https://..." /DGPU_DOWNLOAD_URL="https://..." installer_online.iss
;
; 作者: BaiBinnan
; 日期: 2026-08-11
; ============================================================================

#define MyAppName          "VAI_E_SmartAnnotator"
#define MyAppVersion       "1.2.0"
#define MyAppPublisher     "武汉川丰软件"
#define MyAppExeName       "VAI_E_SmartAnnotator.exe"
#define MyAppDescription   "VAI_E Smart Annotator"

; ===== 下载 URL 配置（可通过 /D 命令行参数覆盖）=====
; 默认 URL 指向 Gitee Release（build.py 编译时通过 /D 参数覆盖为 download_config.ini 中的值）
; 格式: https://gitee.com/{用户}/{仓库}/releases/download/{版本}/{文件名}
#ifndef CPU_DOWNLOAD_URL
  #define CPU_DOWNLOAD_URL "https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases/download/1.2.0_cpu/VAI_E_SmartAnnotator_CPU_1.2.0.zip"
#endif
#ifndef GPU_DOWNLOAD_URL
  #define GPU_DOWNLOAD_URL "https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases/download/1.2.0_gpu/VAI_E_SmartAnnotator_GPU_1.2.0.zip"
#endif

[Setup]
; 应用信息
AppId={{CFSoft-VAI-E-SmartAnnotator}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments={#MyAppDescription} (Online Setup)

; 安装目录
DefaultDirName={autopf}\{#MyAppPublisher}\{#MyAppName}
DefaultGroupName={#MyAppPublisher}\{#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequiredOverridesAllowed=dialog

; 卸载信息
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

; 输出配置（安装程序输出到 build/installer_output/）
OutputDir=build\installer_output
OutputBaseFilename=VAI_E_SmartAnnotator_OnlineSetup
SetupIconFile=app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; 版本信息
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppDescription} Online Setup
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

; 注意: 在线安装器没有 [Files] 段，文件在运行时下载并解压
; [Icons] 段在 PrepareToInstall（解压）之后执行，因此文件已存在

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
; 卸载时尝试关闭运行中的程序
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
; 卸载时清理用户配置与日志
Type: filesandordirs; Name: "{userappdata}\{#MyAppPublisher}\{#MyAppName}"

[Code]
var
  // 版本选择页面（CPU / GPU）
  ModePage: TInputOptionWizardPage;
  // 下载页面（TDownloadWizardPage 提供进度条 + 取消按钮）
  DownloadPage: TDownloadWizardPage;
  // 下载的 zip 文件临时路径
  DownloadedZipPath: String;
  // 用户选择的模式（'CPU' 或 'GPU'）
  SelectedMode: String;

// ============================================================================
// 初始化向导：创建 CPU/GPU 版本选择页面 + 下载页面
// ============================================================================
procedure InitializeWizard();
begin
  ModePage := CreateInputOptionPage(
    wpWelcome,
    '选择安装版本',
    '请选择适合您系统的版本',
    'CPU 版无需 NVIDIA GPU，体积更小；GPU 版需要 NVIDIA GPU + CUDA，推理速度更快。',
    True, False
  );
  ModePage.Add('CPU 版（推荐，无需 NVIDIA GPU，下载约 94 MB）');
  ModePage.Add('GPU 版（需要 NVIDIA GPU + CUDA 12.x，下载约 250 MB）');
  ModePage.SelectedValueIndex := 0;  // 默认选中 CPU 版

  // 创建下载页面（3 参数：标题、描述、进度回调或 nil）
  // 传 nil 使用内置进度显示，TDownloadWizardPage 自带进度条和取消按钮
  DownloadPage := CreateDownloadPage(
    '正在下载安装包',
    '请稍候，正在从 Gitee Release 下载安装文件...',
    nil
  );
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

// ============================================================================
// 版本选择页面的"下一步"按钮：触发下载
// ============================================================================
function NextButtonClick(CurPageID: Integer): Boolean;
var
  DownloadUrl: String;
  FileName: String;
begin
  // 仅在版本选择页面点击下一步时触发下载
  if CurPageID = ModePage.ID then
  begin
    // 根据用户选择确定下载 URL
    if ModePage.SelectedValueIndex = 0 then
    begin
      SelectedMode := 'CPU';
      DownloadUrl := '{#CPU_DOWNLOAD_URL}';
    end
    else
    begin
      SelectedMode := 'GPU';
      DownloadUrl := '{#GPU_DOWNLOAD_URL}';
    end;

    // 从 URL 提取文件名（Gitee Release URL 最后一段即为文件名）
    FileName := ExtractFileName(DownloadUrl);
    DownloadedZipPath := ExpandConstant('{tmp}\') + FileName;

    // 清空下载页面并添加下载任务
    // Add(Url, FileName, RequiredSHA256) — SHA256 传空字符串表示不校验
    DownloadPage.Clear;
    DownloadPage.Add(DownloadUrl, FileName, '');

    // 显示下载页面并执行下载（阻塞直到完成或取消）
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;  // 下载失败会抛出异常
      except
        // 下载失败时显示详细错误信息
        SuppressibleMsgBox(
          '下载失败！请检查网络连接后重试。' + #13#10 + #13#10 +
          '下载地址: ' + DownloadUrl + #13#10 + #13#10 +
          '错误信息: ' + GetExceptionMessage,
          mbError, MB_OK, IDOK
        );
        Result := False;
        Exit;
      end;
    finally
      DownloadPage.Hide;
    end;

    // 验证下载文件确实存在
    if not FileExists(DownloadedZipPath) then
    begin
      SuppressibleMsgBox(
        '下载文件未找到: ' + DownloadedZipPath + #13#10 +
        '可能是 URL 配置错误或网络中断。',
        mbError, MB_OK, IDOK
      );
      Result := False;
      Exit;
    end;
  end;

  Result := True;
end;

// ============================================================================
// 准备安装：在正式安装步骤前解压下载的 zip 文件
// ============================================================================
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  DestDir: String;
  ResultCode: Integer;
  PowerShellCmd: String;
begin
  DestDir := ExpandConstant('{app}');

  // 创建安装目录
  if not DirExists(DestDir) then
    CreateDir(DestDir);

  // 使用 PowerShell 解压 zip 文件
  // Expand-Archive 是 Windows 10+ 内置的 PowerShell 命令
  PowerShellCmd := '-NoProfile -ExecutionPolicy Bypass -Command "' +
    'Expand-Archive -Path ''' + DownloadedZipPath + ''' -DestinationPath ''' + DestDir + ''' -Force' +
    '"';

  WizardForm.StatusLabel.Caption := '正在解压 ' + SelectedMode + ' 版安装包...';
  WizardForm.ProgressGauge.Style := npbstMarquee;

  if not ShellExec('open', 'powershell.exe', PowerShellCmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Result := '无法启动 PowerShell 进行解压。请确保系统已安装 PowerShell。';
    Exit;
  end;

  if ResultCode <> 0 then
  begin
    Result := '解压失败（PowerShell 退出码: ' + IntToStr(ResultCode) + '）。' +
      '可能原因: 磁盘空间不足或 zip 文件损坏。';
    Exit;
  end;

  // 验证主程序文件是否存在
  if not FileExists(DestDir + '\{#MyAppExeName}') then
  begin
    Result := '解压后未找到主程序文件 {#MyAppExeName}。zip 文件可能已损坏。';
    Exit;
  end;

  WizardForm.StatusLabel.Caption := '解压完成，正在配置...';
  Result := '';  // 空字符串表示成功
end;

// ============================================================================
// 安装前初始化
// ============================================================================
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

// ============================================================================
// 卸载前初始化
// ============================================================================
function InitializeUninstall(): Boolean;
begin
  Result := True;
end;
