; Instalador do Importador Zabbix (Inno Setup 6)
;
; Compilar com:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalador.iss
;
; Instalacao POR USUARIO (sem precisar de administrador) em
; %LOCALAPPDATA%\Programs\Importador Zabbix. Essa pasta e gravavel, entao os
; relatorios continuam sendo salvos ao lado do executavel.

#define AppName "Importador Zabbix"
#define AppVersion "1.5.0"
#define AppPublisher "L&K Tecnologia"
#define AppExeName "ImportadorZabbix.exe"
#define SourceExe "dist\ImportadorZabbix.exe"
#define SourceIcon "app\assets\app_icon.ico"

[Setup]
; O AppId foi trocado DE PROPOSITO nesta versao por causa da colisao de nome com o
; app do NetBox: quem tinha a versao antiga instalada precisa instalar esta por cima
; manualmente; nao ha upgrade automatico a partir do AppId antigo.
AppId={{411C126F-367A-4264-842E-C9BF101D419C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Instalador do {#AppName}
VersionInfoCompany={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=ImportadorZabbixSetup-{#AppVersion}
SetupIconFile={#SourceIcon}
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos adicionais:"

[Files]
Source: {#SourceExe}; DestDir: {app}; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName} agora"; Flags: nowait postinstall skipifsilent
