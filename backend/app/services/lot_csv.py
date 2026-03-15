from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO


REQUIRED_COLUMNS = ("N° Commande", "N° Client", "Distributeur", "Client", "Statut")


@dataclass(frozen=True)
class LotCsvRow:
    row_number: int
    commande: str
    client_number: str
    distributeur: str
    client: str
    statut: str


def parse_lot_csv(raw: bytes) -> list[LotCsvRow]:
    text = _decode_csv_bytes(raw)
    reader = csv.DictReader(StringIO(text), delimiter=";")
    if reader.fieldnames is None:
        raise ValueError("CSV is empty")

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
    if missing_columns:
        raise ValueError(f"CSV is missing required columns: {', '.join(missing_columns)}")

    rows: list[LotCsvRow] = []
    for row_number, row in enumerate(reader, start=2):
        rows.append(
            LotCsvRow(
                row_number=row_number,
                commande=(row.get("N° Commande") or "").strip(),
                client_number=(row.get("N° Client") or "").strip(),
                distributeur=(row.get("Distributeur") or "").strip(),
                client=(row.get("Client") or "").strip(),
                statut=(row.get("Statut") or "").strip(),
            )
        )

    if not rows:
        raise ValueError("CSV has no data rows")
    return rows


def _decode_csv_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode CSV file")
