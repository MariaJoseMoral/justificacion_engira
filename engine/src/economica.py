"""Conservative adapter for the normalized economic XLSX template."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook

from .evidencias import EvidenceLink
from .plan import CanonicalPlan, parse_amount


@dataclass(frozen=True)
class FinancialRecord:
    document_path: str
    action_id: str
    action_title: str
    amount: float
    issue_date: str
    document_type: str
    review_state: str


def extraer_gastos_validados(
    inventory: Iterable[dict[str, Any]], plan: CanonicalPlan, links: Iterable[EvidenceLink]
) -> tuple[list[FinancialRecord], list[str]]:
    """Extract only unambiguous expenses with an automatic approved-action link."""
    actions = {action.id: action for action in plan.actions}
    link_by_path = {link.document_path: link for link in links}
    records: list[FinancialRecord] = []
    warnings: list[str] = []
    valid_types = {"factura", "factura_gasto_viaje", "nomina", "recibo"}
    for document in inventory:
        if document.get("tipo_documental") not in valid_types:
            continue
        path = str(document.get("ruta_relativa") or document.get("nombre") or "")
        link = link_by_path.get(path)
        if not link or link.review_state != "automatico" or not link.action_id:
            warnings.append(f"Gasto no cargado por vínculo no automático: {path}")
            continue
        amounts = {
            amount for amount in (
                parse_amount(value) for value in _split_values(document.get("importes_detectados"))
            ) if amount is not None
        }
        if len(amounts) != 1:
            warnings.append(f"Gasto no cargado por importe ambiguo o ausente: {path}")
            continue
        dates = _split_values(document.get("fechas_detectadas"))
        records.append(
            FinancialRecord(
                document_path=path,
                action_id=link.action_id,
                action_title=actions[link.action_id].title,
                amount=amounts.pop(),
                issue_date=dates[0] if dates else "",
                document_type=str(document.get("tipo_documental")),
                review_state=link.review_state,
            )
        )
    return records, warnings


class AdaptadorMemoriaEconomica:
    """Populate documented fields while retaining the official workbook layout."""

    # The template has six lines for externally provided services funded by other income.
    _EXTERNAL_ROWS = range(71, 77)

    def __init__(self, config: dict[str, Any], plan: CanonicalPlan, records: list[FinancialRecord]):
        self.config = config
        self.plan = plan
        self.records = records

    def generar(self, template: Path, output: Path) -> None:
        workbook = load_workbook(template)
        sheet = workbook.active
        project = self.config["proyecto"]
        sheet["A8"] = f"Razón social: {project.get('entidad', '')}"
        sheet["L8"] = f"Nº de Expediente: {project.get('expediente', '')}"
        sheet["A9"] = f"Proyecto: {project.get('nombre', '')}"

        # No concession amount is treated as received income unless configured explicitly.
        received = self.config.get("subvencion", {}).get("importe_cobrado")
        if received is not None:
            sheet["M13"] = float(received)

        for row, record in zip(self._EXTERNAL_ROWS, self.records):
            action = next(action for action in self.plan.actions if action.id == record.action_id)
            # Several template cells are vertically merged in pairs.  Populate
            # only their anchor cells and retain the supplied subtotal formulas.
            if row % 2:
                sheet.cell(row, 2).value = action.phase
                sheet.cell(row, 12).value = self.plan.phase_budgets.get(action.phase)
                sheet.cell(row, 13).value = f"=K{row}-L{row}"
            sheet.cell(row, 4).value = record.action_title
            sheet.cell(row, 6).value = record.document_path
            sheet.cell(row, 8).value = record.issue_date
            sheet.cell(row, 10).value = record.amount

        sheet["M90"] = "=J52"
        sheet["M91"] = "=J84"
        self._write_traceability_sheet(workbook)
        output.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(output)

    def _write_traceability_sheet(self, workbook: Any) -> None:
        name = "TRAZABILIDAD_PIPELINE"
        if name in workbook.sheetnames:
            del workbook[name]
        sheet = workbook.create_sheet(name)
        sheet.append(
            ("documento", "accion_id", "actuacion_aprobada", "importe", "fecha_emision", "estado_revision")
        )
        for record in self.records:
            sheet.append(
                (
                    record.document_path, record.action_id, record.action_title,
                    record.amount, record.issue_date, record.review_state,
                )
            )
        sheet.append(())
        sheet.append(("Nota", "Solo se cargan gastos con importe único y vínculo automático."))


def _split_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [item for item in str(value or "").split("|") if item]
