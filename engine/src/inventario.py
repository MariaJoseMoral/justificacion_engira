from pathlib import Path


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

    ruta = Path(config["datos"]["raiz"]).resolve()

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