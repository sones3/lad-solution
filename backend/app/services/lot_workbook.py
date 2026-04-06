from __future__ import annotations

from datetime import datetime
from pathlib import Path

import xlsxwriter
from xlsxwriter.utility import xl_col_to_name

from app.models.lot_models import LotSeparationPageModel
from app.services.lot_reconciliation import (
    REASON_DUPLICATE,
    STATUS_AMBIGUOUS,
    STATUS_MISSING_PDF,
    STATUS_OK,
    STATUS_REVIEW,
    ReconciliationResult,
)

STATUS_VALIDATED = "Validé"

MAIN_COLUMNS = [
    {
        "key": "status",
        "header": "Statut",
        "format": "locked",
        "width": 14,
        "visible": True,
    },
    {
        "key": "pdf_name",
        "header": "Nom PDF",
        "format": "editable",
        "width": 18,
        "visible": True,
    },
    {
        "key": "link",
        "header": "Ouvrir PDF",
        "format": "locked",
        "width": 13,
        "visible": True,
    },
    {
        "key": "verify_fields",
        "header": "Champs à vérifier",
        "format": "locked_wrap",
        "width": 24,
        "visible": True,
    },
    {
        "key": "validation_operator",
        "header": "Validation opérateur",
        "format": "editable",
        "width": 16,
        "visible": True,
    },
    {
        "key": "review_note",
        "header": "Note opérateur",
        "format": "editable_wrap",
        "width": 24,
        "visible": True,
    },
    {
        "key": "commande",
        "header": "N° Commande",
        "format": "editable",
        "width": 16,
        "visible": True,
    },
    {
        "key": "client_number",
        "header": "N° Client",
        "format": "editable",
        "width": 16,
        "visible": True,
    },
    {
        "key": "distributeur",
        "header": "Distributeur",
        "format": "editable",
        "width": 18,
        "visible": True,
    },
    {
        "key": "client",
        "header": "Client",
        "format": "editable",
        "width": 24,
        "visible": True,
    },
    {
        "key": "cote",
        "header": "Cote",
        "format": "editable",
        "width": 10,
        "visible": True,
    },
    {
        "key": "caisse",
        "header": "Caisse",
        "format": "editable",
        "width": 10,
        "visible": True,
    },
    {
        "key": "details_separator",
        "header": "Détails",
        "format": "separator",
        "width": 8,
        "visible": True,
    },
    {
        "key": "system_status",
        "header": "Statut système",
        "format": "locked",
        "width": 16,
        "visible": True,
    },
    {
        "key": "source_row",
        "header": "Ligne source",
        "format": "locked",
        "width": 12,
        "visible": True,
    },
    {
        "key": "manual",
        "header": "Manuel",
        "format": "locked",
        "width": 10,
        "visible": True,
    },
    {
        "key": "validation_error",
        "header": "Erreur de validation",
        "format": "locked_wrap",
        "width": 30,
        "visible": True,
    },
    {
        "key": "suggested_pdf_name",
        "header": "PDF suggéré",
        "format": "locked",
        "width": 16,
        "visible": True,
    },
    {
        "key": "detected_pdf_name",
        "header": "PDF détecté",
        "format": "locked",
        "width": 16,
        "visible": True,
    },
    {
        "key": "start_page",
        "header": "Page début",
        "format": "locked",
        "width": 11,
        "visible": True,
    },
    {
        "key": "end_page",
        "header": "Page fin",
        "format": "locked",
        "width": 11,
        "visible": True,
    },
    {
        "key": "page_count",
        "header": "Nb pages",
        "format": "locked",
        "width": 10,
        "visible": True,
    },
    {
        "key": "match_type",
        "header": "Type d'association",
        "format": "locked",
        "width": 20,
        "visible": True,
    },
    {
        "key": "global_score",
        "header": "Score global",
        "format": "locked",
        "width": 12,
        "visible": True,
    },
    {
        "key": "commande_exact",
        "header": "Commande exacte",
        "format": "locked",
        "width": 15,
        "visible": True,
    },
    {
        "key": "client_number_exact",
        "header": "N° Client exact",
        "format": "locked",
        "width": 15,
        "visible": True,
    },
    {
        "key": "client_score",
        "header": "Score client",
        "format": "locked",
        "width": 12,
        "visible": True,
    },
    {
        "key": "distributeur_score",
        "header": "Score distributeur",
        "format": "locked",
        "width": 16,
        "visible": True,
    },
    {
        "key": "diagnostic_reason",
        "header": "Motif diagnostic",
        "format": "locked_wrap",
        "width": 28,
        "visible": True,
    },
]

ORPHAN_COLUMNS = [
    "Nom PDF",
    "Ouvrir PDF",
    "Page début",
    "Page fin",
    "Nb pages",
    "Meilleure ligne candidate",
    "N° Commande candidat",
    "N° Client candidat",
    "Distributeur candidat",
    "Client candidat",
    "Cote candidat",
    "Caisse candidat",
    "Motif",
    "Note opérateur",
]

PDF_DETAILS_HEADERS = [
    "nom_pdf_detail",
    "page_debut",
    "page_fin",
    "nb_pages",
    "meilleure_ligne",
    "commande_candidat",
    "client_candidat",
    "distributeur_candidat",
    "nom_client_candidat",
    "cote_candidat",
    "caisse_candidat",
    "motif_pdf",
]

TABLE_NAME = "tblReconciliation"
LINK_FORMULA = '=IF([@[Nom PDF]]="","",HYPERLINK(".\\sep\\" & [@[Nom PDF]],"Ouvrir"))'
SHEET_PASSWORD = "lad-reco"
VBA_PROJECT_PATH = (
    Path(__file__).resolve().parents[2] / "resources" / "reconciliation_vbaProject.bin"
)


def write_reconciliation_workbook(
    *,
    output_path: Path,
    lot_name: str,
    template_name: str,
    paper_threshold: float,
    result: ReconciliationResult,
    page_diagnostics: list[LotSeparationPageModel],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = xlsxwriter.Workbook(output_path, {"in_memory": True})
    try:
        workbook.add_vba_project(str(VBA_PROJECT_PATH))

        formats = _build_formats(workbook)
        reconciliation_sheet = workbook.add_worksheet("Rapprochement")
        orphan_sheet = workbook.add_worksheet("PDF non affectés")
        diagnostics_sheet = workbook.add_worksheet("Diagnostics")
        lists_sheet = workbook.add_worksheet("Listes")
        lists_sheet.hide()

        _write_lists_sheet(
            lists_sheet=lists_sheet,
            diagnostics=result.document_diagnostics,
        )
        workbook.define_name(
            "pdf_names", "=OFFSET(Listes!$A$2,0,0,MAX(COUNTA(Listes!$A:$A)-1,1),1)"
        )
        workbook.define_name("validation_operator_options", "=Listes!$B$2:$B$2")

        _write_reconciliation_sheet(
            worksheet=reconciliation_sheet,
            formats=formats,
            rows=result.rows,
        )
        _write_orphan_pdfs_sheet(
            worksheet=orphan_sheet,
            formats=formats,
            diagnostics=result.document_diagnostics,
        )
        _write_diagnostics_sheet(
            worksheet=diagnostics_sheet,
            formats=formats,
            lot_name=lot_name,
            template_name=template_name,
            paper_threshold=paper_threshold,
            result=result,
            page_diagnostics=page_diagnostics,
        )
    finally:
        workbook.close()


def _build_formats(
    workbook: xlsxwriter.Workbook,
) -> dict[str, xlsxwriter.format.Format]:
    return {
        "title": workbook.add_format(
            {"bold": True, "font_size": 16, "font_color": "#12324a"}
        ),
        "subtitle": workbook.add_format({"font_color": "#4a6d83", "italic": True}),
        "section": workbook.add_format(
            {"bold": True, "bg_color": "#f0e6d8", "border": 1}
        ),
        "header": workbook.add_format(
            {"bold": True, "bg_color": "#f7f4ed", "border": 1}
        ),
        "locked": workbook.add_format({"locked": True, "border": 1, "valign": "top"}),
        "locked_wrap": workbook.add_format(
            {"locked": True, "border": 1, "valign": "top", "text_wrap": True}
        ),
        "editable": workbook.add_format(
            {"locked": False, "border": 1, "valign": "top", "bg_color": "#fff6d8"}
        ),
        "editable_wrap": workbook.add_format(
            {
                "locked": False,
                "border": 1,
                "valign": "top",
                "bg_color": "#fff6d8",
                "text_wrap": True,
            }
        ),
        "separator": workbook.add_format(
            {
                "locked": True,
                "border": 1,
                "bg_color": "#d9d9d9",
            }
        ),
        "separator_header": workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "bg_color": "#d9d9d9",
                "rotation": 90,
                "align": "center",
                "valign": "vcenter",
            }
        ),
        "meta_key": workbook.add_format(
            {"bold": True, "bg_color": "#faf3e6", "border": 1}
        ),
        "meta_value": workbook.add_format({"border": 1}),
        "status_ok": workbook.add_format({"bg_color": "#d6ead6", "border": 1}),
        "status_validated": workbook.add_format({"bg_color": "#93c47d", "border": 1}),
        "status_review": workbook.add_format({"bg_color": "#f4c27a", "border": 1}),
        "status_ambiguous": workbook.add_format({"bg_color": "#d9c8f0", "border": 1}),
        "status_missing": workbook.add_format({"bg_color": "#f4cccc", "border": 1}),
        "status_manual": workbook.add_format({"bg_color": "#d9e1f2", "border": 1}),
        "error_highlight": workbook.add_format({"bg_color": "#f4cccc"}),
    }


def _write_lists_sheet(*, lists_sheet, diagnostics) -> None:
    lists_sheet.write(0, 0, "nom_pdf")
    sorted_diagnostics = sorted(diagnostics, key=lambda diagnostic: diagnostic.pdf_name)
    for index, diagnostic in enumerate(sorted_diagnostics, start=1):
        lists_sheet.write(index, 0, diagnostic.pdf_name)

    lists_sheet.write(0, 1, "validation_operateur")
    lists_sheet.write(1, 1, STATUS_VALIDATED)

    for column_index, header in enumerate(PDF_DETAILS_HEADERS, start=2):
        lists_sheet.write(0, column_index, header)

    for row_index, diagnostic in enumerate(sorted_diagnostics, start=1):
        values = [
            diagnostic.pdf_name,
            diagnostic.start_page,
            diagnostic.end_page,
            diagnostic.page_count,
            diagnostic.best_source_row,
            diagnostic.best_commande,
            diagnostic.best_client_number,
            diagnostic.best_distributeur,
            diagnostic.best_client,
            diagnostic.best_cote,
            diagnostic.best_caisse,
            diagnostic.reason,
        ]
        for column_index, value in enumerate(values, start=2):
            lists_sheet.write(row_index, column_index, value)


def _write_reconciliation_sheet(*, worksheet, formats, rows) -> None:
    worksheet.write(0, 0, "Rapprochement lot / PDF", formats["title"])
    worksheet.write(
        1,
        0,
        "Utilisez les champs surlignés pour corriger ou compléter les affectations.",
        formats["subtitle"],
    )

    worksheet.insert_button(
        0,
        6,
        {
            "macro": "ReconciliationMacros.RegenerateLinks",
            "caption": "Régénérer liens",
            "width": 122,
            "height": 28,
        },
    )
    worksheet.insert_button(
        0,
        8,
        {
            "macro": "ReconciliationMacros.ValidatePdfNames",
            "caption": "Valider PDF",
            "width": 110,
            "height": 28,
        },
    )
    worksheet.insert_button(
        0,
        10,
        {
            "macro": "ReconciliationMacros.AddManualRow",
            "caption": "Ajouter ligne",
            "width": 110,
            "height": 28,
        },
    )

    table_row = 3
    data = [_row_values(row) for row in rows]

    column_options: list[dict[str, object]] = []
    for column in MAIN_COLUMNS:
        option: dict[str, object] = {
            "header": column["header"],
            "format": formats[column["format"]],
        }
        column_options.append(option)

    worksheet.add_table(
        table_row,
        0,
        table_row + max(len(data), 1),
        len(MAIN_COLUMNS) - 1,
        {
            "name": TABLE_NAME,
            "style": "Table Style Light 9",
            "data": data,
            "columns": column_options,
            "autofilter": True,
        },
    )

    if rows:
        status_col = _column_index("status")
        link_col = _column_index("link")
        validation_operator_col = _column_index("validation_operator")
        pdf_col_name = xl_col_to_name(_column_index("pdf_name"))
        system_status_col_name = xl_col_to_name(_column_index("system_status"))
        validation_operator_col_name = xl_col_to_name(validation_operator_col)
        for row_offset in range(len(rows)):
            excel_row = table_row + 1 + row_offset
            worksheet.write_formula(
                excel_row,
                status_col,
                (
                    f'=IF(AND({validation_operator_col_name}{excel_row + 1}="{STATUS_VALIDATED}",'
                    f'{pdf_col_name}{excel_row + 1}<>""),'
                    f'"{STATUS_VALIDATED}",{system_status_col_name}{excel_row + 1})'
                ),
                formats["locked"],
            )
            worksheet.write_formula(
                excel_row,
                link_col,
                f'=IF({pdf_col_name}{excel_row + 1}="","",HYPERLINK(".\\sep\\" & {pdf_col_name}{excel_row + 1},"Ouvrir"))',
                formats["locked"],
            )

    separator_col = _column_index("details_separator")
    worksheet.write(table_row, separator_col, "Détails", formats["separator_header"])
    worksheet.set_row(table_row, 42)

    worksheet.freeze_panes(table_row + 1, 5)
    worksheet.protect(
        SHEET_PASSWORD,
        {"insert_rows": False, "delete_rows": False, "sort": True, "autofilter": True},
    )

    for col_index, column in enumerate(MAIN_COLUMNS):
        worksheet.set_column(col_index, col_index, column["width"])

    pdf_name_col = _column_index("pdf_name")
    status_col = _column_index("status")
    validation_operator_col = _column_index("validation_operator")
    validation_col = _column_index("validation_error")
    visible_end_col = len(MAIN_COLUMNS) - 1
    start_row = table_row + 1
    end_row = 5000
    status_col_name = xl_col_to_name(status_col)
    validation_col_name = xl_col_to_name(validation_col)

    _apply_status_row_format(
        worksheet=worksheet,
        start_row=start_row,
        end_row=end_row,
        start_col=0,
        end_col=visible_end_col,
        status_col_name=status_col_name,
        status_value=STATUS_VALIDATED,
        fmt=formats["status_validated"],
    )
    _apply_status_row_format(
        worksheet=worksheet,
        start_row=start_row,
        end_row=end_row,
        start_col=0,
        end_col=visible_end_col,
        status_col_name=status_col_name,
        status_value=STATUS_OK,
        fmt=formats["status_ok"],
    )
    _apply_status_row_format(
        worksheet=worksheet,
        start_row=start_row,
        end_row=end_row,
        start_col=0,
        end_col=visible_end_col,
        status_col_name=status_col_name,
        status_value=STATUS_REVIEW,
        fmt=formats["status_review"],
    )
    _apply_status_row_format(
        worksheet=worksheet,
        start_row=start_row,
        end_row=end_row,
        start_col=0,
        end_col=visible_end_col,
        status_col_name=status_col_name,
        status_value=STATUS_AMBIGUOUS,
        fmt=formats["status_ambiguous"],
    )
    _apply_status_row_format(
        worksheet=worksheet,
        start_row=start_row,
        end_row=end_row,
        start_col=0,
        end_col=visible_end_col,
        status_col_name=status_col_name,
        status_value=STATUS_MISSING_PDF,
        fmt=formats["status_missing"],
    )
    _apply_status_row_format(
        worksheet=worksheet,
        start_row=start_row,
        end_row=end_row,
        start_col=0,
        end_col=visible_end_col,
        status_col_name=status_col_name,
        status_value="Manuel",
        fmt=formats["status_manual"],
    )
    worksheet.conditional_format(
        start_row,
        pdf_name_col,
        end_row,
        pdf_name_col,
        {
            "type": "formula",
            "criteria": f'=${validation_col_name}{start_row + 1}<>""',
            "format": formats["error_highlight"],
        },
    )
    worksheet.data_validation(
        start_row,
        pdf_name_col,
        end_row,
        pdf_name_col,
        {"validate": "list", "source": "=pdf_names", "ignore_blank": True},
    )
    worksheet.data_validation(
        start_row,
        validation_operator_col,
        end_row,
        validation_operator_col,
        {
            "validate": "list",
            "source": "=validation_operator_options",
            "ignore_blank": True,
        },
    )


def _write_orphan_pdfs_sheet(*, worksheet, formats, diagnostics) -> None:
    worksheet.write(0, 0, "PDF non affectés", formats["title"])
    worksheet.write(
        1,
        0,
        "Liste des PDF sans ligne CSV affectée, avec la meilleure piste disponible.",
        formats["subtitle"],
    )

    headers = []
    for header in ORPHAN_COLUMNS:
        if header == "Note opérateur":
            headers.append({"header": header, "format": formats["editable_wrap"]})
        elif header == "Motif":
            headers.append({"header": header, "format": formats["locked_wrap"]})
        else:
            headers.append({"header": header, "format": formats["locked"]})

    rows = [
        _orphan_row_values(diagnostic)
        for diagnostic in diagnostics
        if diagnostic.status in {"Ambigu", "Non affecté"}
    ]
    table_row = 3
    worksheet.add_table(
        table_row,
        0,
        table_row + max(len(rows), 1),
        len(ORPHAN_COLUMNS) - 1,
        {
            "name": "tblPdfNonAffectes",
            "style": "Table Style Light 9",
            "data": rows,
            "columns": headers,
            "autofilter": True,
        },
    )

    if rows:
        link_col = ORPHAN_COLUMNS.index("Ouvrir PDF")
        pdf_col_name = xl_col_to_name(ORPHAN_COLUMNS.index("Nom PDF"))
        for row_offset in range(len(rows)):
            excel_row = table_row + 1 + row_offset
            worksheet.write_formula(
                excel_row,
                link_col,
                f'=IF({pdf_col_name}{excel_row + 1}="","",HYPERLINK(".\\sep\\" & {pdf_col_name}{excel_row + 1},"Ouvrir"))',
                formats["locked"],
            )

    worksheet.freeze_panes(table_row + 1, 0)
    worksheet.protect(
        SHEET_PASSWORD,
        {"insert_rows": False, "delete_rows": False, "sort": True, "autofilter": True},
    )

    widths = [18, 13, 11, 11, 10, 18, 16, 16, 18, 22, 10, 10, 28, 24]
    for index, width in enumerate(widths):
        worksheet.set_column(index, index, width)


def _write_diagnostics_sheet(
    *,
    worksheet,
    formats,
    lot_name: str,
    template_name: str,
    paper_threshold: float,
    result: ReconciliationResult,
    page_diagnostics: list[LotSeparationPageModel],
) -> None:
    worksheet.write(0, 0, "Diagnostics", formats["title"])
    worksheet.write(
        1,
        0,
        "Synthèse rapide des exceptions et points de contrôle.",
        formats["subtitle"],
    )

    metadata = [
        ("Lot", lot_name),
        ("Modèle", template_name),
        ("Seuil papier", paper_threshold),
        ("Généré le", datetime.now().isoformat(timespec="seconds")),
        ("PDF générés", result.summary.generated_pdf_count),
        ("Lignes CSV", result.summary.csv_row_count),
        ("OK", sum(1 for row in result.rows if row.status == STATUS_OK)),
        ("À vérifier", sum(1 for row in result.rows if row.status == STATUS_REVIEW)),
        ("Ambigus", sum(1 for row in result.rows if row.status == STATUS_AMBIGUOUS)),
        ("Sans PDF", sum(1 for row in result.rows if row.status == STATUS_MISSING_PDF)),
        ("Manuels", sum(1 for row in result.rows if row.status == "Manuel")),
        (
            "PDF non affectés",
            sum(
                1
                for diagnostic in result.document_diagnostics
                if diagnostic.status in {"Ambigu", "Non affecté"}
            ),
        ),
    ]
    for row_index, (label, value) in enumerate(metadata, start=3):
        worksheet.write(row_index, 0, label, formats["meta_key"])
        worksheet.write(row_index, 1, value, formats["meta_value"])

    validation_anchor = 11
    worksheet.write(
        validation_anchor, 0, "Erreurs de validation locales", formats["section"]
    )
    worksheet.write_row(
        validation_anchor + 1,
        0,
        ["Ligne source", "Nom PDF", "Problème"],
        formats["header"],
    )

    orphan_anchor = 36
    worksheet.write(
        orphan_anchor,
        0,
        "PDF présents dans sep/ mais non référencés",
        formats["section"],
    )
    worksheet.write_row(
        orphan_anchor + 2, 0, ["Nom PDF", "Problème"], formats["header"]
    )

    verify_anchor = 60
    worksheet.write(verify_anchor, 0, "Lignes à vérifier", formats["section"])
    verify_headers = ["Ligne source", "Nom PDF", "Champs à vérifier"]
    worksheet.write_row(verify_anchor + 1, 0, verify_headers, formats["header"])
    verify_rows = [
        [row.source_row, row.pdf_name, row.verify_fields]
        for row in result.rows
        if row.status == STATUS_REVIEW
    ]
    for offset, data in enumerate(verify_rows, start=verify_anchor + 2):
        worksheet.write_row(offset, 0, data)

    ambiguous_anchor = verify_anchor + max(len(verify_rows), 1) + 4
    worksheet.write(ambiguous_anchor, 0, "Cas ambigus", formats["section"])
    ambiguous_headers = [
        "Ligne source",
        "N° Commande",
        "N° Client",
        "Client",
        "PDF suggéré",
        "Motif",
    ]
    worksheet.write_row(ambiguous_anchor + 1, 0, ambiguous_headers, formats["header"])
    ambiguous_rows = [
        [
            row.source_row,
            row.commande,
            row.client_number,
            row.client,
            row.suggested_pdf_name,
            row.diagnostic_reason,
        ]
        for row in result.rows
        if row.status == STATUS_AMBIGUOUS
    ]
    for offset, data in enumerate(ambiguous_rows, start=ambiguous_anchor + 2):
        worksheet.write_row(offset, 0, data)

    duplicate_anchor = ambiguous_anchor + max(len(ambiguous_rows), 1) + 4
    worksheet.write(duplicate_anchor, 0, "Doublons possibles", formats["section"])
    duplicate_headers = ["Ligne source", "N° Commande", "N° Client", "Client", "Motif"]
    worksheet.write_row(duplicate_anchor + 1, 0, duplicate_headers, formats["header"])
    duplicate_rows = [
        [
            row.source_row,
            row.commande,
            row.client_number,
            row.client,
            row.diagnostic_reason,
        ]
        for row in result.rows
        if row.diagnostic_reason == REASON_DUPLICATE
    ]
    for offset, data in enumerate(duplicate_rows, start=duplicate_anchor + 2):
        worksheet.write_row(offset, 0, data)

    page_anchor = duplicate_anchor + max(len(duplicate_rows), 1) + 4
    worksheet.write(page_anchor, 0, "Problèmes de séparation", formats["section"])
    page_headers = ["Page", "Nouveau document", "Score papier", "Avertissements"]
    worksheet.write_row(page_anchor + 1, 0, page_headers, formats["header"])
    warning_rows = [
        [
            page.pageNumber,
            "oui" if page.isNewDocument else "non",
            _score_percent(page.score),
            "; ".join(page.warnings) or "",
        ]
        for page in page_diagnostics
        if page.warnings
    ]
    if not warning_rows:
        warning_rows = [["-", "-", None, "Aucun avertissement de séparation détecté"]]
    for offset, data in enumerate(warning_rows, start=page_anchor + 2):
        worksheet.write_row(offset, 0, data)

    worksheet.freeze_panes(2, 0)
    worksheet.set_column("A:A", 18)
    worksheet.set_column("B:B", 18)
    worksheet.set_column("C:F", 24)


def _apply_status_row_format(
    *,
    worksheet,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
    status_col_name: str,
    status_value: str,
    fmt,
) -> None:
    worksheet.conditional_format(
        start_row,
        start_col,
        end_row,
        end_col,
        {
            "type": "formula",
            "criteria": f'=${status_col_name}{start_row + 1}="{status_value}"',
            "format": fmt,
        },
    )


def _column_index(key: str) -> int:
    return next(
        index for index, column in enumerate(MAIN_COLUMNS) if column["key"] == key
    )


def _row_values(row) -> list:
    values = []
    for column in MAIN_COLUMNS:
        key = column["key"]
        if key in {"link", "details_separator"}:
            values.append("")
        elif key == "validation_operator":
            values.append(STATUS_VALIDATED if row.status == STATUS_OK else "")
        elif key == "system_status":
            values.append(row.status)
        else:
            values.append(getattr(row, key))
    return values


def _orphan_row_values(diagnostic) -> list:
    return [
        diagnostic.pdf_name,
        "",
        diagnostic.start_page,
        diagnostic.end_page,
        diagnostic.page_count,
        diagnostic.best_source_row,
        diagnostic.best_commande,
        diagnostic.best_client_number,
        diagnostic.best_distributeur,
        diagnostic.best_client,
        diagnostic.best_cote,
        diagnostic.best_caisse,
        diagnostic.reason,
        "",
    ]


def _score_percent(value: float | None) -> int | None:
    if value is None:
        return None
    return max(0, min(100, round(value * 100)))
