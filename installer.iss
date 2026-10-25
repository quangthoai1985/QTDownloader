; Bộ cài QT Downloader (Inno Setup 6) — cài theo người dùng, KHÔNG cần quyền quản trị (UAC).
; Biên dịch: python tools/package_release.py   (hoặc: iscc /DAppVersion=1.1.0 installer.iss sau khi chạy build.bat)
; Kết quả : release\QTDownloader-<phiên bản>-setup.exe
; Cài im lặng: QTDownloader-<ver>-setup.exe /SILENT  hoặc  /VERYSILENT /SUPPRESSMSGBOXES   (thêm /LAUNCHAPP để mở app khi xong)
;
; AppId phải trùng qtdownloader/__init__.py:INNO_APP_ID; AppMutex trùng APP_MUTEX_NAME (test tests/test_installer.py).
; Khoá giao thức / khởi động cùng Windows do APP ghi khi người dùng bật tuỳ chọn (core/integration.py) — bộ cài
; không ghi, nhưng trình gỡ cài đặt xoá chúng (kể cả khoá của tên cũ TDownload) để không để lại lệnh trỏ vào tệp đã xoá.

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\QTDownloader"
#endif
#ifndef OutputDir
  #define OutputDir "release"
#endif
#define AppName "QT Downloader"
#define AppId "QTDownloader"
#define AppExe "QTDownloader.exe"
#define AppDesc "Trình tăng tốc tải xuống đa kết nối: tải tiếp, hàng đợi, lịch hẹn, bắt link từ trình duyệt."
#define RepoUrl "https://github.com/quangthoai1985/QTDownloader"
#define Protocol "qtdownloader"
#define LegacyProtocol "tdownload"
#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
AppId={{60877C1B-878F-46D0-A5B2-F015CCF3F562}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Quang Thoại (quangthoai1985)
AppPublisherURL={#RepoUrl}
AppSupportURL={#RepoUrl}/issues
AppUpdatesURL={#RepoUrl}/releases
AppCopyright=MIT License
VersionInfoVersion={#AppVersion}.0
VersionInfoProductName={#AppName}
VersionInfoDescription=Bộ cài {#AppName}
; Cài theo người dùng: %LOCALAPPDATA%\Programs\QT Downloader — cài/cập nhật/gỡ không cần UAC
PrivilegesRequired=lowest
UsedUserAreasWarning=no
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DefaultGroupName={#AppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename={#AppId}-{#AppVersion}-setup
SetupIconFile=assets\qtdownloader.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=LICENSE
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Trùng APP_MUTEX_NAME trong qtdownloader/__init__.py: bộ cài / gỡ cài đặt nhận ra app đang mở (kể cả dưới khay)
AppMutex=QTDownloader.AppMutex
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "vietnamese"; MessagesFile: "compiler:Default.isl,installer\Vietnamese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Cài đè bản cũ: xoá bộ thư viện cũ để không lẫn tệp của phiên bản trước
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Giấy phép MIT của dự án + giấy phép thư viện đóng kèm (Qt/PySide6 LGPL-3.0, Python PSF, httpx…)
Source: "LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "{#AppDesc}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Win+R «QTDownloader»
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; Cập nhật từ trong app (/SILENT /LAUNCHAPP): mở lại app sau khi cài xong
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: LaunchRequested

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function LaunchRequested(): Boolean;
var
  I: Integer;
begin
  Result := False;
  if not WizardSilent() then
    Exit;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/LAUNCHAPP') = 0 then
      Result := True;
end;

procedure RemoveAppRegistry();
begin
  // Giao thức qtdownloader:// (tuỳ chọn «Cho phép trình duyệt mở QT Downloader») và tdownload:// của bản cũ
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\{#Protocol}');
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\{#LegacyProtocol}');
  // Khởi động cùng Windows (tuỳ chọn trong app) — tên mới và tên cũ
  RegDeleteValue(HKCU, '{#RunKey}', 'QTDownloader');
  RegDeleteValue(HKCU, '{#RunKey}', 'TDownload');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
    RemoveAppRegistry();
  if CurUninstallStep <> usPostUninstall then
    Exit;
  // Dữ liệu người dùng (%LOCALAPPDATA%\QTDownloader: danh sách tải, thiết lập, nhật ký): hỏi trước khi xoá;
  // gỡ im lặng thì giữ lại. Tệp đã tải về (thư mục Downloads) không bao giờ bị đụng tới.
  DataDir := ExpandConstant('{localappdata}\{#AppId}');
  if DirExists(DataDir) and not UninstallSilent() then
    if MsgBox(CustomMessage('RemoveData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(DataDir, True, True, True);
end;
