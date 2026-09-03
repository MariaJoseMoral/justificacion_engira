"""Conservative adapter for the normalized economic XLSX template."""

from __future__ import annotations

from collections import defaultdict
from collections import Counter
from dataclasses import dataclass, replace
import math
from pathlib import Path
import re
from typing import Any, Iterable

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
import pandas as pd
import pdfplumber

from .evidencias import EvidenceLink
from .plan import CanonicalPlan, normalizar_texto, parse_amount


@dataclass(frozen=True)
class FinancialRecord:
    document_path: str
    action_id: str
    action_title: str
    amount: float
    issue_date: str
    document_type: str
    review_state: str


@dataclass(frozen=True)
class RelationExpense:
    numero_factura: str
    emisor: str
    tipo_gasto: str
    gasto_original: str
    gasto_normalizado: str
    cargo: str
    partida: str
    concepto: str
    importe: float
    fecha_factura: str
    fecha_pago: str
    mes_nomina: str = ""
    nombre_perceptor: str = ""


def extraer_gastos_validados(
    inventory: Iterable[dict[str, Any]],
    plan: CanonicalPlan,
    links: Iterable[EvidenceLink],
) -> tuple[list[FinancialRecord], list[str]]:
    """
    Extrae los documentos económicos situados físicamente en
    CONTABILIDAD/GASTOS.

    La pertenencia a la carpeta GASTOS y el indicador es_gasto tienen
    prioridad sobre la clasificación automática del tipo documental.
    Esto evita perder facturas mal clasificadas como presupuesto,
    nómina, documento, etc.
    """
    actions = {action.id: action for action in plan.actions}
    link_by_path = {link.document_path: link for link in links}

    records: list[FinancialRecord] = []
    warnings: list[str] = []

    for document in inventory:
        path = str(
            document.get("ruta_relativa")
            or document.get("nombre")
            or ""
        )

        # Solo documentos situados en la carpeta contable de gastos.
        if "/CONTABILIDAD/GASTOS/" not in path.replace("\\", "/"):
            continue

        # Debe estar identificado funcionalmente como gasto.
        es_gasto = document.get("es_gasto")

        if isinstance(es_gasto, str):
            es_gasto = es_gasto.strip().lower() in {
                "true", "1", "yes", "si", "sí"
            }

        if not es_gasto:
            continue

        # Necesitamos vínculo con una acción aprobada.
        link = link_by_path.get(path)

        if not link or not link.action_id:
            warnings.append(
                f"Gasto no cargado por falta de vínculo "
                f"con acción aprobada: {path}"
            )
            continue

        if link.action_id not in actions:
            warnings.append(
                f"Gasto no cargado: acción aprobada inexistente "
                f"{link.action_id}: {path}"
            )
            continue

        # Extraer importes detectados.
        amounts = [
            amount
            for amount in (
                parse_amount(value)
                for value in _split_values(
                    document.get("importes_detectados")
                )
            )
            if amount is not None and amount > 0
        ]

        amount = _resolve_amount(path, amounts, warnings)

        if amount is None:
            warnings.append(
                f"Gasto detectado pero sin importe resoluble: {path}"
            )
            continue

        dates = _split_values(
            document.get("fechas_detectadas")
        )

        records.append(
            FinancialRecord(
                document_path=path,
                action_id=link.action_id,
                action_title=actions[link.action_id].title,
                amount=amount,
                issue_date=dates[0] if dates else "",
                document_type=str(
                    document.get("tipo_documental") or "gasto"
                ),
                review_state=link.review_state,
            )
        )

    return records, warnings


class AdaptadorMemoriaEconomica:
    """Populate documented fields while retaining the official workbook layout."""

    # Section definitions ordered bottom-to-top for dynamic row insertion.
    # Each tuple: (section_key, tpl_first_data_row, tpl_last_data_row, tpl_total_row)
    _SECTION_DEFS: list[tuple[tuple[str, str], int, int, int]] = [
        (("APORTACION PROPIA", "ORDINARIO"), 79, 82, 83),
        (("APORTACION PROPIA", "EXTERNO"),   71, 76, 77),
        (("APORTACION PROPIA", "AUTONOMA"),  65, 68, 69),
        (("APORTACION PROPIA", "NOMINA"),    58, 61, 62),
        (("AYUDA", "EXTERNO"),               45, 50, 51),
        (("AYUDA", "PROTOCOLARIO"),          39, 42, 43),
        (("AYUDA", "AUTONOMA"),              31, 36, 37),
        (("AYUDA", "NOMINA"),                24, 27, 28),
    ]
    _T1_TOTAL_ROW = 52
    _T2_TOTAL_ROW = 84
    # APORTACION PROPIA proveedores with these partidas → "gastos ordinarios" section
    _ORDINARIO_PARTIDAS = frozenset({"gestoria", "administracion"})

    def __init__(self, config: dict[str, Any], plan: CanonicalPlan, records: list[FinancialRecord]):
        self.config = config
        self.plan = plan
        self.records = records
        self._accounting_index = self._load_accounting_index()
        self._relation_expenses = self._load_relation_expenses()
        self._authorized_budget = self._load_authorized_budget()
        self._grouped_rows = self._group_expenses()

    def _data_root(self) -> Path:
        root = self.config.get("_data_root")
        if root is None:
            raise ValueError("No existe _data_root en la configuración del pipeline.")
        return Path(root)

    def _relation_xlsx_path(self) -> Path:
        folder = self.config["rutas_entrada"]["justificacion_economica"]
        candidates = [
            self._data_root() / folder / "relacion_gastos.xlsx",
            self._data_root() / folder / "CONTABILIDAD" / "relacion_gastos.xlsx",
        ]
        for path in candidates:
            if path.exists():
                return path
        raise FileNotFoundError(
            "No se ha encontrado la relación de gastos esperada en "
            f"{candidates[0]} ni en {candidates[1]}."
        )

    def _budget_pdf_path(self) -> Path:
        folder = self.config["rutas_entrada"]["desviaciones"]
        path = self._data_root() / folder / "presupuesto modificaciones sustanciales_signed.pdf"
        if not path.exists():
            raise FileNotFoundError(f"No se ha encontrado el presupuesto autorizado: {path}")
        return path

    def _load_accounting_index(self) -> dict[str, list[dict[str, str]]]:
        root = self._data_root() / "08_JUSTIFICACION_ECONOMICA" / "CONTABILIDAD"
        index: dict[str, list[dict[str, str]]] = defaultdict(list)
        if not root.exists():
            return index
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            lower = path.as_posix().lower()
            if "nominas" in lower:
                kind = "NOMINA"
            elif "autonoma" in lower:
                kind = "AUTONOMA"
            elif "proveedores externos" in lower or "gastos" in lower:
                kind = "EXTERNO"
            else:
                continue
            text = normalizar_texto(path.stem)
            person = ""
            for alias, label in (
                ("carles harillo", "Carles Harillo Magnet"),
                ("darlene", "Darlene Rodríguez Fernández"),
                ("maria jose", "María José Moral Morgado"),
                ("maria jose moral", "María José Moral Morgado"),
                ("moral", "María José Moral Morgado"),
            ):
                if alias in text:
                    person = label
                    break
            month_year = ""
            match = re.search(r"(?:0?[1-9]|1[0-2])[/-](?:20\d{2}|\d{2})", path.name)
            if match:
                month_year = match.group(0)
            if "20" not in month_year and re.search(r"20\d{2}", path.name):
                month_year = re.search(r"20\d{2}", path.name).group(0)
            for target_kind in {kind, "AUTONOMA" if kind == "NOMINA" else kind}:
                index[target_kind].append({"path": str(path), "person": person, "month_year": month_year})
        return dict(index)

    def _enrich_expense_from_accounting(self, expense: RelationExpense) -> RelationExpense:
        entidad = self.config.get("proyecto", {}).get("entidad", "")
        candidates = self._accounting_index.get(expense.tipo_gasto, [])
        best = None
        for candidate in candidates:
            if not candidate["person"] and not candidate["month_year"]:
                continue
            if expense.importe and candidate["path"] and str(expense.importe) in candidate["path"]:
                best = candidate
                break
            best = candidate
        if best is None:
            # For autónoma, still fix the emisor and perceptor even without accounting match.
            if expense.tipo_gasto == "AUTONOMA":
                emisor = expense.emisor
                if not emisor or emisor.upper() in {"AUTONOMA", "NOMINA", "NÓMINA"}:
                    emisor = entidad
                return replace(expense, emisor=emisor, nombre_perceptor=entidad)
            return expense
        fallback_person = (
            expense.nombre_perceptor
            if expense.nombre_perceptor
            and expense.nombre_perceptor.upper() not in {"NOMINA", "AUTONOMA", "NÓMINA"}
            else ""
        )
        # Autónoma work is always performed by the project owner; use entidad directly.
        if expense.tipo_gasto == "AUTONOMA":
            person = entidad
        else:
            # Prefer the already-known perceptor name (e.g. from CONCEPTO column) over
            # the generic accounting-index match, which may be the project owner's name
            # regardless of which employee the payslip belongs to.
            person = fallback_person or best.get("person") or expense.concepto or entidad
        month_year = (
            expense.mes_nomina
            or best.get("month_year")
            or _month_year_placeholder(expense.fecha_factura, expense.fecha_pago)
        )
        emisor = expense.emisor
        if not emisor or emisor.upper() in {"AUTONOMA", "NOMINA", "NÓMINA"}:
            emisor = person or entidad
        if expense.tipo_gasto in {"NOMINA", "AUTONOMA"}:
            return replace(
                expense,
                emisor=emisor,
                nombre_perceptor=person or entidad,
                mes_nomina=month_year,
            )
        return replace(expense, emisor=emisor)

    def _load_relation_expenses(self) -> list[RelationExpense]:
        """
        Carga los gastos consolidados desde relacion_gastos.xlsx y añade
        automáticamente los nuevos documentos económicos detectados por
        el pipeline que todavía no estén incluidos en esa relación.
        """

    # ------------------------------------------------------------------
    # 1. Cargar relación de gastos consolidada/manual
    # ------------------------------------------------------------------
        frame = pd.read_excel(self._relation_xlsx_path(), sheet_name="Hoja 1")
        columns = {str(column): normalizar_texto(str(column)) for column in frame.columns}

        def pick(*patterns: str) -> str:
            for column, key in columns.items():
                if all(pattern in key for pattern in patterns):
                    return column
            raise KeyError(f"No existe columna para patrones {patterns}.")

        col_numero = pick("factura")
        col_emisor = pick("emisor")
        col_gastos = pick("gasto")
        col_partida = pick("partida")
        col_cargo = pick("cargo")
        col_concepto = pick("concepto", "gasto")
        col_importe = pick("importe")
        col_fecha_factura = pick("fecha", "factura")
        col_fecha_pago = pick("fecha", "pago")

        expenses: list[RelationExpense] = []

        for _, row in frame.iterrows():
            cargo = _clean_text(row.get(col_cargo))
            partida = _clean_text(row.get(col_partida))
            gasto_original = _clean_text(row.get(col_gastos))
            gasto_normalizado = normalizar_gasto_label(gasto_original)

            if not cargo or not partida or not gasto_original:
                continue

            tipo = _normalize_expense_type(gasto_normalizado)

            numero_factura = _clean_text(row.get(col_numero))
            if _looks_like_date_token(numero_factura):
                numero_factura = ""

            concepto = _clean_text(row.get(col_concepto))
            if not concepto:
                concepto = partida

            fecha_factura_raw = row.get(col_fecha_factura)
            fecha_pago_raw = row.get(col_fecha_pago)

            emisor = _clean_text(row.get(col_emisor))
            fecha_factura = _format_relation_date(fecha_factura_raw)
            fecha_pago = _format_relation_date(fecha_pago_raw)

            mes_nomina = _month_year_placeholder(fecha_factura, fecha_pago)

            if not mes_nomina and emisor and _looks_like_date_token(emisor):
                mes_nomina = _month_year_placeholder(emisor[:10], "")

            nombre_perceptor = _clean_text(
                row.get("Nombre y apellidos del perceptor")
            )

            if tipo in {"NOMINA", "AUTONOMA"}:
                if not fecha_pago and fecha_factura:
                    fecha_pago = fecha_factura

                if not mes_nomina:
                    mes_nomina = _month_year_placeholder(
                        fecha_factura,
                        fecha_pago,
                    )

                if not nombre_perceptor:
                    nombre_perceptor = concepto

            amount = _parse_relation_amount(row.get(col_importe))

            if amount is None or amount <= 0:
                if tipo in {"NOMINA", "AUTONOMA"}:
                    amount = _parse_relation_amount(fecha_factura_raw)

                if amount is None or amount <= 0:
                    continue

            expense = RelationExpense(
                numero_factura=numero_factura,
                emisor=emisor,
                tipo_gasto=tipo,
                gasto_original=gasto_original,
                gasto_normalizado=gasto_normalizado,
                cargo=_normalize_charge(cargo),
                partida=partida,
                concepto=concepto,
                importe=float(amount),
                fecha_factura=fecha_factura,
                fecha_pago=fecha_pago,
                mes_nomina=mes_nomina,
                nombre_perceptor=nombre_perceptor,
            )

            expenses.append(
                self._enrich_expense_from_accounting(expense)
            )

        return expenses

    def _load_authorized_budget(self) -> dict[tuple[str, str], float]:
        budget: dict[tuple[str, str], float] = defaultdict(float)
        with pdfplumber.open(self._budget_pdf_path()) as pdf:
            for page in pdf.pages:
                page_text = normalizar_texto(page.extract_text() or "")
                cargo = _cargo_from_budget_page(page_text)
                if not cargo:
                    continue
                for table in page.extract_tables() or []:
                    current_partida = ""
                    for row in table:
                        values = [_clean_text(item) for item in row]
                        if not any(values):
                            continue
                        partida_value = values[1] if len(values) > 1 else ""
                        if partida_value:
                            current_partida = partida_value
                        if not current_partida:
                            continue
                        normalized_partida = normalizar_texto(current_partida)
                        if "total" in normalized_partida:
                            continue
                        if not re.search(r"[a-z]", normalized_partida):
                            continue
                        amount = parse_amount(values[-1] if values else "")
                        if amount is None or amount <= 0:
                            continue
                        key = (cargo, normalized_partida)
                        budget[key] += float(amount)
        return dict(budget)

    def _budget_for_partida(self, cargo: str, partida: str) -> float | None:
        normalized_partida = normalizar_texto(partida)
        exact = self._authorized_budget.get((cargo, normalized_partida))
        if exact is not None:
            return exact
        matches = [
            amount
            for (budget_cargo, budget_partida), amount in self._authorized_budget.items()
            if budget_cargo == cargo
            and (
                normalized_partida in budget_partida
                or budget_partida in normalized_partida
                or _token_overlap(normalized_partida, budget_partida)
            )
        ]
        return max(matches) if matches else None

    def _group_expenses(self) -> dict[tuple[str, str], list[dict[str, Any]]]:
        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for expense in self._relation_expenses:
            key = (expense.cargo, expense.tipo_gasto, expense.partida)
            bucket = grouped.setdefault(
                key,
                {
                    "cargo": expense.cargo,
                    "tipo_gasto": expense.tipo_gasto,
                    "partida": expense.partida,
                    "conceptos": [],
                    "justificantes": [],
                    "fechas_factura": [],
                    "importe": 0.0,
                },
            )
            if expense.concepto:
                bucket["conceptos"].append(expense.concepto)
            if expense.numero_factura:
                bucket["justificantes"].append(expense.numero_factura)
            if expense.fecha_factura:
                bucket["fechas_factura"].append(expense.fecha_factura)
            bucket["importe"] += float(expense.importe)

        by_section: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for bucket in grouped.values():
            section_key = (bucket["cargo"], bucket["tipo_gasto"])
            by_section[section_key].append(bucket)
        for section in by_section.values():
            section.sort(key=lambda item: normalizar_texto(item["partida"]))
        return dict(by_section)

    def _set_cell_value(self, sheet: Any, row: int, column: int, value: Any) -> None:
        target = sheet.cell(row, column)
        if isinstance(target, MergedCell):
            for merged_range in sheet.merged_cells.ranges:
                if (
                    merged_range.min_row <= row <= merged_range.max_row
                    and merged_range.min_col <= column <= merged_range.max_col
                ):
                    anchor = sheet.cell(merged_range.min_row, merged_range.min_col)
                    anchor.value = value
                    return
        target.value = value

    def generar(self, template: Path, output: Path) -> None:
        """Populate the official economic memory workbook from relacion_gastos data."""
        from copy import copy as _copy
        wb = load_workbook(template)
        ws = wb.active
        project = self.config["proyecto"]

        # ── Header ──────────────────────────────────────────────────────────
        ws["A8"] = f"Razón social: {project.get('entidad', '')}"
        ws["L8"] = f"Nº de Expediente: {project.get('expediente', '')}"
        ws["A9"] = f"Proyecto: {project.get('nombre', '')}"

        # ── Income section ───────────────────────────────────────────────────
        ayuda = float(self.config.get("subvencion", {}).get("importe_concedido", 0))
        if ayuda:
            ws["M13"] = ayuda
        propia = sum(e.importe for e in self._relation_expenses if e.cargo == "APORTACION PROPIA")
        if propia:
            ws["M14"] = round(propia, 2)

        # ── Classify expenses into the 8 template sections ───────────────────
        expenses_by_section = self._classify_by_section()
        perceptor_default = project.get("entidad", "")

        # ── Compute extra rows needed per section (key = tpl_total_row) ──────
        extras_by_tpl_total: dict[int, int] = {}
        for sec_key, tpl_f, tpl_l, tpl_t in self._SECTION_DEFS:
            n_items = len(expenses_by_section.get(sec_key, []))
            n_tpl = tpl_l - tpl_f + 1
            extras_by_tpl_total[tpl_t] = max(0, n_items - n_tpl)

        def actual_row(tpl_r: int) -> int:
            """Template row → actual row after all insertions."""
            return tpl_r + sum(
                extra for tt, extra in extras_by_tpl_total.items() if tt <= tpl_r
            )

        def actual_first(tpl_f: int) -> int:
            """First data row of a section in the final sheet."""
            return tpl_f + sum(
                extra for tt, extra in extras_by_tpl_total.items() if tt < tpl_f
            )

        # ── openpyxl 3.x insert_rows does not reliably shift merged ranges.
        #    Strategy: save all template merges, remove them, do all insertions
        #    and data writes, then re-apply merges at their correct final positions.
        template_merges = [
            (mc.min_row, mc.min_col, mc.max_row, mc.max_col)
            for mc in list(ws.merged_cells.ranges)
        ]
        # The data-area template merges (B:M within each section's data rows) will
        # be replaced by per-partida-group merges; skip them when re-applying.
        data_area_merges: set[tuple[int, int, int, int]] = set()
        for _, tpl_f, tpl_l, _ in self._SECTION_DEFS:
            for r1, c1, r2, c2 in template_merges:
                if c1 > 1 and r1 >= tpl_f and r2 <= tpl_l:
                    data_area_merges.add((r1, c1, r2, c2))
        # Remove all merges now so insert_rows operates on plain cells
        for mc in list(ws.merged_cells.ranges):
            ws.unmerge_cells(str(mc))

        # ── Insert rows and write cell values (bottom to top, no merges yet) ─
        for sec_key, tpl_f, tpl_l, tpl_t in self._SECTION_DEFS:
            items = expenses_by_section.get(sec_key, [])
            extra = extras_by_tpl_total[tpl_t]

            # Insert extra rows just before the total row, copying source style
            if extra > 0:
                src_style_row = tpl_l
                ws.insert_rows(tpl_t, extra)
                for dst_row in range(tpl_t, tpl_t + extra):
                    for col in range(1, ws.max_column + 1):
                        src = ws.cell(src_style_row, col)
                        dst = ws.cell(dst_row, col)
                        if src.has_style:
                            dst.font = _copy(src.font)
                            dst.fill = _copy(src.fill)
                            dst.border = _copy(src.border)
                            dst.alignment = _copy(src.alignment)
                            dst.number_format = src.number_format

            # Write expense data (values only; merges added in final pass below)
            row = tpl_f
            seq = 1
            for partida, group_items in _group_by_partida(items).items():
                for item in group_items:
                    _write_single_row(ws, row, seq, item, perceptor_default)
                    row += 1
                    seq += 1

            # Clear placeholder values from unused template data rows
            for r in range(tpl_f + len(items), tpl_l + 1):
                for c in range(2, 14):
                    ws.cell(r, c).value = None

        # ── Re-apply all structural template merges at their final positions ─
        for r1, c1, r2, c2 in template_merges:
            if (r1, c1, r2, c2) in data_area_merges:
                continue  # replaced by per-partida merges below
            ws.merge_cells(
                start_row=actual_row(r1), start_column=c1,
                end_row=actual_row(r2), end_column=c2,
            )

        # ── Apply per-partida-group merges and write partida names/budgets ───
        for sec_key, tpl_f, tpl_l, tpl_t in self._SECTION_DEFS:
            items = expenses_by_section.get(sec_key, [])
            af = actual_first(tpl_f)
            row = af
            for partida, group_items in _group_by_partida(items).items():
                g_start = row
                row += len(group_items)
                g_end = row - 1
                ws.cell(g_start, 2).value = partida  # B anchor
                if g_end > g_start:
                    ws.merge_cells(
                        start_row=g_start, start_column=2,
                        end_row=g_end, end_column=3,
                    )
                    for c in (11, 12, 13):  # K, L, M
                        ws.merge_cells(
                            start_row=g_start, start_column=c,
                            end_row=g_end, end_column=c,
                        )

        # ── Write formulas (after all row insertions, using final positions) ──
        for sec_key, tpl_f, tpl_l, tpl_t in self._SECTION_DEFS:
            items = expenses_by_section.get(sec_key, [])
            n = len(items)
            af = actual_first(tpl_f)
            act_total = actual_row(tpl_t)

            if n > 0:
                al = af + n - 1
                ws.cell(act_total, 10).value = f"=SUM(J{af}:J{al})"
                ws.cell(act_total, 11).value = f"=SUM(J{af}:J{al})"
            else:
                ws.cell(act_total, 10).value = 0
                ws.cell(act_total, 11).value = 0

            # Per-partida K formula (partida total) and L/M (presupuesto/desvío)
            row = af
            for partida, group_items in _group_by_partida(items).items():
                g_start = row
                g_end = row + len(group_items) - 1
                ws[f"K{g_start}"] = f"=SUM(J{g_start}:J{g_end})"
                budget = self._budget_for_partida(sec_key[0], partida)
                if budget is not None:
                    ws[f"L{g_start}"] = budget
                    ws[f"M{g_start}"] = f"=L{g_start}-K{g_start}"
                row = g_end + 1

        # Table 1 and Table 2 grand totals
        t1_total_rows = [actual_row(tpl_t) for sk, _, _, tpl_t in self._SECTION_DEFS if sk[0] == "AYUDA"]
        t2_total_rows = [actual_row(tpl_t) for sk, _, _, tpl_t in self._SECTION_DEFS if sk[0] == "APORTACION PROPIA"]
        t1_actual = actual_row(self._T1_TOTAL_ROW)
        t2_actual = actual_row(self._T2_TOTAL_ROW)
        ws.cell(t1_actual, 10).value = "=" + "+".join(f"J{r}" for r in t1_total_rows)
        ws.cell(t2_actual, 10).value = "=" + "+".join(f"J{r}" for r in t2_total_rows)

        # Summary section (resumen de gastos)
        m90 = actual_row(90)
        m91 = actual_row(91)
        m92 = actual_row(92)
        ws.cell(m90, 13).value = f"=J{t1_actual}"
        ws.cell(m91, 13).value = f"=J{t2_actual}"
        ws.cell(m92, 13).value = f"=SUM(M{m90}:M{m91})"

        self._write_traceability_sheet(wb)
        self._write_relation_eda_sheet(wb)
        output.parent.mkdir(parents=True, exist_ok=True)
        wb.save(output)

    def _classify_by_section(self) -> dict[tuple[str, str], list[RelationExpense]]:
        """Group expenses into the 8 template sections, adding ORDINARIO classification."""
        result: dict[tuple[str, str], list[RelationExpense]] = {}
        for expense in self._relation_expenses:
            tipo = expense.tipo_gasto
            cargo = expense.cargo
            if (
                tipo == "EXTERNO"
                and cargo == "APORTACION PROPIA"
                and normalizar_texto(expense.partida) in self._ORDINARIO_PARTIDAS
            ):
                tipo = "ORDINARIO"
            result.setdefault((cargo, tipo), []).append(expense)
        return result

    def _write_traceability_sheet(self, workbook: Any) -> None:
        name = "TRAZABILIDAD_PIPELINE"
        if name in workbook.sheetnames:
            del workbook[name]
        sheet = workbook.create_sheet(name)
        sheet.append(
            (
                "tipo_gasto",
                "gasto_original",
                "gasto_normalizado",
                "cargo",
                "partida",
                "concepto",
                "justificante",
                "fecha_factura",
                "importe",
            )
        )
        for expense in self._relation_expenses:
            sheet.append(
                (
                    expense.tipo_gasto,
                    expense.gasto_original,
                    expense.gasto_normalizado,
                    expense.cargo,
                    expense.partida,
                    expense.concepto,
                    expense.numero_factura,
                    expense.fecha_factura,
                    expense.importe,
                )
            )
        sheet.append(())
        sheet.append((
            "Nota",
            "Fuente: relacion_gastos.xlsx (Hoja 1), normalizacion del gasto y presupuesto autorizado PDF.",
        ))

    def _write_relation_eda_sheet(self, workbook: Any) -> None:
        name = "EDA_RELACION_GASTOS"
        if name in workbook.sheetnames:
            del workbook[name]
        sheet = workbook.create_sheet(name)
        sheet.append(("gasto_original", "gasto_normalizado", "frecuencia"))
        counter = Counter(
            (expense.gasto_original, expense.gasto_normalizado) for expense in self._relation_expenses
        )
        for (gasto_original, gasto_normalizado), frequency in sorted(
            counter.items(), key=lambda item: (normalizar_texto(item[0][1]), normalizar_texto(item[0][0]))
        ):
            sheet.append((gasto_original, gasto_normalizado, frequency))
        sheet.append(())
        sheet.append((
            "Nota",
            "La normalizacion consolida variantes del campo gasto para agrupar conceptos equivalentes.",
        ))



def _unmerge_data_rows(ws: Any, first_row: int, last_row: int) -> None:
    """Remove merged cell ranges that are entirely within [first_row, last_row] and not in col A."""
    to_unmerge = [
        str(mc)
        for mc in list(ws.merged_cells.ranges)
        if mc.min_row >= first_row and mc.max_row <= last_row and mc.min_col > 1
    ]
    for rng in to_unmerge:
        ws.unmerge_cells(rng)


def _group_by_partida(items: list[RelationExpense]) -> dict[str, list[RelationExpense]]:
    """Return expenses grouped by partida, sorted alphabetically by partida."""
    groups: dict[str, list[RelationExpense]] = {}
    for item in sorted(items, key=lambda x: normalizar_texto(x.partida or "")):
        groups.setdefault(item.partida or "(sin partida)", []).append(item)
    return groups


def _write_single_row(
    ws: Any,
    row: int,
    seq: int,
    expense: RelationExpense,
    perceptor_default: str = "",
) -> None:
    """Write one expense into a single worksheet row with the correct column mapping.

    Column layout (A=1):
      B-C (2-3): partida — written by caller after grouping
      D   (4):   concepto de gasto
      E   (5):   mes y año (nóminas/autónoma) | Nº de factura (proveedores/ordinarios)
      G   (7):   nombre perceptor (nóminas/autónoma) | emisor (proveedores/ordinarios)
      H   (8):   fecha de emisión
      I   (9):   fecha de pago
      J   (10):  importe ejecutado por concepto (€)
      K   (11):  importe ejecutado por partida (€) — formula written after grouping
      L   (12):  importe presupuestado — written after grouping
      M   (13):  desvío — formula written after grouping
    """
    ws.cell(row, 4).value = expense.concepto or ""
    if expense.tipo_gasto in {"NOMINA", "AUTONOMA"}:
        ws.cell(row, 5).value = expense.mes_nomina or ""
        ws.cell(row, 7).value = expense.nombre_perceptor or perceptor_default
    else:
        ws.cell(row, 5).value = expense.numero_factura or seq
        ws.cell(row, 7).value = expense.emisor or ""
    ws.cell(row, 8).value = expense.fecha_factura or ""
    ws.cell(row, 9).value = expense.fecha_pago or ""
    ws.cell(row, 10).value = float(expense.importe)


def _split_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [item for item in str(value or "").split("|") if item]


def _resolve_amount(path: str, amounts: list[float], warnings: list[str]) -> float | None:
    if not amounts:
        warnings.append(f"Gasto no cargado por importe ausente: {path}")
        return None
    unique = sorted(set(amounts))
    if len(unique) == 1:
        return unique[0]
    selected = max(unique)
    warnings.append(
        f"Gasto con importes múltiples; se usa el mayor ({selected:.2f}): {path}"
    )
    return selected


def _normalize_expense_type(value: str) -> str:
    key = normalizar_texto(value)
    if "autonom" in key:
        return "AUTONOMA"
    if "externo" in key:
        return "EXTERNO"
    return "NOMINA"


def normalizar_gasto_label(value: str) -> str:
    key = normalizar_texto(value)
    if not key:
        return ""
    if any(
        token in key
        for token in (
            "proveedores externos",
            "proveedor externo",
            "externos",
            "externo",
        )
    ):
        return "externos"
    if any(
        token in key
        for token in (
            "trabajos realizados por el autonomo",
            "trabajo autonomo",
            "autonoma",
            "autónoma",
            "autonomo",
            "autónomo",
            "autónomos",
            "autonomos",
        )
    ):
        return "autónoma"
    if any(token in key for token in ("nomina", "nómina", "personal", "salarios", "sueldos")):
        return "nómina"
    return key


def _normalize_charge(value: str) -> str:
    key = normalizar_texto(value)
    if "aportacion propia" in key or "otros gastos" in key:
        return "APORTACION PROPIA"
    if "ayuda" in key:
        return "AYUDA"
    return value.strip().upper()


def _cargo_from_budget_page(normalized_text: str) -> str:
    if "2 3 resumen de gastos" in normalized_text:
        return ""
    if "2 2" in normalized_text and "ingresos ajenos" in normalized_text:
        return "APORTACION PROPIA"
    if "otros gastos del proyecto" in normalized_text:
        return "APORTACION PROPIA"
    if "maximo 20 de la ayuda" in normalized_text:
        return "AYUDA"
    if "2 1" in normalized_text and "financiados con la ayuda" in normalized_text:
        return "AYUDA"
    if "gastos financiados con carga a la ayuda" in normalized_text:
        return "AYUDA"
    if "total trabajos realizados por el autonomo 1 800" in normalized_text:
        return "AYUDA"
    if "stand mercartes" in normalized_text:
        return "AYUDA"
    if (
        "desglosar conceptos de gasto" in normalized_text
        and "trabajos realizados por el autonomo" in normalized_text
        and "gastos de personal" in normalized_text
    ):
        return "AYUDA"
    return ""


def _clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return "" if text.casefold() == "nan" else text


def _format_relation_date(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
        day, month, year = text.split("/")
        if 1900 <= int(year) <= 2100:
            return f"{year}-{month}-{day}"
        return ""
    if isinstance(value, object) and hasattr(value, "strftime"):
        try:
            return value.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return text


def _date_cell_value(value: str) -> str:
    if not value:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    return value


def _month_year_placeholder(*values: str) -> str:
    for value in values:
        if not value:
            continue
        match = re.search(r"(\d{4})-(\d{2})", value)
        if match:
            return f"{match.group(2)}/{match.group(1)}"
        match = re.search(r"(\d{2})/(\d{2})/(\d{4})", value)
        if match:
            return f"{match.group(2)}/{match.group(3)}"
    return ""


def _parse_relation_amount(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = _clean_text(value).replace("€", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return parse_amount(text)


def _looks_like_date_token(value: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?$", value))


def _join_unique(values: list[str], limit: int) -> str:
    unique: list[str] = []
    for value in values:
        item = _clean_text(value)
        if item and item not in unique:
            unique.append(item)
    return " | ".join(unique[:limit])


def _merge_overflow_items(items: list[dict[str, Any]], capacity: int) -> list[dict[str, Any]]:
    if len(items) <= capacity:
        return items
    head = items[: capacity - 1]
    tail = items[capacity - 1:]
    merged = {
        "cargo": tail[0]["cargo"],
        "tipo_gasto": tail[0]["tipo_gasto"],
        "partida": "RESTO DE PARTIDAS",
        "conceptos": [concept for item in tail for concept in item["conceptos"]],
        "justificantes": [code for item in tail for code in item["justificantes"]],
        "fechas_factura": [date for item in tail for date in item["fechas_factura"]],
        "importe": sum(float(item["importe"]) for item in tail),
    }
    return head + [merged]


def _token_overlap(left: str, right: str) -> bool:
    stopwords = {"de", "la", "el", "y"}
    left_tokens = {token for token in left.split() if token not in stopwords}
    right_tokens = {token for token in right.split() if token not in stopwords}
    if not left_tokens or not right_tokens:
        return False
    return len(left_tokens & right_tokens) >= max(1, min(len(left_tokens), len(right_tokens)) - 1)
