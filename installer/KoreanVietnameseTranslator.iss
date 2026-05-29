#define MyAppName "Korean-Vietnamese Live Translator"
#define MyAppExeName "KoreanVietnameseTranslator.exe"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Local Classroom Tools"

[Setup]
AppId={{8C85F312-2D8A-43AE-A8B9-39E2775D2CF4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\KoreanVietnameseTranslator
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\installer-output
OutputBaseFilename=KoreanVietnameseTranslatorSetup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
#ifexist "..\assets\app.ico"
SetupIconFile=..\assets\app.ico
#endif

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
