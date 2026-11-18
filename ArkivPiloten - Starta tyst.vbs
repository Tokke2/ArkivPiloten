Option Explicit

' Console-free entry point for the Windows bootstrap. The batch file performs
' setup and then starts pdfsorter.pyw; this wrapper keeps its console hidden.
Dim shell, fso, batchPath, command, exitCode
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

If WScript.Arguments.Count > 0 Then
    batchPath = WScript.Arguments(0)
Else
    batchPath = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), _
        "ArkivPiloten - Installera senaste Python och starta.bat")
End If

If Not fso.FileExists(batchPath) Then
    MsgBox "Startfilen saknas:" & vbCrLf & batchPath, vbCritical, "ArkivPiloten"
    WScript.Quit 1
End If

command = """" & batchPath & """ --hidden"
exitCode = shell.Run(command, 0, True)
If exitCode <> 0 And exitCode <> 2 Then
    MsgBox "ArkivPiloten kunde inte startas (kod " & exitCode & ")." & vbCrLf & _
        "Se logs\install.log för detaljer.", vbExclamation, "ArkivPiloten"
End If
