"""Tabla revisable de incidencias documentales."""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


def generar_tabla_incidencias(
    incidencias: Iterable[dict[str, Any]],
    inventario: Iterable[dict[str, Any]],
    salida_xlsx: Path,
    salida_csv: Path,
) -> None:
    """Genera tablas con IDs estables y enlaces locales a cada documento."""
    documentos_por_nombre: dict[str, list[dict[str, Any]]] = {}
    for documento in inventario:
        documentos_por_nombre.setdefault(str(documento.get("nombre", "")), []).append(documento)

    filas: list[dict[str, Any]] = []
    for numero, incidencia in enumerate(incidencias, start=1):
        referencias = [
            str(incidencia[campo])
            for campo in ("documento", "documento1", "documento2")
            if incidencia.get(campo)
        ] or [""]
        for referencia in dict.fromkeys(referencias):
            documento = _resolver_documento(referencia, documentos_por_nombre)
            ruta = str(documento.get("ruta_absoluta", "")) if documento else ""
            filas.append(
                {
                    "id_incidencia": f"INC-{numero:04d}",
                    "id_documento": _id_documento(ruta) if ruta else "",
                    "tipo_incidencia": incidencia.get("tipo", "desconocida"),
                    "severidad": incidencia.get("severidad", "sin clasificar"),
                    "documento": referencia or "No asociado a un documento",
                    "ruta_documento": ruta,
                    "accion_aprobada_id": documento.get("accion_aprobada_id", "") if documento else "",
                    "estado_vinculo": documento.get("revision_accion", "") if documento else "",
                    "descripcion": incidencia.get("descripcion", ""),
                    "recomendacion": incidencia.get("recomendacion", ""),
                }
            )

    tabla = pd.DataFrame(filas)
    if tabla.empty:
        tabla = pd.DataFrame(columns=_columnas())
    tabla["enlace_documento"] = np.where(
        tabla["ruta_documento"].astype(bool),
        tabla["ruta_documento"].map(lambda ruta: Path(ruta).resolve().as_uri()),
        "",
    )
    tabla["estado_revision"] = np.select(
        [
            tabla["ruta_documento"].eq(""),
            tabla["estado_vinculo"].eq("pendiente_revision"),
            tabla["estado_vinculo"].eq("sin_vincular"),
        ],
        ["documento_no_resuelto", "revisar_vinculo", "sin_vincular"],
        default="revisable",
    )
    tabla = tabla[_columnas()]
    salida_xlsx.parent.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(salida_csv, index=False, encoding="utf-8")
    with pd.ExcelWriter(salida_xlsx, engine="openpyxl") as escritor:
        tabla.to_excel(escritor, sheet_name="INCIDENCIAS", index=False)
        hoja = escritor.book["INCIDENCIAS"]
        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = hoja.dimensions
        for celda in hoja[1]:
            celda.font = celda.font.copy(bold=True)
        enlace_columna = _columnas().index("enlace_documento") + 1
        for fila in range(2, hoja.max_row + 1):
            celda = hoja.cell(fila, enlace_columna)
            if celda.value:
                celda.hyperlink = celda.value
                celda.style = "Hyperlink"
                celda.value = "Abrir documento"
        for columna in hoja.columns:
            letra = columna[0].column_letter
            hoja.column_dimensions[letra].width = min(
                55, max(12, max(len(str(celda.value or "")) for celda in columna) + 2)
            )


def _resolver_documento(
    nombre: str, documentos_por_nombre: dict[str, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    coincidencias = documentos_por_nombre.get(nombre, [])
    return coincidencias[0] if len(coincidencias) == 1 else None


def _id_documento(ruta: str) -> str:
    return f"DOC-{sha1(ruta.encode()).hexdigest()[:12].upper()}"


def _columnas() -> list[str]:
    return [
        "id_incidencia",
        "id_documento",
        "tipo_incidencia",
        "severidad",
        "documento",
        "enlace_documento",
        "ruta_documento",
        "accion_aprobada_id",
        "estado_vinculo",
        "estado_revision",
        "descripcion",
        "recomendacion",
    ]
