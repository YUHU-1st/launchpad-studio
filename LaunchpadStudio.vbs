Option Explicit
Dim shell, fso, base, pythonw, app, setup, command, rc
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = base & "\.venv\Scripts\pythonw.exe"
app = base & "\app.py"
setup = base & "\setup.ps1"

If Not fso.FileExists(pythonw) Then
    command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & setup & """"
    rc = shell.Run(command, 0, True)
    If rc <> 0 Then
        MsgBox "Launchpad Studio setup failed. Please check data\crash.log.", 16, "Launchpad Studio"
        WScript.Quit 1
    End If
    If Not fso.FileExists(pythonw) Then
        MsgBox "Launchpad Studio runtime was not found after setup.", 16, "Launchpad Studio"
        WScript.Quit 1
    End If
End If

command = """" & pythonw & """ """ & app & """"
shell.Run command, 0, False
