Attribute VB_Name = "ReconciliationMacros"
Option Explicit

Private Const RECON_SHEET As String = "Rapprochement"
Private Const ORPHAN_SHEET As String = "PDF non affectés"
Private Const DIAGNOSTICS_SHEET As String = "Diagnostics"
Private Const LISTS_SHEET As String = "Listes"
Private Const TABLE_NAME As String = "tblReconciliation"
Private Const ORPHAN_TABLE_NAME As String = "tblPdfNonAffectes"
Private Const PASSWORD As String = "lad-reco"
Private Const STATUS_VALIDATED As String = "Validé"
Private Const xlUp As Integer = -4162
Private Const xlValidateList As Integer = 3
Private Const xlValidAlertStop As Integer = 1

Public Sub RegenerateLinks()
    On Error GoTo HandleError
    Application.ScreenUpdating = False

    RefreshPdfListInternal
    WriteStatusFormulas
    WriteLinkFormulas
    ApplyPdfValidation
    ApplyValidationOperatorValidation
    RefreshOperationalSheets

    Application.ScreenUpdating = True
    Exit Sub

HandleError:
    Application.ScreenUpdating = True
    MsgBox "Échec de la régénération des liens : " & Err.Description, vbExclamation
End Sub

Public Sub ValidatePdfNames()
    On Error GoTo HandleError
    Application.ScreenUpdating = False

    RefreshPdfListInternal
    WriteStatusFormulas
    WriteLinkFormulas
    ApplyPdfValidation
    ApplyValidationOperatorValidation
    ValidatePdfNamesInternal True

    Application.ScreenUpdating = True
    Exit Sub

HandleError:
    Application.ScreenUpdating = True
    MsgBox "Échec de la validation des PDF : " & Err.Description, vbExclamation
End Sub

Public Sub AddManualRow()
    On Error GoTo HandleError
    Application.ScreenUpdating = False

    Dim worksheet As Worksheet
    Set worksheet = ThisWorkbook.Worksheets(RECON_SHEET)
    worksheet.Unprotect PASSWORD

    Dim table As ListObject
    Set table = worksheet.ListObjects(TABLE_NAME)

    Dim newRow As ListRow
    Set newRow = table.ListRows.Add

    SetCellValue newRow, "Statut", "Manuel"
    SetCellValue newRow, "Nom PDF", ""
    SetCellValue newRow, "Champs à vérifier", ""
    SetCellValue newRow, "Validation opérateur", ""
    SetCellValue newRow, "Note opérateur", ""
    SetCellValue newRow, "N° Commande", ""
    SetCellValue newRow, "N° Client", ""
    SetCellValue newRow, "Distributeur", ""
    SetCellValue newRow, "Client", ""
    SetCellValue newRow, "Cote", ""
    SetCellValue newRow, "Caisse", ""
    SetCellValue newRow, "Statut système", "Manuel"
    SetCellValue newRow, "Ligne source", ""
    SetCellValue newRow, "Manuel", "oui"
    SetCellValue newRow, "Erreur de validation", ""
    SetCellValue newRow, "PDF suggéré", ""
    SetCellValue newRow, "PDF détecté", ""
    SetCellValue newRow, "Page début", ""
    SetCellValue newRow, "Page fin", ""
    SetCellValue newRow, "Nb pages", ""
    SetCellValue newRow, "Type d'association", ""
    SetCellValue newRow, "Score global", ""
    SetCellValue newRow, "Commande exacte", ""
    SetCellValue newRow, "N° Client exact", ""
    SetCellValue newRow, "Score client", ""
    SetCellValue newRow, "Score distributeur", ""
    SetCellValue newRow, "Motif diagnostic", "Ligne ajoutée manuellement dans Excel"

    WriteStatusFormulas
    WriteLinkFormulas
    ApplyPdfValidation
    ApplyValidationOperatorValidation
    RefreshOperationalSheets
    worksheet.Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True

    Application.ScreenUpdating = True
    Exit Sub

HandleError:
    On Error Resume Next
    ThisWorkbook.Worksheets(RECON_SHEET).Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True
    Application.ScreenUpdating = True
    MsgBox "Échec de l'ajout d'une ligne manuelle : " & Err.Description, vbExclamation
End Sub

Private Sub RefreshOperationalSheets()
    Dim available As Object
    Dim used As Object
    Dim orphanRows As Collection

    Set available = BuildAvailablePdfMap()
    Set used = BuildUsedPdfMap()
    Set orphanRows = RefreshUnassignedPdfsSheet(used, available)
    UpdateOrphanDiagnostics orphanRows
End Sub

Private Sub RefreshPdfListInternal()
    Dim worksheet As Worksheet
    Set worksheet = ThisWorkbook.Worksheets(LISTS_SHEET)
    worksheet.Range("A:B").ClearContents
    worksheet.Cells(1, 1).Value = "nom_pdf"

    Dim folderPath As String
    folderPath = ThisWorkbook.Path & Application.PathSeparator & "sep" & Application.PathSeparator

    Dim currentName As String
    Dim rowIndex As Integer
    rowIndex = 2
    currentName = Dir(folderPath & "*.pdf")
    Do While currentName <> ""
        worksheet.Cells(rowIndex, 1).Value = currentName
        rowIndex = rowIndex + 1
        currentName = Dir()
    Loop

    worksheet.Cells(1, 2).Value = "validation_operateur"
    worksheet.Cells(2, 2).Value = STATUS_VALIDATED
End Sub

Private Sub WriteStatusFormulas()
    Dim worksheet As Worksheet
    Set worksheet = ThisWorkbook.Worksheets(RECON_SHEET)
    worksheet.Unprotect PASSWORD

    Dim table As ListObject
    Set table = worksheet.ListObjects(TABLE_NAME)
    If table.ListRows.Count = 0 Then
        worksheet.Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True
        Exit Sub
    End If

    Dim statusColumnIndex As Long
    Dim pdfColumnIndex As Long
    Dim validationColumnIndex As Long
    Dim systemStatusColumnIndex As Long
    statusColumnIndex = table.ListColumns("Statut").Index
    pdfColumnIndex = table.ListColumns("Nom PDF").Index
    validationColumnIndex = table.ListColumns("Validation opérateur").Index
    systemStatusColumnIndex = table.ListColumns("Statut système").Index

    Dim rowItem As ListRow
    Dim quoteMark As String
    quoteMark = Chr(34)

    For Each rowItem In table.ListRows
        Dim statusCell As Range
        Dim pdfCell As Range
        Dim validationCell As Range
        Dim systemStatusCell As Range
        Set statusCell = rowItem.Range.Cells(1, statusColumnIndex)
        Set pdfCell = rowItem.Range.Cells(1, pdfColumnIndex)
        Set validationCell = rowItem.Range.Cells(1, validationColumnIndex)
        Set systemStatusCell = rowItem.Range.Cells(1, systemStatusColumnIndex)
        statusCell.Formula = _
            "=IF(AND(" & validationCell.Address(False, False) & "=" & quoteMark & STATUS_VALIDATED & quoteMark & "," & _
            pdfCell.Address(False, False) & "<>" & quoteMark & quoteMark & ")," & _
            quoteMark & STATUS_VALIDATED & quoteMark & "," & _
            systemStatusCell.Address(False, False) & ")"
    Next rowItem

    worksheet.Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True
End Sub

Private Sub WriteLinkFormulas()
    Dim worksheet As Worksheet
    Set worksheet = ThisWorkbook.Worksheets(RECON_SHEET)
    worksheet.Unprotect PASSWORD

    Dim table As ListObject
    Set table = worksheet.ListObjects(TABLE_NAME)
    If table.ListRows.Count = 0 Then
        worksheet.Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True
        Exit Sub
    End If

    Dim pdfColumnIndex As Long
    Dim linkColumnIndex As Long
    pdfColumnIndex = table.ListColumns("Nom PDF").Index
    linkColumnIndex = table.ListColumns("Ouvrir PDF").Index

    Dim rowItem As ListRow
    For Each rowItem In table.ListRows
        Dim pdfCell As Range
        Dim linkCell As Range
        Set pdfCell = rowItem.Range.Cells(1, pdfColumnIndex)
        Set linkCell = rowItem.Range.Cells(1, linkColumnIndex)
        linkCell.Formula = "=IF(" & pdfCell.Address(False, False) & "="""","""",HYPERLINK("".\sep\"" & " & pdfCell.Address(False, False) & ",""Ouvrir""))"
    Next rowItem

    worksheet.Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True
End Sub

Private Sub ApplyPdfValidation()
    Dim worksheet As Worksheet
    Set worksheet = ThisWorkbook.Worksheets(RECON_SHEET)
    worksheet.Unprotect PASSWORD

    Dim table As ListObject
    Set table = worksheet.ListObjects(TABLE_NAME)
    If table.ListRows.Count = 0 Then
        worksheet.Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True
        Exit Sub
    End If

    Dim pdfRange As Range
    Set pdfRange = table.ListColumns("Nom PDF").DataBodyRange
    pdfRange.Validation.Delete
    pdfRange.Validation.Add Type:=xlValidateList, AlertStyle:=xlValidAlertStop, Formula1:="=pdf_names"
    pdfRange.Validation.IgnoreBlank = True
    pdfRange.Validation.InCellDropdown = True

    worksheet.Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True
End Sub

Private Sub ApplyValidationOperatorValidation()
    Dim worksheet As Worksheet
    Set worksheet = ThisWorkbook.Worksheets(RECON_SHEET)
    worksheet.Unprotect PASSWORD

    Dim table As ListObject
    Set table = worksheet.ListObjects(TABLE_NAME)
    If table.ListRows.Count = 0 Then
        worksheet.Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True
        Exit Sub
    End If

    Dim operatorRange As Range
    Set operatorRange = table.ListColumns("Validation opérateur").DataBodyRange
    operatorRange.Validation.Delete
    operatorRange.Validation.Add Type:=xlValidateList, AlertStyle:=xlValidAlertStop, Formula1:="=validation_operator_options"
    operatorRange.Validation.IgnoreBlank = True
    operatorRange.Validation.InCellDropdown = True

    worksheet.Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True
End Sub

Private Sub ValidatePdfNamesInternal(ByVal showMessage As Boolean)
    Dim worksheet As Worksheet
    Set worksheet = ThisWorkbook.Worksheets(RECON_SHEET)
    worksheet.Unprotect PASSWORD

    Dim table As ListObject
    Set table = worksheet.ListObjects(TABLE_NAME)

    Dim available As Object
    Set available = BuildAvailablePdfMap()
    Dim used As Object
    Set used = BuildUsedPdfMap()
    Dim issues As Collection
    Set issues = New Collection

    If table.ListRows.Count > 0 Then
        Dim index As Long
        For index = 1 To table.ListRows.Count
            Dim rowItem As ListRow
            Set rowItem = table.ListRows(index)

            Dim errorText As String
            errorText = BuildRowError(rowItem, available, used)

            SetCellValue rowItem, "Erreur de validation", errorText

            Dim pdfCell As Range
            Set pdfCell = GetCell(rowItem, "Nom PDF")
            If errorText <> "" Then
                pdfCell.Interior.Color = RGB(244, 204, 204)
                issues.Add Array(GetCellValue(rowItem, "Ligne source"), GetCellValue(rowItem, "Nom PDF"), errorText)
            Else
                pdfCell.Interior.Pattern = xlNone
            End If
        Next index
    End If

    Dim orphanRows As Collection
    Set orphanRows = RefreshUnassignedPdfsSheet(used, available)
    UpdateDiagnostics issues, orphanRows
    worksheet.Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True

    If showMessage Then
        MsgBox "Validation terminée. " & issues.Count & " problème(s) détecté(s).", vbInformation
    End If
End Sub

Private Function BuildAvailablePdfMap() As Object
    Dim available As Object
    Set available = CreateObject("Scripting.Dictionary")

    Dim listSheet As Worksheet
    Set listSheet = ThisWorkbook.Worksheets(LISTS_SHEET)
    Dim lastPdfRow As Long
    lastPdfRow = listSheet.Cells(listSheet.Rows.Count, 1).End(xlUp).Row

    Dim index As Long
    For index = 2 To lastPdfRow
        Dim listedName As String
        listedName = Trim(CStr(listSheet.Cells(index, 1).Value))
        If listedName <> "" Then
            available(LCase(listedName)) = listedName
        End If
    Next index

    Set BuildAvailablePdfMap = available
End Function

Private Function BuildUsedPdfMap() As Object
    Dim used As Object
    Set used = CreateObject("Scripting.Dictionary")

    Dim worksheet As Worksheet
    Set worksheet = ThisWorkbook.Worksheets(RECON_SHEET)
    Dim table As ListObject
    Set table = worksheet.ListObjects(TABLE_NAME)
    If table.ListRows.Count = 0 Then
        Set BuildUsedPdfMap = used
        Exit Function
    End If

    Dim index As Long
    For index = 1 To table.ListRows.Count
        Dim pdfName As String
        pdfName = Trim(CStr(GetCellValue(table.ListRows(index), "Nom PDF")))
        If pdfName <> "" Then
            Dim key As String
            key = LCase(pdfName)
            If used.Exists(key) Then
                used(key) = used(key) + 1
            Else
                used(key) = 1
            End If
        End If
    Next index

    Set BuildUsedPdfMap = used
End Function

Private Function BuildRowError(ByVal rowItem As ListRow, ByVal available As Object, ByVal used As Object) As String
    Dim messages As Collection
    Set messages = New Collection

    Dim pdfName As String
    pdfName = Trim(CStr(GetCellValue(rowItem, "Nom PDF")))
    If pdfName = "" Then
        If Trim(CStr(GetCellValue(rowItem, "Validation opérateur"))) = STATUS_VALIDATED Then
            messages.Add "Impossible de valider sans Nom PDF"
        End If
    Else
        If LCase$(Right$(pdfName, 4)) <> ".pdf" Then
            messages.Add "Le nom du PDF doit se terminer par .pdf"
        End If
        If Not available.Exists(LCase(pdfName)) Then
            messages.Add "Le fichier PDF est introuvable dans sep/"
        End If
        If used.Exists(LCase(pdfName)) And used(LCase(pdfName)) > 1 Then
            messages.Add "Le même PDF est utilisé plusieurs fois"
        End If
    End If

    If LCase$(Trim(CStr(GetCellValue(rowItem, "Manuel")))) = "oui" Then
        If Trim(CStr(GetCellValue(rowItem, "N° Commande"))) = "" Then messages.Add "N° Commande obligatoire pour une ligne manuelle"
        If Trim(CStr(GetCellValue(rowItem, "N° Client"))) = "" Then messages.Add "N° Client obligatoire pour une ligne manuelle"
        If Trim(CStr(GetCellValue(rowItem, "Distributeur"))) = "" Then messages.Add "Distributeur obligatoire pour une ligne manuelle"
        If Trim(CStr(GetCellValue(rowItem, "Client"))) = "" Then messages.Add "Client obligatoire pour une ligne manuelle"
        If Trim(CStr(GetCellValue(rowItem, "Cote"))) = "" Then messages.Add "Cote obligatoire pour une ligne manuelle"
        If Trim(CStr(GetCellValue(rowItem, "Caisse"))) = "" Then messages.Add "Caisse obligatoire pour une ligne manuelle"
    End If

    BuildRowError = JoinCollection(messages, "; ")
End Function

Private Function RefreshUnassignedPdfsSheet(ByVal used As Object, ByVal available As Object) As Collection
    Dim detailsMap As Object
    Set detailsMap = BuildPdfDetailsMap()

    Dim notesByPdf As Object
    Set notesByPdf = ReadOrphanNotes()

    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets(ORPHAN_SHEET)
    sheet.Unprotect PASSWORD

    Dim table As ListObject
    Set table = sheet.ListObjects(ORPHAN_TABLE_NAME)
    ClearTableRows table

    Dim orphanRows As Collection
    Set orphanRows = New Collection

    Dim key As Variant
    For Each key In available.Keys
        If Not used.Exists(key) Then
            Dim values As Variant
            values = GetPdfDetails(detailsMap, available(key))

            Dim newRow As ListRow
            Set newRow = table.ListRows.Add
            newRow.Range.Cells(1, 1).Value = values(0)
            newRow.Range.Cells(1, 2).Formula = "=IF(" & newRow.Range.Cells(1, 1).Address(False, False) & "="""","""",HYPERLINK("".\sep\"" & " & newRow.Range.Cells(1, 1).Address(False, False) & ",""Ouvrir""))"
            newRow.Range.Cells(1, 3).Value = values(1)
            newRow.Range.Cells(1, 4).Value = values(2)
            newRow.Range.Cells(1, 5).Value = values(3)
            newRow.Range.Cells(1, 6).Value = values(4)
            newRow.Range.Cells(1, 7).Value = values(5)
            newRow.Range.Cells(1, 8).Value = values(6)
            newRow.Range.Cells(1, 9).Value = values(7)
            newRow.Range.Cells(1, 10).Value = values(8)
            newRow.Range.Cells(1, 11).Value = values(9)
            newRow.Range.Cells(1, 12).Value = values(10)
            newRow.Range.Cells(1, 13).Value = values(11)
            If notesByPdf.Exists(key) Then
                newRow.Range.Cells(1, 14).Value = notesByPdf(key)
            Else
                newRow.Range.Cells(1, 14).Value = ""
            End If

            orphanRows.Add Array(values(0), values(11))
        End If
    Next key

    sheet.Protect PASSWORD, AllowFiltering:=True, AllowSorting:=True
    Set RefreshUnassignedPdfsSheet = orphanRows
End Function

Private Function BuildPdfDetailsMap() As Object
    Dim detailsMap As Object
    Set detailsMap = CreateObject("Scripting.Dictionary")

    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets(LISTS_SHEET)
    Dim lastRow As Long
    lastRow = sheet.Cells(sheet.Rows.Count, 3).End(xlUp).Row

    Dim index As Long
    For index = 2 To lastRow
        Dim pdfName As String
        pdfName = Trim(CStr(sheet.Cells(index, 3).Value))
        If pdfName <> "" Then
            detailsMap(LCase(pdfName)) = Array( _
                pdfName, _
                sheet.Cells(index, 4).Value, _
                sheet.Cells(index, 5).Value, _
                sheet.Cells(index, 6).Value, _
                sheet.Cells(index, 7).Value, _
                sheet.Cells(index, 8).Value, _
                sheet.Cells(index, 9).Value, _
                sheet.Cells(index, 10).Value, _
                sheet.Cells(index, 11).Value, _
                sheet.Cells(index, 12).Value, _
                sheet.Cells(index, 13).Value, _
                sheet.Cells(index, 14).Value _
            )
        End If
    Next index

    Set BuildPdfDetailsMap = detailsMap
End Function

Private Function GetPdfDetails(ByVal detailsMap As Object, ByVal pdfName As String) As Variant
    Dim key As String
    key = LCase(pdfName)
    If detailsMap.Exists(key) Then
        GetPdfDetails = detailsMap(key)
        Exit Function
    End If

    GetPdfDetails = Array(pdfName, "", "", "", "", "", "", "", "", "", "", "PDF présent dans sep/ mais non référencé")
End Function

Private Function ReadOrphanNotes() As Object
    Dim notesByPdf As Object
    Set notesByPdf = CreateObject("Scripting.Dictionary")

    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets(ORPHAN_SHEET)
    Dim table As ListObject
    Set table = sheet.ListObjects(ORPHAN_TABLE_NAME)
    If table.ListRows.Count = 0 Then
        Set ReadOrphanNotes = notesByPdf
        Exit Function
    End If

    Dim index As Long
    For index = 1 To table.ListRows.Count
        Dim pdfName As String
        pdfName = Trim(CStr(table.ListRows(index).Range.Cells(1, 1).Value))
        If pdfName <> "" Then
            notesByPdf(LCase(pdfName)) = table.ListRows(index).Range.Cells(1, 14).Value
        End If
    Next index

    Set ReadOrphanNotes = notesByPdf
End Function

Private Sub ClearTableRows(ByVal table As ListObject)
    Do While table.ListRows.Count > 0
        table.ListRows(1).Delete
    Loop
End Sub

Private Sub UpdateDiagnostics(ByVal issues As Collection, ByVal orphanRows As Collection)
    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets(DIAGNOSTICS_SHEET)

    sheet.Range("A14:C35").ClearContents
    sheet.Range("A40:B58").ClearContents

    Dim rowIndex As Long
    rowIndex = 14

    Dim item As Variant
    For Each item In issues
        sheet.Cells(rowIndex, 1).Value = item(0)
        sheet.Cells(rowIndex, 2).Value = item(1)
        sheet.Cells(rowIndex, 3).Value = item(2)
        rowIndex = rowIndex + 1
        If rowIndex > 35 Then Exit For
    Next item

    UpdateOrphanDiagnostics orphanRows
End Sub

Private Sub UpdateOrphanDiagnostics(ByVal orphanRows As Collection)
    Dim sheet As Worksheet
    Set sheet = ThisWorkbook.Worksheets(DIAGNOSTICS_SHEET)
    sheet.Range("A40:B58").ClearContents

    Dim rowIndex As Long
    rowIndex = 40

    Dim item As Variant
    For Each item In orphanRows
        sheet.Cells(rowIndex, 1).Value = item(0)
        sheet.Cells(rowIndex, 2).Value = item(1)
        rowIndex = rowIndex + 1
        If rowIndex > 58 Then Exit For
    Next item
End Sub

Private Function GetCell(ByVal rowItem As ListRow, ByVal headerName As String) As Range
    Set GetCell = rowItem.Range.Cells(1, rowItem.Parent.ListColumns(headerName).Index)
End Function

Private Function GetCellValue(ByVal rowItem As ListRow, ByVal headerName As String) As Variant
    GetCellValue = GetCell(rowItem, headerName).Value
End Function

Private Sub SetCellValue(ByVal rowItem As ListRow, ByVal headerName As String, ByVal value As Variant)
    GetCell(rowItem, headerName).Value = value
End Sub

Private Function JoinCollection(ByVal values As Collection, ByVal separator As String) As String
    Dim parts() As String
    If values.Count = 0 Then
        JoinCollection = ""
        Exit Function
    End If

    ReDim parts(1 To values.Count)
    Dim index As Long
    For index = 1 To values.Count
        parts(index) = CStr(values(index))
    Next index
    JoinCollection = Join(parts, separator)
End Function
