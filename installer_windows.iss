; ============================================================================
;  PDFeverything — Windows 安装包定义 (Inno Setup 6)
; ============================================================================
;
;  用法 / Usage:
;    ISCC.exe installer_windows.iss /DMyAppVersion=1.9.0
;
;  全部路径由本文件用 SourcePath 自行推导（= 本脚本所在目录），因此无论从哪个
;  工作目录调用 ISCC 都能正确找到资源，无需传路径参数。
;  可覆盖的宏：MyAppVersion / MySourceExe / MyOutputDir / MyLicenseFile / MyIconFile
;
;  要求：Inno Setup 6.0+（中文向导需要 Languages\ChineseSimplified.isl，
;        该文件随 Inno Setup 6 官方安装包一起分发）。
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
; 默认「仅为我安装」，不弹 UAC；用户仍可在向导首屏切换为全机器安装。
PrivilegesRequired=lowest
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
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
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
