Attribute VB_Name = "ImportGripper"
Option Explicit

' Import this module into a SOLIDWORKS VBA macro.
' AssetRoot is the editable_gripper_preview directory; units and axes come from STEP.
' Return the imported ModelDoc2; the caller controls placement and saving.
Public Function OpenGripper(ByVal swApp As Object, ByVal AssetRoot As String, _
    Optional ByVal Channel As Long = 32, Optional ByVal State As String = "assembled", _
    Optional ByVal PartId As String = "") As Object

    If Channel <> 12 And Channel <> 32 Then Err.Raise 5, , "Channel must be 12 or 32."
    If State <> "assembled" And State <> "exploded" Then Err.Raise 5, , "Invalid state."
    Dim fso As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    If Not fso.FileExists(fso.BuildPath(AssetRoot, "interface\manifest.json")) Then
        Err.Raise 53, , "AssetRoot does not contain interface\manifest.json."
    End If
    Dim fileName As String
    If Len(PartId) > 0 Then
        If State <> "assembled" Then Err.Raise 5, , "Individual STEP uses assembled coordinates."
        Select Case PartId
            Case "Structural_body", "Source_cover", "Silicone_cap", "PCB_illustrative", "Connector_illustrative"
                fileName = PartId & ".step"
            Case Else
                Err.Raise 5, , "No standalone STEP for this ID; use the full assembly STEP."
        End Select
    Else
        fileName = "gripper-" & CStr(Channel) & "-" & State & ".step"
    End If
    Dim stepFile As String
    stepFile = fso.BuildPath(AssetRoot, "cad\" & CStr(Channel) & "\" & fileName)
    If Not fso.FileExists(stepFile) Then Err.Raise 53, , stepFile
    Dim importData As Object
    Set importData = swApp.GetImportFileData(stepFile)
    If importData Is Nothing Then Err.Raise 5, , "STEP import data unavailable."
    importData.MapConfigurationData = True
    Dim errors As Long
    Dim doc As Object
    Set doc = swApp.LoadFile4(stepFile, "r", importData, errors)
    If doc Is Nothing Then Err.Raise 5, , "STEP import failed: " & CStr(errors)
    If errors <> 0 Then Debug.Print "SOLIDWORKS import flags: " & CStr(errors)
    Set OpenGripper = doc
End Function

Public Sub main()
    Dim swApp As Object
    Set swApp = Application.SldWorks
    Dim fso As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    Dim assetRoot As String
    ' Save the .swp macro next to this .bas inside interface/ for automatic lookup.
    assetRoot = fso.GetParentFolderName(fso.GetParentFolderName(swApp.GetCurrentMacroPathName))
    If Not fso.FileExists(fso.BuildPath(assetRoot, "interface\manifest.json")) Then
        assetRoot = InputBox("Path to editable_gripper_preview:", "Gripper assets")
        If Len(assetRoot) = 0 Then Exit Sub
    End If
    Dim doc As Object
    Set doc = OpenGripper(swApp, assetRoot, 32, "assembled")
End Sub
