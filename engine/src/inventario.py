from pathlib import Path
import csv

from src.clasificadores import enriquecer_con_clasificaciones
from src.extractores import extraer_metadatos


def buscar_documentos(config: dict) -> list[dict]:
    """
    Recorre una carpeta de forma recursiva y devuelve todos los archivos encontrados.

    Args:
    config: Configuración del proyecto cargada desde proyecto.yaml.

    Returns:
        Lista de objetos Path correspondientes a los archivos encontrados.
    """

    if "datos" not in config:
        raise KeyError("No existe la sección 'datos' en proyecto.yaml")

    ruta = Path(config.get("_data_root", config["datos"]["raiz"])).resolve()

    if not ruta.exists():
        raise FileNotFoundError(
            f"La carpeta de datos no existe: {ruta}"
        )

    if not ruta.is_dir():
        raise NotADirectoryError(
            f"La ruta indicada no es una carpeta: {ruta}"
        )

    documentos = []

    for nombre_area, carpeta in config["rutas_entrada"].items():
        ruta_carpeta = ruta / carpeta

        if not ruta_carpeta.exists():
            continue

        for archivo in ruta_carpeta.rglob("*"):
            if archivo.is_file():
                documentos.append(
                    {
                        "area": nombre_area,
                        "ruta": archivo,
                    }
                )

    return documentos


def generar_inventario_csv(
    documentos: list[dict],
    ruta_salida: Path,
    ruta_base: Path,
    config: dict,
    con_metadatos: bool = True,
) -> list[dict]:
    """Genera el inventario enriquecido que consumen las fases posteriores."""
    registros = []
    for documento in documentos:
        ruta = documento["ruta"]
        if not config.get("opciones", {}).get("incluir_archivos_ocultos", False):
            if any(parte.startswith(".") for parte in ruta.relative_to(ruta_base).parts):
                continue

        registro = {
            "area": documento["area"],
            "ruta_relativa": str(ruta.relative_to(ruta_base)),
            "ruta_absoluta": str(ruta),
            "nombre": ruta.name,
            "extension": ruta.suffix.lower(),
            "tamaño": ruta.stat().st_size,
            "categoria": _categoria_archivo(ruta, config),
        }
        if con_metadatos:
            registro.update(extraer_metadatos(ruta))
            registro["texto_preview"] = _texto_preview(registro.get("texto"))
        registros.append(registro)

    enriquecer_con_clasificaciones(registros, config)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    campos = [
        "area",
        "ruta_relativa",
        "nombre",
        "extension",
        "tamaño",
        "categoria",
        "fecha_modificacion",
        "num_paginas",
        "fechas_detectadas",
        "importes_detectados",
        "nifs_detectados",
        "urls_detectadas",
        "idioma",
        "texto_preview",
        "tipo_documental",
        "confianza_tipo",
        "categorias_funcionales",
        "es_evidencia",
        "es_gasto",
        "es_pago",
        "actividad_asociada",
        "accion_aprobada_id",
        "confianza_accion",
        "revision_accion",
        "ruta_absoluta",
    ]
    with ruta_salida.open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(
            archivo,
            fieldnames=campos,
            extrasaction="ignore",
            lineterminator="\n",
        )
        escritor.writeheader()
        for registro in registros:
            escritor.writerow(_serializar_registro(registro, campos))
    return registros


def generar_informe_markdown(
    documentos: list[dict], ruta_salida: Path, config: dict, ruta_base: Path
) -> None:
    """Genera un informe breve del inventario físico por área documental."""
    por_area: dict[str, list[dict]] = {}
    for documento in documentos:
        por_area.setdefault(documento["area"], []).append(documento)

    proyecto = config["proyecto"]
    lineas = [
        "# Informe de Inventario Documental",
        "",
        f"**Proyecto:** {proyecto['nombre']}",
        f"**Expediente:** {proyecto['expediente']}",
        "",
        "## Documentos por área",
    ]
    for area, documentos_area in sorted(por_area.items()):
        lineas.extend(["", f"### {area} ({len(documentos_area)} documentos)"])
        for documento in documentos_area:
            lineas.append(f"- {documento['ruta'].relative_to(ruta_base)}")

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    ruta_salida.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def _categoria_archivo(ruta: Path, config: dict) -> str:
    for tipo, definicion in config.get("tipos_archivos", {}).items():
        if ruta.suffix.lower() in definicion.get("extensiones", []):
            return definicion.get("categoria", tipo)
    return "otro"


def _serializar_registro(registro: dict, campos: list[str]) -> dict:
    resultado = {}
    for campo in campos:
        valor = registro.get(campo, "")
        if isinstance(valor, list):
            valor = "|".join(str(elemento) for elemento in valor)
        resultado[campo] = valor
    return resultado


def _texto_preview(texto: object) -> str:
    """Conserva texto suficiente para sintetizar, sin convertir el CSV en un repositorio."""
    if not isinstance(texto, str):
        return ""
    lineas = [" ".join(linea.split()) for linea in texto.splitlines()]
    return "\n".join(linea for linea in lineas if linea)[:12000]