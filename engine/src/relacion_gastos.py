"""Structured, conservative extraction of invoice data and its provenance."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha1
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from docx import Document as DocxDocument
import pandas as pd
import pdfplumber

from .plan import CanonicalPlan, parse_amount


_TIPOS_GASTO = {"factura", "factura_gasto_viaje", "nomina"}
_DATE_PATTERN = re.compile(
    r"\b(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{1,2}\s+(?:de\s+)?[A-Za-záéíóúñ]+\s+(?:de\s+)?\d{4}|"
    r"[A-Za-z]+\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
_MONEY_PATTERN = re.compile(
    r"(?<![\w.,])[-+]?\s*(?:\d{1,3}(?:[.\s,]\d{3})+|\d+)[,.]\d{2}(?!\d)"
)
_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12, "january": 1, "february": 2, "march": 3,
    "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}


@dataclass(frozen=True)
class InvoicePage:
    """Text and tables extracted from one document page.

    This deliberately small boundary also makes the extraction logic testable
    without creating PDFs or adding an OCR/PDF-generation dependency.
    """

    number: int
    text: str = ""
    tables: tuple[tuple[tuple[str, ...], ...], ...] = ()


@dataclass(frozen=True)
class FieldProvenance:
    field: str
    value: str
    page: int | None
    source_type: str
    source: str
    snippet: str
    confidence: float
    review_status: str
    ocr_needed: bool

    def as_dict(self, document_id: str, document_path: str, filename: str) -> dict[str, Any]:
        return {
            "id": document_id,
            "nombre_archivo": filename,
            "documento_ruta": document_path,
            "campo": self.field,
            "valor": self.value,
            "pagina": self.page or "",
            "tipo_fuente": self.source_type,
            "fuente": self.source,
            "fragmento": self.snippet,
            "confianza": f"{self.confidence:.2f}",
            "estado_revision": self.review_status,
            "requiere_ocr": "sí" if self.ocr_needed else "no",
        }


@dataclass
class InvoiceExtraction:
    """Values supported by a single invoice plus auditable source records."""

    values: dict[str, str] = field(default_factory=dict)
    provenance: list[FieldProvenance] = field(default_factory=list)
    ocr_needed: bool = False

    def value(self, field_name: str) -> str:
        return self.values.get(field_name, "")


@dataclass(frozen=True)
class _Fragment:
    page: int
    source_type: str
    source: str
    text: str


@dataclass(frozen=True)
class _Candidate:
    value: str
    fragment: _Fragment
    snippet: str
    confidence: float


def generar_relacion_gastos(
    inventario: Iterable[dict[str, Any]],
    plan: CanonicalPlan,
    salida: str,
    salida_campos: str | None = None,
    salida_revision: str | None = None,
    opciones_extraccion: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Create the fixed expense CSV and independent field-level audit CSVs.

    Payment and funding allocations remain blank: an invoice alone does not
    prove either fact.  The main CSV contract is intentionally unchanged.
    """

    threshold = float((opciones_extraccion or {}).get("confianza_revision_automatica", 0.90))
    acciones = {accion.id: accion for accion in plan.actions}
    filas: list[dict[str, str]] = []
    campos: list[dict[str, Any]] = []
    revisiones: list[dict[str, str]] = []

    for documento in inventario:
        ruta_relativa = str(documento.get("ruta_relativa", "")).replace("\\", "/")

        # Todo documento situado físicamente en CONTABILIDAD/GASTOS
        # se considera candidato a gasto, aunque el clasificador haya
        # asignado incorrectamente su tipo documental.
        if "/CONTABILIDAD/GASTOS/" not in ruta_relativa:
            continue

        es_gasto = documento.get("es_gasto")

        if isinstance(es_gasto, str):
            es_gasto = es_gasto.strip().lower() in {
                "true", "1", "yes", "si", "sí"
            }

        if not es_gasto:
            continue

        gasto_id = _id_gasto(str(documento["ruta_relativa"]))
        extraction = extraer_factura_documento(documento)
        extraction = _apply_review_threshold(extraction, threshold)
        accion = acciones.get(str(documento.get("accion_aprobada_id", "")))
        tipo = str(documento.get("tipo_documental"))
        partida, partida_source = _partida(documento, accion)
        concept = extraction.value("concepto")

        fila = {
            "id": gasto_id,
            "nombre_archivo": str(documento.get("nombre", "")),
            "emisor": extraction.value("emisor"),
            "partida": partida,
            "concepto_de_gasto": concept,
            "fecha_emision": extraction.value("fecha_emision"),
            "fecha_pago": "",
            "cargo_subvencion": "",
            "cargo_otros": "",
            "importe_sin_iva": extraction.value("base_imponible"),
            "nomina": "sí" if tipo == "nomina" else "no",
            "factura": "sí" if tipo != "nomina" else "no",
        }
        filas.append(fila)

        ruta = str(documento.get("ruta_relativa", documento.get("ruta_absoluta", "")))
        filename = fila["nombre_archivo"]
        campos.extend(
            item.as_dict(gasto_id, ruta, filename) for item in extraction.provenance
        )
        campos.extend(
            item.as_dict(gasto_id, ruta, filename)
            for item in _provenance_main_fields(fila, partida_source, extraction)
        )
        revisiones.append(_review_row(gasto_id, filename, ruta, extraction))

    tabla = pd.DataFrame(filas, columns=_columnas())
    if not tabla.empty:
        tabla.sort_values(["partida", "nombre_archivo"], inplace=True, na_position="last")
    ruta_salida = Path(salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(ruta_salida, index=False, encoding="utf-8", lineterminator="\n")

    ruta_campos = Path(salida_campos) if salida_campos else ruta_salida.with_name(
        "extraccion_facturas_campos.csv"
    )
    ruta_revision = Path(salida_revision) if salida_revision else ruta_salida.with_name(
        "revision_extraccion_facturas.csv"
    )
    _guardar_campos(ruta_campos, campos)
    _guardar_revision(ruta_revision, revisiones)
    _guardar_trazabilidad(tabla, ruta_salida)
    return tabla


def extraer_factura_documento(documento: Mapping[str, Any]) -> InvoiceExtraction:
    """Read a source document page-by-page; never substitute filename guesses."""

    ruta = Path(str(documento.get("ruta_absoluta", "")))
    try:
        paginas = leer_paginas_factura(ruta)
    except Exception:
        # A malformed or unsupported source must be reviewable, not fatal to
        # the complete justification pipeline.
        paginas = ()
    if not paginas:
        preview = str(documento.get("texto_preview", "") or "")
        paginas = (InvoicePage(1, preview),) if preview else ()
    return extraer_factura_desde_paginas(paginas)


def leer_paginas_factura(ruta: Path) -> tuple[InvoicePage, ...]:
    """Extract native PDF text and tables, retaining their page provenance."""

    if ruta.suffix.lower() == ".pdf":
        pages: list[InvoicePage] = []
        with pdfplumber.open(ruta) as pdf:
            for number, page in enumerate(pdf.pages, start=1):
                tables = tuple(
                    tuple(tuple(_clean(cell) for cell in row) for row in table)
                    for table in (page.extract_tables() or [])
                )
                pages.append(InvoicePage(number, page.extract_text() or "", tables))
        return tuple(pages)
    if ruta.suffix.lower() == ".docx":
        document = DocxDocument(ruta)
        tables = tuple(
            tuple(tuple(_clean(cell.text) for cell in row.cells) for row in table.rows)
            for table in document.tables
        )
        text = "\n".join(_clean(paragraph.text) for paragraph in document.paragraphs if paragraph.text)
        return (InvoicePage(1, text, tables),)
    return ()


def extraer_factura_desde_paginas(paginas: Sequence[InvoicePage]) -> InvoiceExtraction:
    """Extract only values explicitly supported by supplied page text/tables."""

    fragments = tuple(_fragments(paginas))
    ocr_needed = not any(fragment.text.strip() for fragment in fragments)
    extraction = InvoiceExtraction(ocr_needed=ocr_needed)
    if ocr_needed:
        return _complete_missing_fields(extraction, ocr_needed)

    specs = {
        "emisor": (
            r"emisor|proveedor|expedidor|datos empresa|datos (?:del |de la )?proveedor|"
            r"issuer|supplier|seller|billed from",
            "text",
        ),
        "receptor": (
            r"cliente|destinatario|receptor|datos (?:del |de la )?cliente|"
            r"bill to|customer|billed to",
            "text",
        ),
        "fecha_emision": (
            r"fecha (?:de )?(?:emisi[oó]n|factura|expedici[oó]n)|invoice date|issue date",
            "date",
        ),
        "fecha_vencimiento": (
            r"fecha (?:de )?(?:vencimiento|pago)|vencimiento|due date|payment due",
            "date",
        ),
        "base_imponible": (
            r"base imponible|subtotal|importe neto|total sin iva|net amount|taxable amount|"
            r"b\.?i(?=[.\s|]|$)",
            "money",
        ),
        "iva": (r"\biva\b|\bvat\b|cuota tributaria|impuesto", "money"),
        "retencion": (r"retenci[oó]n|\birpf\b|withholding", "money"),
        "total": (
            r"total(?!\s*\((?:base imponible|sin imp\.?))(?:\s+(?:factura|a pagar|importe))?|"
            r"importe total|total due|grand total|amount due",
            "money",
        ),
        "numero_factura": (
            r"(?:n[úu]m(?:ero)?\.?|n[ºo]|no\.?|número de)?\s*factura|"
            r"invoice\s*(?:number|no\.?|#)?",
            "invoice_number",
        ),
    }
    selected: dict[str, _Candidate] = {}
    for name, (labels, kind) in specs.items():
        candidates = _labelled_candidates(fragments, labels, kind)
        if kind != "text":
            candidates.extend(_table_label_candidates(paginas, labels, kind))
        candidates = _dedupe_candidates(candidates)
        if candidates:
            selected[name] = _select_candidate(candidates)

    for name, candidate in _financial_summary_candidates(fragments).items():
        if name not in selected:
            selected[name] = candidate
    if "fecha_emision" not in selected:
        invoice_date = _date_from_invoice_context(fragments)
        if invoice_date:
            selected["fecha_emision"] = invoice_date
    issuer_fallback = _issuer_from_tax_identity(fragments, selected.get("receptor"))
    if "emisor" not in selected and issuer_fallback:
        selected["emisor"] = issuer_fallback

    for name, candidate in selected.items():
        extraction.values[name] = candidate.value
        extraction.provenance.append(
            _candidate_provenance(name, candidate, ocr_needed, len({
                item.value for item in (
                    _labelled_candidates(fragments, specs[name][0], specs[name][1])
                    + _table_label_candidates(paginas, specs[name][0], specs[name][1])
                )
            }) > 1 if name in specs else False)
        )

    concepts = _concept_candidates(paginas, fragments)
    if concepts:
        unique = _dedupe_candidates(concepts)
        extraction.values["concepto"] = " | ".join(candidate.value for candidate in unique)
        for index, candidate in enumerate(unique, start=1):
            extraction.provenance.append(
                _candidate_provenance(f"concepto_linea_{index}", candidate, ocr_needed, False)
            )
        extraction.provenance.append(
            FieldProvenance(
                "concepto",
                extraction.values["concepto"],
                unique[0].fragment.page,
                "derivado",
                "líneas de concepto extraídas",
                _snippet(" | ".join(item.value for item in unique)),
                min(item.confidence for item in unique),
                "pendiente_revision" if len(unique) > 1 else _status(unique[0].confidence),
                ocr_needed,
            )
        )

    return _complete_missing_fields(extraction, ocr_needed)


def _labelled_candidates(
    fragments: Sequence[_Fragment], labels: str, kind: str
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    label = re.compile(rf"(?i)\b(?:{labels})\b")
    for fragment in fragments:
        lines = [line.strip() for line in fragment.text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            match = label.search(line)
            if not match:
                continue
            raw = line[match.end():].lstrip(" :#-|\t")
            allow_next = kind != "money" or line.rstrip().endswith(":")
            if not raw and allow_next and index + 1 < len(lines):
                raw = lines[index + 1]
            value = _parse_label_value(raw, kind)
            if not value and allow_next and index + 1 < len(lines):
                value = _parse_label_value(lines[index + 1], kind)
            if value:
                candidates.append(_Candidate(value, fragment, _snippet(line), 0.96))
        if fragment.source_type == "tabla":
            cells = [_clean(value) for value in fragment.text.split("|")]
            for index, cell in enumerate(cells):
                if not label.search(cell):
                    continue
                raw = label.sub("", cell).lstrip(" :#-")
                allow_next = kind != "money" or cell.rstrip().endswith(":")
                if not raw and allow_next and index + 1 < len(cells):
                    raw = cells[index + 1]
                value = _parse_label_value(raw, kind)
                if not value and allow_next and index + 1 < len(cells):
                    value = _parse_label_value(cells[index + 1], kind)
                if value:
                    candidates.append(_Candidate(value, fragment, _snippet(fragment.text), 0.98))
    return _dedupe_candidates(candidates)


def _parse_label_value(raw: str, kind: str) -> str:
    if kind == "date":
        match = _DATE_PATTERN.search(raw)
        return _normalise_date(match.group(0)) if match else ""
    if kind == "money":
        tokens = _money_values(raw)
        return _format_amount(tokens[-1]) if tokens else ""
    if kind == "invoice_number":
        value = re.sub(r"^(?:n[úu]m(?:ero)?\.?|n[ºo]|no\.?|#)\s*", "", raw, flags=re.I)
        match = re.search(r"\b[A-Z0-9][A-Z0-9/_-]{2,}\b", value, flags=re.I)
        return match.group(0) if match and any(char.isdigit() for char in match.group(0)) else ""
    value = re.split(r"\s{2,}|\s+\|\s+", raw, maxsplit=1)[0].strip(" -:|")
    value = re.split(
        r"(?i)\s+(?:n[ºo]\.?\s*)?factura\b|\s+(?:fecha|invoice\s+number)\b",
        value,
        maxsplit=1,
    )[0].strip(" -:|")
    return value if _is_text_value(value) else ""


def _table_label_candidates(
    paginas: Sequence[InvoicePage], labels: str, kind: str
) -> list[_Candidate]:
    """Read a labelled table column instead of flattening it into loose text."""

    label = re.compile(rf"(?i)\b(?:{labels})\b")
    candidates: list[_Candidate] = []
    for page in paginas:
        for table_number, table in enumerate(page.tables, start=1):
            for row_index, row in enumerate(table[:4]):
                columns = [index for index, cell in enumerate(row) if label.search(cell)]
                if not columns:
                    continue
                for column in columns:
                    for data_row in table[row_index + 1:]:
                        if column >= len(data_row):
                            continue
                        value = _parse_label_value(_clean(data_row[column]), kind)
                        if not value:
                            continue
                        fragment = _Fragment(
                            page.number,
                            "tabla",
                            f"página {page.number}, tabla {table_number}, columna {column + 1}",
                            " | ".join(_clean(cell) for cell in data_row),
                        )
                        is_total_row = any(
                            re.fullmatch(r"(?i)total(?:\s+factura)?", _clean(cell))
                            for cell in data_row
                        )
                        candidates.append(_Candidate(
                            value, fragment, _snippet(fragment.text), 0.99 if is_total_row else 0.98
                        ))
                break
    return _dedupe_candidates(candidates)


def _financial_summary_candidates(fragments: Sequence[_Fragment]) -> dict[str, _Candidate]:
    """Read ``Base / IVA / Total`` summaries preserved as aligned PDF text."""

    summaries: dict[str, _Candidate] = {}
    for fragment in fragments:
        if fragment.source_type != "texto":
            continue
        lines = [line.strip() for line in fragment.text.splitlines() if line.strip()]
        for index, header in enumerate(lines):
            normalized = header.casefold()
            has_base = "base imponible" in normalized or re.search(r"\bb\.?\s*i\.?\b", normalized)
            if not (has_base and re.search(r"\b(?:iva|vat)\b", normalized) and "total" in normalized):
                continue
            for total_line in lines[index + 1:index + 16]:
                if not re.match(r"(?i)^total(?:\s+factura)?\b", total_line):
                    continue
                values = _money_values(total_line)
                if len(values) < 3:
                    continue
                for field_name, amount in zip(
                    ("base_imponible", "iva", "total"), values[-3:]
                ):
                    summaries[field_name] = _Candidate(
                        _format_amount(amount), fragment, _snippet(total_line), 0.94
                    )
                break
    return summaries


def _issuer_from_tax_identity(
    fragments: Sequence[_Fragment], recipient: _Candidate | None
) -> _Candidate | None:
    """Use a legal name adjacent to a tax identity only as a reviewable fallback."""

    recipient_key = recipient.value.casefold() if recipient else ""
    identity = re.compile(
        r"(?i)\b(?:n\.?i\.?f\.?|c\.?i\.?f\.?|vat(?:\s*(?:no|number))?)\s*[:.-]?\s*[A-Z0-9-]{7,16}\b"
    )
    for fragment in fragments:
        lines = [line.strip() for line in fragment.text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if not identity.search(line):
                continue
            before = identity.split(line)[0].strip(" -:|,")
            candidate = before if _is_company_candidate(before) else (
                lines[index - 1] if index else ""
            )
            candidate = _clean_company_name(candidate)
            if (
                _is_company_candidate(candidate)
                and candidate.casefold() != recipient_key
                and not any(word in candidate.casefold() for word in ("cliente", "customer", "destinatario"))
            ):
                return _Candidate(candidate, fragment, _snippet(line), 0.68)
    return None


def _date_from_invoice_context(fragments: Sequence[_Fragment]) -> _Candidate | None:
    """Accept an unqualified ``Fecha`` only in a nearby invoice-data block."""

    for fragment in fragments:
        lines = [line.strip() for line in fragment.text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if not re.search(r"(?i)\bfecha\b", line):
                continue
            match = _DATE_PATTERN.search(line)
            context = " ".join(lines[max(0, index - 4):index + 1]).casefold()
            if match and ("datos factura" in context or "factura" in context):
                value = _normalise_date(match.group(0))
                if value:
                    return _Candidate(value, fragment, _snippet(line), 0.85)
    return None


def _concept_candidates(
    paginas: Sequence[InvoicePage], fragments: Sequence[_Fragment]
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    concept_headers = re.compile(
        r"(?i)\b(?:concepto|descripci[oó]n|detalle|art[ií]culo|producto|servicio|item)\b"
    )
    for page in paginas:
        for table_number, table in enumerate(page.tables, start=1):
            for row_index, row in enumerate(table[:4]):
                columns = [index for index, cell in enumerate(row) if concept_headers.search(cell)]
                if not columns:
                    continue
                column = columns[0]
                for data_row in table[row_index + 1:]:
                    if column >= len(data_row):
                        continue
                    value = _clean(data_row[column])
                    if _is_concept_value(value):
                        fragment = _Fragment(
                            page.number, "tabla", f"página {page.number}, tabla {table_number}",
                            " | ".join(_clean(cell) for cell in data_row),
                        )
                        candidates.append(_Candidate(value, fragment, _snippet(fragment.text), 0.97))
                break
    if candidates:
        return candidates

    for fragment in fragments:
        lines = [line.strip() for line in fragment.text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if not concept_headers.search(line):
                continue
            raw = concept_headers.sub("", line).lstrip(" :|-")
            if not raw and index + 1 < len(lines):
                raw = lines[index + 1]
            if _is_concept_value(raw):
                candidates.append(_Candidate(raw, fragment, _snippet(line), 0.92))
    return candidates


def _complete_missing_fields(extraction: InvoiceExtraction, ocr_needed: bool) -> InvoiceExtraction:
    fields = (
        "emisor", "receptor", "numero_factura", "fecha_emision", "fecha_vencimiento",
        "base_imponible", "iva", "retencion", "total", "concepto",
    )
    existing = {item.field for item in extraction.provenance}
    status = "requiere_ocr" if ocr_needed else "pendiente_revision"
    for name in fields:
        if name in existing:
            continue
        extraction.values.setdefault(name, "")
        extraction.provenance.append(
            FieldProvenance(
                name, "", None, "no_disponible", "sin evidencia textual extraíble", "",
                0.0, status, ocr_needed,
            )
        )
    return extraction


def _apply_review_threshold(extraction: InvoiceExtraction, threshold: float) -> InvoiceExtraction:
    revised = []
    for item in extraction.provenance:
        status = item.review_status
        if item.value and item.confidence < threshold and status == "automatico":
            status = "pendiente_revision"
        revised.append(FieldProvenance(
            item.field, item.value, item.page, item.source_type, item.source, item.snippet,
            item.confidence, status, item.ocr_needed,
        ))
    extraction.provenance = revised
    return extraction


def _candidate_provenance(
    field_name: str, candidate: _Candidate, ocr_needed: bool, ambiguous: bool
) -> FieldProvenance:
    return FieldProvenance(
        field_name, candidate.value, candidate.fragment.page, candidate.fragment.source_type,
        candidate.fragment.source, candidate.snippet, candidate.confidence,
        "pendiente_revision" if ambiguous else _status(candidate.confidence), ocr_needed,
    )


def _status(confidence: float) -> str:
    return "automatico" if confidence >= 0.90 else "pendiente_revision"


def _fragments(paginas: Sequence[InvoicePage]) -> Iterable[_Fragment]:
    for page in paginas:
        if page.text.strip():
            yield _Fragment(page.number, "texto", f"página {page.number}", page.text)
        for table_number, table in enumerate(page.tables, start=1):
            for row_number, row in enumerate(table, start=1):
                value = " | ".join(_clean(cell) for cell in row if _clean(cell))
                if value:
                    yield _Fragment(
                        page.number, "tabla", f"página {page.number}, tabla {table_number}, fila {row_number}",
                        value,
                    )


def _money_values(value: str) -> list[float]:
    values = [
        amount for raw in _MONEY_PATTERN.findall(value)
        if (amount := parse_amount(raw)) is not None
    ]
    if values:
        return values
    currency_values = re.findall(
        r"(?i)(?:€|eur)\s*([-+]?\s*(?:\d{1,3}(?:[.\s,]\d{3})+|\d+))|"
        r"([-+]?\s*(?:\d{1,3}(?:[.\s,]\d{3})+|\d+))\s*(?:€|eur)",
        value,
    )
    return [
        amount for pair in currency_values for raw in pair if raw
        if (amount := parse_amount(raw)) is not None
    ]


def _format_amount(value: float) -> str:
    return f"{value:.2f}"


def _normalise_date(value: str) -> str:
    cleaned = re.sub(r"\s+de\s+", " ", value.casefold()).replace(".", "/").strip()
    for pattern in ("%Y/%m/%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(cleaned, pattern).date().isoformat()
        except ValueError:
            pass
    month_match = re.fullmatch(r"(\d{1,2})\s+([a-záéíóúñ]+)\s+(\d{4})", cleaned)
    if month_match and month_match.group(2) in _MONTHS:
        return f"{month_match.group(3)}-{_MONTHS[month_match.group(2)]:02d}-{int(month_match.group(1)):02d}"
    english_match = re.fullmatch(r"([a-z]+)\s+(\d{1,2}),?\s+(\d{4})", cleaned)
    if english_match and english_match.group(1) in _MONTHS:
        return f"{english_match.group(3)}-{_MONTHS[english_match.group(1)]:02d}-{int(english_match.group(2)):02d}"
    return ""


def _dedupe_candidates(candidates: Sequence[_Candidate]) -> list[_Candidate]:
    unique: dict[str, _Candidate] = {}
    for candidate in candidates:
        key = candidate.value.casefold()
        if key and (key not in unique or candidate.confidence > unique[key].confidence):
            unique[key] = candidate
    return list(unique.values())


def _select_candidate(candidates: Sequence[_Candidate]) -> _Candidate:
    return sorted(candidates, key=lambda item: (-item.confidence, item.fragment.page))[0]


def _is_text_value(value: str) -> bool:
    return (
        len(value) >= 2
        and any(character.isalpha() for character in value)
        and len(value) <= 180
        and not re.search(r"(?i)^\W*(?:fecha|factura|cliente|proveedor|total|página|datos)\b", value)
        and not re.search(r"(?i)\bdatos\s+(?:empresa|factura|cliente)\b", value)
    )


def _is_company_candidate(value: str) -> bool:
    if not _is_text_value(value):
        return False
    lowered = value.casefold()
    return bool(re.search(r"\b(?:s\.?l\.?u?|s\.?a\.?s?|coop\.?|inc\.?|ltd\.?|llc)\b", lowered))


def _is_concept_value(value: str) -> bool:
    cleaned = _clean(value)
    if not _is_text_value(cleaned):
        return False
    lowered = cleaned.casefold()
    return not any(word in lowered for word in (
        "base imponible", "subtotal", "total", "iva", "vat", "retención",
        "página", "nif", "cif", "precio unitario", "cantidad",
    ))


def _clean(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _clean_company_name(value: str) -> str:
    value = re.split(
        r"(?i)\b(?:datos fiscales|c\.?i\.?f\.?|n\.?i\.?f\.?|vat)\b", _clean(value), maxsplit=1
    )[0]
    postcode = re.search(r"\b\d{5}\s+", value)
    legal_form = re.search(r"(?i)\b(?:s\.?l\.?u?|s\.?a\.?s?|coop\.?|inc\.?|ltd\.?|llc)\b", value)
    if postcode and legal_form and postcode.end() < legal_form.start():
        value = value[postcode.end():]
    return re.sub(r"[:,-]\s*[A-Z]-?\d{7,12}\s*$", "", value).strip(" -,:")


def _snippet(value: str, limit: int = 320) -> str:
    value = _clean(value)
    return value if len(value) <= limit else f"{value[:limit - 1]}…"


def _partida(documento: Mapping[str, Any], accion: Any) -> tuple[str, str]:
    if accion:
        return str(accion.phase), "actuación aprobada"
    return _partida_por_ruta(str(documento.get("ruta_relativa", ""))), "ruta contable"


def _provenance_main_fields(
    fila: Mapping[str, str], partida_source: str, extraction: InvoiceExtraction
) -> list[FieldProvenance]:
    """Add records for fixed-schema fields not represented by invoice fields."""

    source_fields = {
        "emisor": "emisor", "concepto_de_gasto": "concepto",
        "fecha_emision": "fecha_emision", "importe_sin_iva": "base_imponible",
    }
    result: list[FieldProvenance] = []
    for main_field, source_field in source_fields.items():
        source = next(item for item in extraction.provenance if item.field == source_field)
        result.append(FieldProvenance(
            main_field, fila[main_field], source.page, source.source_type, source.source,
            source.snippet, source.confidence, source.review_status, source.ocr_needed,
        ))
    for main_field in ("fecha_pago", "cargo_subvencion", "cargo_otros"):
        result.append(FieldProvenance(
            main_field, "", None, "no_disponible",
            "la factura no acredita pago ni distribución de financiación", "",
            0.0, "pendiente_revision", extraction.ocr_needed,
        ))
    result.append(FieldProvenance(
        "partida", fila["partida"], None, "derivado", partida_source, "",
        1.0 if fila["partida"] else 0.0,
        "automatico" if fila["partida"] else "pendiente_revision", extraction.ocr_needed,
    ))
    return result


def _review_row(
    gasto_id: str, filename: str, path: str, extraction: InvoiceExtraction
) -> dict[str, str]:
    missing = [
        name for name in ("emisor", "numero_factura", "fecha_emision", "base_imponible", "total", "concepto")
        if not extraction.value(name)
    ]
    pending = sorted({
        item.field for item in extraction.provenance
        if item.value and item.review_status != "automatico"
    })
    state = "requiere_ocr" if extraction.ocr_needed else (
        "pendiente_revision" if missing or pending else "automatico"
    )
    return {
        "id": gasto_id,
        "nombre_archivo": filename,
        "documento_ruta": path,
        "estado_revision": state,
        "requiere_ocr": "sí" if extraction.ocr_needed else "no",
        "campos_sin_extraer": "|".join(missing),
        "campos_a_revisar": "|".join(pending),
    }


def _guardar_campos(ruta: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = (
        "id", "nombre_archivo", "documento_ruta", "campo", "valor", "pagina",
        "tipo_fuente", "fuente", "fragmento", "confianza", "estado_revision", "requiere_ocr",
    )
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _guardar_revision(ruta: Path, rows: Sequence[Mapping[str, str]]) -> None:
    fields = (
        "id", "nombre_archivo", "documento_ruta", "estado_revision", "requiere_ocr",
        "campos_sin_extraer", "campos_a_revisar",
    )
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _partida_por_ruta(ruta: str) -> str:
    partes = ruta.split("/")
    etiquetas = {
        "MANTENIMIENTO TÉCNICO": "Software",
        "SERVIDOR": "Software",
        "GESTORIA": "Gestoría",
        "LEGAL": "Legal",
        "FORMACION": "Formación",
        "NOMINAS": "Laboral",
        "DIETAS": "Comercialización",
        "TRANSPORTE": "Comercialización",
        "SUMINISTROS": "Administración",
        "PROGRAMA ACOMPAÑAMIENTO": "Alianzas estratégicas",
    }
    return next((etiquetas[parte] for parte in reversed(partes) if parte in etiquetas), "")


def _id_gasto(ruta: str) -> str:
    return f"GAS-{sha1(ruta.encode()).hexdigest()[:12].upper()}"


def _columnas() -> list[str]:
    return [
        "id", "nombre_archivo", "emisor", "partida", "concepto_de_gasto",
        "fecha_emision", "fecha_pago", "cargo_subvencion", "cargo_otros",
        "importe_sin_iva", "nomina", "factura",
    ]


def _guardar_trazabilidad(tabla: pd.DataFrame, salida: Path) -> None:
    """Keep the legacy trace file, directing detailed review to the new CSV."""

    trazabilidad = tabla[
        ["id", "nombre_archivo", "emisor", "concepto_de_gasto", "fecha_emision", "importe_sin_iva"]
    ].copy()
    trazabilidad["origen_campos"] = (
        "Consulte extraccion_facturas_campos.csv: evidencia por página, tabla o texto; "
        "pago y cargos permanecen vacíos sin soporte."
    )
    salida.with_name("relacion_facturas_gastos_trazabilidad.csv").write_text(
        trazabilidad.to_csv(index=False, lineterminator="\n"), encoding="utf-8"
    )
