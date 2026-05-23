; Inno Setup script for JobHunter Windows installer
; Requires: Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;
; Build:
;   1. Run: python build.py
;   2. Open this file in Inno Setup Compiler
;   3. Click Build -> Compile
;   Output: dist/JobHunter-Setup.exe

[Setup]
AppName=JobHunter
AppVersion=0.2.0
AppPublisher=Talon Assistant
AppPublisherURL=https://github.com/talon-assistant/jobhunter
DefaultDirName={autopf}\JobHunter
DefaultGroupName=JobHunter
OutputDir=dist
OutputBaseFilename=JobHunter-Setup
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
SetupLogging=yes

[Files]
Source: "dist\JobHunter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\JobHunter"; Filename: "{app}\JobHunter.exe"
Name: "{autodesktop}\JobHunter"; Filename: "{app}\JobHunter.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\JobHunter.exe"; Description: "Launch JobHunter"; Flags: nowait postinstall skipifsilent
