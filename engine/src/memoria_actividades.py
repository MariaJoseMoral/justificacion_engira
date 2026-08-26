"""Populate the normalized activity template from approved actions and evidence."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from docx import Document

from .economica import FinancialRecord
from .evidencias import EvidenceLink
from .plan import CanonicalPlan, PlanAction


class GeneradorMemoriaActividades:
    """Generate a traceable chronogram without drafting unsupported narrative."""

    def __init__(
        self,
        config: dict[str, Any],
        plan: CanonicalPlan,
        links: Iterable[EvidenceLink],
        financial_records: Iterable[FinancialRecord] = (),
    ):
        self.config = config
        self.plan = plan
        self.links = list(links)
        self.financial_records = list(financial_records)

    def generar(self, plantilla: Path, salida: Path) -> None:
        documento = Document(plantilla)
        if not documento.tables:
            raise ValueError("La plantilla de memoria de actividades no contiene la tabla de cronograma.")
        self._rellenar_cronograma(documento.tables[0])
        salida.parent.mkdir(parents=True, exist_ok=True)
        documento.save(salida)

    def _rellenar_cronograma(self, table: Any) -> None:
        phases = self._phase_actions()
        required_rows = 1 + len(phases) + 1  # heading + phases + total
        while len(table.rows) < required_rows:
            table.add_row()

        evidence_by_action = defaultdict(list)
        for link in self.links:
            if link.action_id:
                evidence_by_action[link.action_id].append(link)
        actual_by_action = defaultdict(float)
        for record in self.financial_records:
            actual_by_action[record.action_id] += record.amount

        for index, (phase, actions) in enumerate(phases, start=1):
            row = table.rows[index]
            row.cells[0].text = phase
            row.cells[1].text = self._phase_period(actions)
            row.cells[2].text = self._phase_detail(actions, evidence_by_action)
            actual = sum(actual_by_action[action.id] for action in actions)
            row.cells[3].text = (
                f"{actual:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
                if actual else "0,00 € (sin gasto validado)"
            )

        total_row = table.rows[1 + len(phases)]
        total_row.cells[0].text = "TOTAL"
        total_row.cells[1].text = ""
        total_row.cells[2].text = (
            "Total calculado exclusivamente con gastos documentados, de importe único "
            "y vínculo automático a una actuación aprobada."
        )
        total = sum(record.amount for record in self.financial_records)
        total_row.cells[3].text = (
            f"{total:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        )

    def _phase_actions(self) -> list[tuple[str, list[PlanAction]]]:
        grouped: dict[str, list[PlanAction]] = {}
        for action in self.plan.actions:
            grouped.setdefault(action.phase, []).append(action)
        return list(grouped.items())

    @staticmethod
    def _phase_period(actions: list[PlanAction]) -> str:
        periods = list(dict.fromkeys(action.approved_period for action in actions))
        return " / ".join(periods)

    def _phase_detail(
        self, actions: list[PlanAction], evidence_by_action: dict[str, list[EvidenceLink]]
    ) -> str:
        lines: list[str] = []
        budget = self.plan.phase_budgets.get(actions[0].phase)
        if budget is not None:
            lines.append(f"Presupuesto aprobado de fase: {budget:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        for action in actions:
            lines.append(f"[{action.id}] {action.title}")
            linked = evidence_by_action.get(action.id, [])
            if linked:
                for link in linked:
                    lines.append(
                        f"  Evidencia ({link.review_state}, {link.confidence:.0%}): {link.document_path}"
                    )
            else:
                lines.append("  Sin evidencia vinculada; requiere revisión.")
        return "\n".join(lines)
