"""Canonical representation of the approved project plan.

The model deliberately preserves the wording and amounts in the approved
chronogram.  It is the only source used to define actions in generated files.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha1
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable

from docx import Document


@dataclass(frozen=True)
class PlanAction:
    """One approved action, identified independently of its table row."""

    id: str
    phase: str
    area: str
    title: str
    approved_period: str
    period_start: str | None
    period_end: str | None
    approved_budget: float | None
    budget_scope: str
    source: str


@dataclass(frozen=True)
class CanonicalPlan:
    """Actions and phase budgets read from the approved project documentation."""

    source_documents: tuple[str, ...]
    actions: tuple[PlanAction, ...]
    phase_budgets: dict[str, float]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_documents": list(self.source_documents),
            "actions": [asdict(action) for action in self.actions],
            "phase_budgets": self.phase_budgets,
            "warnings": list(self.warnings),
        }


_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def normalizar_texto(value: str) -> str:
    """Return a stable comparison key without changing displayed source text."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def parse_amount(value: object) -> float | None:
    """Parse common Spanish/European money formats without guessing plain text."""
    if value is None:
        return None
    text = str(value).replace("\xa0", " ").strip()
    match = re.search(r"[-+]?\s*(?:\d{1,3}(?:[.\s]\d{3})+|\d+)(?:,\d{1,2}|\.\d{1,2})?", text)
    if not match:
        return None
    number = match.group(0).replace(" ", "")
    if "," in number:
        number = number.replace(".", "").replace(",", ".")
    elif number.count(".") > 1:
        number = number.replace(".", "")
    elif "." in number and len(number.rsplit(".", 1)[1]) == 3:
        number = number.replace(".", "")
    try:
        return float(number)
    except ValueError:
        return None


def parse_approved_plan(config: dict[str, Any], data_root: Path) -> CanonicalPlan:
    """Find configured chronograms under the logical submitted-project folder."""
    plan_config = config.get("plan_aprobado", {})
    project_folder = config["rutas_entrada"]["proyecto_presentado"]
    root = data_root / project_folder
    patterns = plan_config.get("patrones_cronograma", ["*cronograma*.docx", "*Cronograma*.docx"])
    documents: list[Path] = []
    for pattern in patterns:
        documents.extend(sorted(root.glob(pattern)))
    unique_documents = list(dict.fromkeys(documents))
    if not unique_documents:
        raise FileNotFoundError(
            f"No se ha encontrado un cronograma aprobado en {root}. "
            "Configure plan_aprobado.patrones_cronograma."
        )
    return parse_plan_documents(unique_documents, data_root)


def parse_plan_documents(
    documents: Iterable[Path], data_root: Path | None = None
) -> CanonicalPlan:
    """Parse chronogram tables from DOCX files into a canonical plan."""
    actions: list[PlanAction] = []
    sources: list[str] = []
    warnings: list[str] = []
    phase_budgets: dict[str, float] = {}

    for source_path in documents:
        source_path = Path(source_path)
        source_label = _source_label(source_path, data_root)
        doc = Document(source_path)
        sources.append(source_label)
        found_table = False
        for table in doc.tables:
            columns = _chronogram_columns(table)
            if columns is None:
                continue
            found_table = True
            header_row, phase_column, period_column, action_column, budget_column = columns
            for row in table.rows[header_row + 1:]:
                cells = [_clean(cell.text) for cell in row.cells]
                if max(phase_column, period_column, action_column, budget_column) >= len(cells):
                    continue
                phase, period, title, budget_raw = (
                    cells[phase_column], cells[period_column], cells[action_column], cells[budget_column]
                )
                if not phase or not title or _is_total_row(phase, title):
                    continue
                amount = parse_amount(budget_raw)
                start, end = parse_period(period)
                action_id = stable_action_id(phase, title, period)
                action = PlanAction(
                    id=action_id,
                    phase=phase,
                    area=normalizar_texto(phase).replace(" ", "_"),
                    title=title,
                    approved_period=period,
                    period_start=start,
                    period_end=end,
                    approved_budget=amount,
                    budget_scope="phase",
                    source=source_label,
                )
                if action.id not in {existing.id for existing in actions}:
                    actions.append(action)
                else:
                    warnings.append(f"Acción duplicada ignorada: {action.id} ({source_label})")
                if amount is not None:
                    previous = phase_budgets.get(phase)
                    if previous is None:
                        phase_budgets[phase] = amount
                    elif previous != amount:
                        warnings.append(
                            f"Presupuestos distintos para la fase '{phase}': "
                            f"{previous:.2f} y {amount:.2f}."
                        )
        if not found_table:
            warnings.append(f"No se detectó una tabla de cronograma en {source_label}.")

    if not actions:
        raise ValueError("El cronograma aprobado no contiene acciones interpretables.")
    return CanonicalPlan(tuple(sources), tuple(actions), phase_budgets, tuple(warnings))


def stable_action_id(phase: str, title: str, period: str) -> str:
    """Create a repeatable ID from approved content rather than a row number."""
    phase_key = normalizar_texto(phase).replace(" ", "-")[:18].upper() or "SIN-FASE"
    fingerprint = sha1(
        "|".join((normalizar_texto(phase), normalizar_texto(title), normalizar_texto(period))).encode()
    ).hexdigest()[:10].upper()
    return f"ACC-{phase_key}-{fingerprint}"


def parse_period(value: str) -> tuple[str | None, str | None]:
    """Extract the first and last month/year in an approved Spanish period."""
    matches = re.findall(
        r"(?i)\b(" + "|".join(_MONTHS) + r")\s+(20\d{2})\b", value
    )
    if not matches:
        iso = re.findall(r"\b(20\d{2})-(\d{2})(?:-\d{2})?\b", value)
        if iso:
            return f"{iso[0][0]}-{iso[0][1]}-01", f"{iso[-1][0]}-{iso[-1][1]}-28"
        return None, None
    start_month, start_year = matches[0]
    end_month, end_year = matches[-1]
    start = date(int(start_year), _MONTHS[start_month.casefold()], 1).isoformat()
    # The day is intentionally month-level: the source chronogram has no day.
    end = date(int(end_year), _MONTHS[end_month.casefold()], 28).isoformat()
    return start, end


def _chronogram_columns(table: Any) -> tuple[int, int, int, int, int] | None:
    for row_index, row in enumerate(table.rows[:3]):
        headers = [normalizar_texto(cell.text) for cell in row.cells]
        phase = next((i for i, text in enumerate(headers) if "denominacion" in text and "fase" in text), None)
        period = next((i for i, text in enumerate(headers) if "fecha" in text), None)
        action = next((i for i, text in enumerate(headers) if "actuacion" in text), None)
        budget = next((i for i, text in enumerate(headers) if "cuantia" in text or "gasto" in text), None)
        if None not in (phase, period, action, budget):
            return row_index, phase, period, action, budget
    return None


def _is_total_row(phase: str, title: str) -> bool:
    return "suma total" in normalizar_texto(phase) or "suma total" in normalizar_texto(title)


def _source_label(path: Path, root: Path | None) -> str:
    if root is None:
        return path.name
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())
