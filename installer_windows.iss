; ============================================================================
;  PDFeverything — Windows 安装包定义 (Inno Setup 6)
; ============================================================================
;
;  用法 / Usage:
;    ISCC.exe installer_windows.iss /DMyAppVersion=1.9.0
;
;  全部路径由本文件用 SourcePath 自行推导（= 本脚本所在目录），因此无论从哪个
;  工作目录调用 ISCC 都能正确找到资源，无需传路径参数。
;  可覆盖的宏：MyAppVersion / MySourceExe / MyOutputDir / MyLicenseFile /
;             MyIconFile / MyChineseMessages
;
;  要求：Inno Setup 6.0+。中文向导依赖 ChineseSimplified.isl，见下方探测逻辑：
;        编译器自带就用自带的，否则用 resources\ChineseSimplified.isl（随仓库分发），
;        都没有则退化为纯英文向导。
;
;  产物：dist\PDFeverything_Setup_v<version>.exe
; ============================================================================

;  SourcePath 是 ISPP 预定义变量（= 本 .iss 所在目录），但**不带**结尾反斜杠
;  （官方例子到处写 AddBackslash(SourcePath) + "..."），所以必须过一遍 AddBackslash，
;  否则拼出来会是 "...\PDFeverythingdist\PDFeverything.exe"。
#ifndef MyProjectRoot
  #define MyProjectRoot SourcePath
#endif
#define MyProjectRootDir AddBackslash(MyProjectRoot)
#ifndef MyAppVersion
  #define MyAppVersion "1.9.0"
#endif
#ifndef MySourceExe
  #define MySourceExe MyProjectRootDir + "dist\PDFeverything.exe"
#endif
#ifndef MyOutputDir
  #define MyOutputDir MyProjectRootDir + "dist"
#endif
#ifndef MyLicenseFile
  #define MyLicenseFile MyProjectRootDir + "resources\LICENSE.txt"
#endif
#ifndef MyIconFile
  #define MyIconFile MyProjectRootDir + "resources\app_icon.ico"
#endif

;  中文向导的翻译文件按「编译器自带 → 仓库里 vendors 的那份 → 放弃中文」三级降级：
;    * Inno Setup 6.7.x 把 ChineseSimplified.isl 放在 Languages\Unofficial\ 下
;    * 更早的版本放在 Languages\ 下
;    * 有些精简安装（CI 上 Chocolatey 装的就是）干脆两个都没有 —— 上次构建就是
;      因此报 "Couldn't open include file ... ChineseSimplified.isl"
;  探测顺序保证本地装任何版本的 Inno Setup 都用它自带的那份（版本必然匹配），
;  探测不到才退回仓库里这份（对应 6.7.1），全都没有就只出英文向导，绝不失败。
#ifndef MyChineseMessages
  #if FileExists(AddBackslash(CompilerPath) + "Languages\ChineseSimplified.isl")
    #define MyChineseMessages AddBackslash(CompilerPath) + "Languages\ChineseSimplified.isl"
  #else
    #if FileExists(AddBackslash(CompilerPath) + "Languages\Unofficial\ChineseSimplified.isl")
      #define MyChineseMessages AddBackslash(CompilerPath) + "Languages\Unofficial\ChineseSimplified.isl"
    #else
      #if FileExists(MyProjectRootDir + "resources\ChineseSimplified.isl")
        #define MyChineseMessages MyProjectRootDir + "resources\ChineseSimplified.isl"
      #endif
    #endif
  #endif
#endif

#define MyAppName "PDFeverything"
#define MyAppExeName "PDFeverything.exe"
#define MyAppPublisher "Lezheng2333"
#define MyAppURL "https://github.com/Lezheng2333/PDFeverything"

[Setup]
; AppId 是安装包的永久身份，升级/卸载全靠它，任何情况下都不要改动。
AppId={{7C1F4E62-2B9D-4A57-9E31-5D8A6F0C3B74}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile={#MyLicenseFile}
OutputDir={#MyOutputDir}
OutputBaseFilename=PDFeverything_Setup_v{#MyAppVersion}
SetupIconFile={#MyIconFile}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 默认装进 C:\Program Files\PDFeverything —— README.md（中英两处）和 mcp/README.md
; 里的 Claude Desktop / Code 配置写死了这个路径，改这里必须同步改那三处。
; 保留「安装模式」选择页：没有管理员权限的用户仍可改装到 %LOCALAPPDATA%\Programs。
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
; x64compatible 是 Inno 6.3+ 的新名字，6.3 之前只认 x64。
#if VER >= EncodeVer(6,3,0,0)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#else
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
#endif

[Languages]
#ifdef MyChineseMessages
Name: "chinesesimplified"; MessagesFile: "{#MyChineseMessages}"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MySourceExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyLicenseFile}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
