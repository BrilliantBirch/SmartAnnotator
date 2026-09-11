; -*- coding: utf-8 -*-
; ============================================================================
; BrilliantAnnotator 在线安装器 Inno Setup 脚本
;
; 用途: 生成轻量级在线安装器（约 3 MB），安装时从 Gitee Release 下载
;       CPU 版或 GPU 版压缩包并自动解压安装。
;       同时支持静默安装（/SILENT /MODE=CPU|GPU），供应用内"检查更新"
;       下载后静默拉起完成在线升级。
;
; 编译: ISCC.exe installer_online.iss
; 自定义 URL: ISCC.exe /DCPU_DOWNLOAD_URL="https://..." /DGPU_DOWNLOAD_URL="https://..." installer_online.iss
; 自定义版本: ISCC.exe /DMyAppVersion="2.1.1" installer_online.iss
;             （build.py 编译时传入 version_manager 的 PRODUCT_VERSION）
;
; 静默安装: BrilliantAnnotator_OnlineSetup.exe /SILENT /MODE=CPU
;           （/MODE 缺省 CPU；应用内更新由客户端自动检测当前模式传入）
;
; 作者: BaiBinnan
; 日期: 2026-08-11
; 更新: 2026-09-09 版本号 define 化（/DMyAppVersion 传入，消除硬编码）；
;       新增静默安装支持（/MODE 参数 + PrepareToInstall 阶段补下载）；
;       解压前 taskkill 关闭运行中的旧版本（在线更新覆盖安装）；
;       安装完成写入 install_mode.txt 模式标记（客户端更新检测用）
; 更新: 2026-09-11 静默更新体验闭环：PrepareToInstall 错误改经代码
;       MsgBox 显示（/SUPPRESSMSGBOXES 会抑制 Inno 内置错误框，原实现
;       静默失败无任何提示）；静默安装完成后自动启动新版本（原 [Run]
;       skipifsilent 导致更新完成后无任何反馈）
; 更新: 2026-09-11 解压与磁盘清理重构：zip 解压改用 Inno 原生
;       [Files] extractarchive（ArchiveExtraction=full，is7z.dll 引擎），
;       进度条按 zip 条目真实推进（修复原 PowerShell Expand-Archive
;       走马灯"卡 10% 后瞬间 100%"观感）；分卷合并后立即删除分卷、
;       安装完成后删除合并 zip，降低用户磁盘占用
; 更新: 2026-09-11 修复静默更新模式失效 bug：Inno 静默安装仍会依页
;       触发 NextButtonClick，ModePage 默认选中 CPU 抢先下载并置
;       DownloadCompleted，短路 /MODE=GPU 补下载分支（GPU 版静默更新
;       会装成 CPU 包）；修复后静默下载统一由 PrepareToInstall 完成
; ============================================================================

#define MyAppName          "BrilliantAnnotator"
; 产品版本：build.py 编译时经 /DMyAppVersion 传入（缺省占位 1.2.0）
#ifndef MyAppVersion
  #define MyAppVersion     "1.2.0"
#endif
#define MyAppPublisher     "BrilliantBirch"
#define MyAppExeName       "BrilliantAnnotator.exe"
#define MyAppDescription   "BrilliantAnnotator"

; ===== 下载 URL 配置（可通过 /D 命令行参数覆盖）=====
; 默认 URL 指向 Gitee Release（build.py 编译时通过 /D 参数覆盖为 download_config.ini 中的值）
; 格式: https://gitee.com/{用户}/{仓库}/releases/download/{版本}/{文件名}
; 分卷: parts>1 时 URL 为基础 URL（以 .part 结尾），追加 001/002/... 下载各分卷
#ifndef CPU_DOWNLOAD_URL
  #define CPU_DOWNLOAD_URL "https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases/download/v2.1.0/BrilliantAnnotator_CPU_2.1.0.zip"
#endif
#ifndef GPU_DOWNLOAD_URL
  #define GPU_DOWNLOAD_URL "https://gitee.com/baibinnan/vai_-e_-smart-annotator/releases/download/v2.1.0/BrilliantAnnotator_GPU_2.1.0.zip.part"
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
; 允许向导页与命令行（/ALLUSERS|/CURRENTUSER）覆盖安装权限模式
PrivilegesRequiredOverridesAllowed=dialog commandline

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
; 将四段式产品版本号（如 2.1.1 → 2.1.1.0）拼给 VersionInfoProductVersion
VersionInfoProductVersion={#MyAppVersion}.0
VersionInfoVersion={#MyAppVersion}.0

; 归档解压引擎：full 使用 is7z.dll（7-Zip 全格式引擎），支持 .zip
; （basic/enhanced 仅支持 .7z）；编译器自动将 DLL 打包进安装器
ArchiveExtraction=full

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

; 运行时下载的 zip 经 Inno 原生解压引擎安装到 {app}：
; external 指向 {code:GetZipSource}（下载合并后的临时 zip），
; extractarchive 由安装引擎按 zip 条目解压并驱动真实进度条，
; 失败自动中止并回滚安装
[Files]
Source: "{code:GetZipSource}"; DestDir: "{app}"; Flags: external extractarchive recursesubdirs createallsubdirs ignoreversion

; [Icons] 段在安装（解压）之后执行，因此文件已存在

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
  // 下载阶段错误信息（空字符串 = 下载成功）；由 DownloadAndMerge 填写，
  // 调用方（交互 NextButtonClick / 静默 PrepareToInstall）负责展示
  DownloadError: String;
  // 下载+合并是否已完成（交互模式在 NextButtonClick 完成；静默模式
  // 跳过向导页，需在 PrepareToInstall 补做）
  DownloadCompleted: Boolean;

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
// 下载 + 分卷合并公共过程（交互模式：版本选择页下一步触发；
// 静默模式：PrepareToInstall 阶段补做），错误写入全局 DownloadError
// ============================================================================
procedure DownloadAndMerge();
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
  DownloadError := '';

  // 根据已选模式确定下载 URL 和分卷数
  if SelectedMode = 'CPU' then
  begin
    DownloadUrl := '{#CPU_DOWNLOAD_URL}';
    PartCount := StrToInt('{#CPU_PARTS}');
  end
  else
  begin
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
      // 下载失败时记录详细错误信息（由调用方展示）
      DownloadError := '下载失败！请检查网络连接后重试。' + #13#10 + #13#10 +
        '错误信息: ' + GetExceptionMessage;
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
      DownloadError :=
        '分卷合并失败！PowerShell 退出码: ' + IntToStr(ResultCode) + #13#10 +
        '请确保系统已安装 PowerShell 且磁盘空间充足。';
      Exit;
    end;
  end;

  // 验证合并后的 zip 文件存在
  if not FileExists(DownloadedZipPath) then
  begin
    DownloadError :=
      '下载文件未找到: ' + DownloadedZipPath + #13#10 +
      '可能是 URL 配置错误或网络中断。';
    Exit;
  end;

  // 分卷已合并为完整 zip，立即删除分卷释放磁盘
  // （GPU 版 6 分卷约 550MB，与合并 zip 并存时占用峰值减半）
  if PartCount > 1 then
  begin
    for PartIndex := 1 to PartCount do
      DeleteFile(TmpDir + '\' + MergeZipName + '.part' + Format('%.3d', [PartIndex]));
  end;

  // 全部成功：标记下载完成
  DownloadCompleted := True;
end;

// ============================================================================
// 版本选择页面的"下一步"按钮：记录所选模式并触发下载（仅交互模式）
// ============================================================================
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  // 静默模式下 Inno 仍会依页序触发 NextButtonClick：ModePage 默认选中
  // CPU 会抢先下载 CPU 包、令 DownloadCompleted 置 True，进而短路
  // PrepareToInstall 的 /MODE 补下载分支——静默更新永远装成 CPU 版。
  // 故静默时此处置空，下载统一由 PrepareToInstall 的 /MODE 分支完成
  if WizardSilent() then
  begin
    Result := True;
    Exit;
  end;

  // 仅在版本选择页面点击下一步时触发下载
  if CurPageID = ModePage.ID then
  begin
    // 根据用户选择确定模式（下载逻辑统一走 DownloadAndMerge）
    if ModePage.SelectedValueIndex = 0 then
      SelectedMode := 'CPU'
    else
      SelectedMode := 'GPU';

    DownloadAndMerge();
    if DownloadError <> '' then
    begin
      // 统一用代码 MsgBox（交互模式与 SuppressibleMsgBox 等效，且不被
      // /SUPPRESSMSGBOXES 抑制，静默场景错误始终可见）
      MsgBox(DownloadError, mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;

  Result := True;
end;

// ============================================================================
// 准备安装实际逻辑：静默模式补下载 → 关闭运行中的旧版本 → 创建目录
// zip 解压由 [Files] 的 extractarchive 条目承担（真实进度条，失败回滚），
// install_mode.txt 模式标记与 zip 清理在 CurStepChanged(ssPostInstall) 完成
// 错误写入 Err（空字符串 = 成功），由包装函数 PrepareToInstall 统一展示
// ============================================================================
procedure DoPrepareToInstall(var Err: String);
var
  DestDir: String;
  ResultCode: Integer;
  Mode: String;
begin
  Err := '';  // 空字符串表示成功

  // ===== 静默模式补下载（/SILENT 下向导页被跳过，NextButtonClick 不会触发）=====
  if (not DownloadCompleted) and WizardSilent() then
  begin
    // /MODE=CPU|GPU 命令行参数（应用内更新传入检测到的模式），缺省 CPU
    Mode := Uppercase(ExpandConstant('{param:MODE}'));
    if (Mode <> 'CPU') and (Mode <> 'GPU') then
      Mode := 'CPU';
    SelectedMode := Mode;
    DownloadAndMerge();
    if DownloadError <> '' then
    begin
      Err := DownloadError;
      Exit;
    end;
  end;

  // ===== 在线更新场景：先关闭运行中的旧版本并等待句柄释放 =====
  DestDir := ExpandConstant('{app}');
  ShellExec('open', 'taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1500);

  // 创建安装目录（{app} 尚不存在时 [Files] 也会创建，此处显式创建保目录语义）
  if not DirExists(DestDir) then
    CreateDir(DestDir);
end;

// ============================================================================
// 准备安装（Inno 回调）：委托 DoPrepareToInstall，失败原因经代码 MsgBox
// 展示——/SUPPRESSMSGBOXES 只抑制 Inno 内置错误框，代码 MsgBox 不受抑制，
// 确保应用内静默更新失败时用户能看到原因（而非安装器无声退出）
// ============================================================================
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Err: String;
begin
  Err := '';
  DoPrepareToInstall(Err);
  if Err <> '' then
  begin
    if WizardSilent() then
      MsgBox(Err, mbCriticalError, MB_OK);
    Result := Err;
  end
  else
    Result := '';
end;

// ============================================================================
// 安装前初始化
// ============================================================================
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

// ============================================================================
// 安装步骤回调：写模式标记 + 清理 zip + 静默安装完成后自动启动新版本
// ============================================================================
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // ===== 写安装模式标记（供应用内"检查更新"识别 CPU/GPU 版本） =====
    // 解压已由 [Files] 完成（失败会在该阶段自动中止），此处主程序必在
    SaveStringToFile(ExpandConstant('{app}\install_mode.txt'), SelectedMode, False);

    // ===== 清理合并 zip：解压完成后压缩包已无用，立即释放磁盘 =====
    // （CPU 约 94MB / GPU 约 550MB；{tmp} 在安装器退出时本会自动清空，
    //  此处显式删除可提前释放并在异常退出时兜底）
    if DownloadCompleted then
      DeleteFile(DownloadedZipPath);

    // [Run] 的"立即启动"带 skipifsilent，静默更新完成后安装器直接退出，
    // 用户感知不到更新结果；此处补启动新版本形成更新闭环（交互安装仍
    // 由 [Run] 复选框决定，WizardSilent 判断保证不重复启动）
    if WizardSilent() then
      ShellExec('open', ExpandConstant('{app}\{#MyAppExeName}'), '', '',
        SW_SHOW, ewNoWait, ResultCode);
  end;
end;

// ============================================================================
// [Files] external 条目回调：返回待解压 zip 的本地路径
// 调用发生在安装（解压）阶段，此时下载/合并必然已完成
// ============================================================================
function GetZipSource(Param: String): String;
begin
  Result := DownloadedZipPath;
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
