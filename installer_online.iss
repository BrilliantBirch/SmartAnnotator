; -*- coding: utf-8 -*-
; ============================================================================
; BrilliantAnnotator 在线安装器 Inno Setup 脚本
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

#define MyAppName          "BrilliantAnnotator"
#define MyAppVersion       "1.2.0"
#define MyAppPublisher     "BrilliantBirch"
#define MyAppExeName       "BrilliantAnnotator.exe"
#define MyAppDescription   "BrilliantAnnotator"

; ===== 下载 URL 配置（可通过 /D 命令行参数覆盖）=====
; 默认 URL 指向 Gitee Release（build.py 编译时通过 /D 参数覆盖为 download_config.ini 中的值）
; 格式: https://gitee.com/{用户}/{仓库}/releases/download/{版本}/{文件名}
; 分卷: parts>1 时 URL 为基础 URL（以 .part 结尾），追加 001/002/... 下载各分卷
#ifndef CPU_DOWNLOAD_URL
  #define CPU_DOWNLOAD_URL "https://gitee.com/baibinnan/brilliantannotator/releases/download/v1.2.0/BrilliantAnnotator_CPU_1.2.0.zip"
#endif
#ifndef GPU_DOWNLOAD_URL
  #define GPU_DOWNLOAD_URL "https://gitee.com/baibinnan/brilliantannotator/releases/download/v1.2.0/BrilliantAnnotator_GPU_1.2.0.zip.part"
#endif
#ifndef CPU_PARTS
  #define CPU_PARTS "1"
#endif
#ifndef GPU_PARTS
  #define GPU_PARTS "6"
#endif

[Setup]
; 应用信息
AppId={{BrilliantAnnotator}}
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
OutputBaseFilename=BrilliantAnnotator_OnlineSetup
SetupIconFile=app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; 版本信息
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppDescription} Online Setup
VersionInfoProductName=BrilliantAnnotator
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
; 在线安装器无 [Files] 段，Inno Setup 不知道解压的文件
; 必须显式删除整个安装目录（包含 exe、依赖文件夹、运行时生成的 Log 等）
Type: filesandordirs; Name: "{app}"
; 清理用户配置与日志（运行时在 %APPDATA% 中生成）
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
  ModePage.Add('GPU 版（需要 NVIDIA GPU + CUDA 12.x，下载约 549 MB，分 6 个分卷）');
  ModePage.SelectedValueIndex := 0;  // 默认选中 CPU 版

  // 创建下载页面（3 参数：标题、描述、进度回调或 nil）
  // 传 nil 使用内置进度显示，TDownloadWizardPage 自带进度条和取消按钮
  DownloadPage := CreateDownloadPage(
    '正在下载安装包',
    '请稍候，正在下载安装文件...',
    nil
  );
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

// ============================================================================
// 版本选择页面的"下一步"按钮：触发下载（支持分卷下载与合并）
// ============================================================================
function NextButtonClick(CurPageID: Integer): Boolean;
var
  DownloadUrl: String;
  FileName: String;
  PartCount: Integer;
  PartIndex: Integer;
  PartSuffix: String;
  MergeZipName: String;
  ResultCode: Integer;
  PowerShellCmd: String;
  TmpDir: String;
begin
  // 仅在版本选择页面点击下一步时触发下载
  if CurPageID = ModePage.ID then
  begin
    // 根据用户选择确定下载 URL 和分卷数
    if ModePage.SelectedValueIndex = 0 then
    begin
      SelectedMode := 'CPU';
      DownloadUrl := '{#CPU_DOWNLOAD_URL}';
      PartCount := StrToInt('{#CPU_PARTS}');
    end
    else
    begin
      SelectedMode := 'GPU';
      DownloadUrl := '{#GPU_DOWNLOAD_URL}';
      PartCount := StrToInt('{#GPU_PARTS}');
    end;

    TmpDir := ExpandConstant('{tmp}');
    DownloadPage.Clear;

    if PartCount = 1 then
    begin
      // 单文件下载（CPU 版或小体积包）
      FileName := ExtractFileName(DownloadUrl);
      DownloadedZipPath := TmpDir + '\' + FileName;
      DownloadPage.Add(DownloadUrl, FileName, '');
    end
    else
    begin
      // 分卷下载：URL 为基础 URL（以 .part 结尾），追加 001/002/... 下载各分卷
      // 下载后合并为单个 zip 文件
      MergeZipName := 'BrilliantAnnotator_' + SelectedMode + '.zip';
      DownloadedZipPath := TmpDir + '\' + MergeZipName;
      for PartIndex := 1 to PartCount do
      begin
        PartSuffix := Format('%.3d', [PartIndex]);
        // URL: 基础URL + 001/002/...，保存文件名: xxx.zip.part001
        DownloadPage.Add(DownloadUrl + PartSuffix, MergeZipName + '.part' + PartSuffix, '');
      end;
    end;

    // 显示下载页面并执行下载（阻塞直到完成或取消）
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;  // 下载失败会抛出异常
      except
        // 下载失败时显示详细错误信息
        SuppressibleMsgBox(
          '下载失败！请检查网络连接后重试。' + #13#10 + #13#10 +
          '错误信息: ' + GetExceptionMessage,
          mbError, MB_OK, IDOK
        );
        Result := False;
        Exit;
      end;
    finally
      DownloadPage.Hide;
    end;

    // 分卷合并（仅 PartCount > 1 时）
    if PartCount > 1 then
    begin
      WizardForm.StatusLabel.Caption := '正在合并 ' + IntToStr(PartCount) + ' 个分卷文件...';
      WizardForm.ProgressGauge.Style := npbstMarquee;
      // PowerShell: 按文件名排序读取所有分卷，合并为单个 zip
      PowerShellCmd := '-NoProfile -ExecutionPolicy Bypass -Command "' +
        '$parts = Get-ChildItem -Path ''' + TmpDir + '\' + MergeZipName + '.part*'' | Sort-Object Name; ' +
        '$out = [System.IO.File]::Create(''' + DownloadedZipPath + '''); ' +
        'foreach ($p in $parts) { $in = [System.IO.File]::OpenRead($p.FullName); $in.CopyTo($out); $in.Close() }; ' +
        '$out.Close()' +
        '"';
      if not ShellExec('open', 'powershell.exe', PowerShellCmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      begin
        SuppressibleMsgBox(
          '分卷合并失败！PowerShell 退出码: ' + IntToStr(ResultCode) + #13#10 +
          '请确保系统已安装 PowerShell 且磁盘空间充足。',
          mbError, MB_OK, IDOK
        );
        Result := False;
        Exit;
      end;
    end;

    // 验证合并后的 zip 文件存在
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

// ============================================================================
// 卸载步骤回调：确保完全清理
// 在线安装器无 [Files] 段，Inno Setup 未记录解压文件，文件锁定会导致
// [UninstallDelete] 删除失败，因此需要：
//   1. 卸载前强制关闭程序并等待文件句柄释放
//   2. 卸载后使用 DelTree 二次清理残留（含运行时生成的 Log 目录）
// ============================================================================
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // 卸载开始前：强制关闭程序并等待文件句柄释放
    ShellExec('open', 'taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1000);  // 等待 1 秒确保 OS 释放文件句柄
  end;

  if CurUninstallStep = usPostUninstall then
  begin
    // 备用清理：删除 [UninstallDelete] 可能因文件锁定遗漏的残留
    DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
