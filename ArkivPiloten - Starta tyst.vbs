Option Explicit

' Console-free Windows entry point. The bootstrap and GUI both run hidden;
' setup questions, if needed, are ordinary Windows dialogs.
Dim shell, fso, batchPath, command, exitCode, appDir, desktopPath, programsPath, appMenuPath
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)

If WScript.Arguments.Count > 0 Then
    batchPath = WScript.Arguments(0)
Else
    batchPath = fso.BuildPath(appDir, _
        "ArkivPiloten - Installera senaste Python och starta.bat")
End If

If Not fso.FileExists(batchPath) Then
    MsgBox "Startfilen saknas:" & vbCrLf & batchPath, vbCritical, "ArkivPiloten"
    WScript.Quit 1
End If

command = """" & batchPath & """ --hidden"
exitCode = shell.Run(command, 0, True)
If exitCode = 0 Then
    ' Give the user console-free desktop and Start-menu entry points for
    ' future launches. Never replace a shortcut that belongs to another app.
    On Error Resume Next
    desktopPath = shell.SpecialFolders("Desktop")
    If desktopPath <> "" Then
        CreateArkivPilotenShortcut fso.BuildPath(desktopPath, "ArkivPiloten.lnk")
    End If
    programsPath = shell.SpecialFolders("Programs")
    If programsPath <> "" Then
        appMenuPath = fso.BuildPath(programsPath, "ArkivPiloten")
        If Not fso.FolderExists(appMenuPath) Then fso.CreateFolder appMenuPath
        CreateArkivPilotenShortcut fso.BuildPath(appMenuPath, "ArkivPiloten.lnk")
    End If
    On Error GoTo 0
ElseIf exitCode <> 2 Then
    MsgBox "ArkivPiloten kunde inte startas (kod " & exitCode & ")." & vbCrLf & _
        "Se logs\install.log för detaljer.", vbExclamation, "ArkivPiloten"
End If

Sub CreateArkivPilotenShortcut(linkPath)
    Dim shortcut, iconPath
    On Error Resume Next
    Set shortcut = shell.CreateShortcut(linkPath)
    If Err.Number <> 0 Then
        Err.Clear
        Exit Sub
    End If
    If fso.FileExists(linkPath) Then
        ' Refresh only shortcuts previously created for this launcher.
        If LCase(shortcut.TargetPath) <> LCase(WScript.FullName) Then Exit Sub
        If InStr(1, shortcut.Arguments, "ArkivPiloten - Starta tyst.vbs", vbTextCompare) = 0 Then Exit Sub
    End If
    shortcut.TargetPath = WScript.FullName
    shortcut.Arguments = """" & WScript.ScriptFullName & """"
    shortcut.WorkingDirectory = appDir
    shortcut.Description = "Starta ArkivPiloten utan terminalfönster"
    iconPath = fso.BuildPath(appDir, "ArkivPiloten.ico")
    If fso.FileExists(iconPath) Then shortcut.IconLocation = iconPath & ",0"
    shortcut.Save
    Err.Clear
    On Error GoTo 0
End Sub
