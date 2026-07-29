from pathlib import Path
import sys

import yaml


def cargar_configuracion(ruta_config: Path) -> dict:
    """Carga y valida inicialmente el archivo de configuración YAML."""
    if not ruta_config.exists():
        raise FileNotFoundError(
            f"No se ha encontrado el archivo de configuración: {ruta_config}"
        )

    with ruta_config.open("r", encoding="utf-8") as archivo:
        configuracion = yaml.safe_load(archivo)

    if not isinstance(configuracion, dict):
        raise ValueError("La configuración YAML no contiene una estructura válida.")

    campos_obligatorios = [
        "proyecto",
        "subvencion",
        "fechas",
        "rutas_entrada",
        "rutas_salida",
    ]

    campos_faltantes = [
        campo for campo in campos_obligatorios if campo not in configuracion
    ]

    if campos_faltantes:
        raise ValueError(
            "Faltan secciones obligatorias en proyecto.yaml: "
            + ", ".join(campos_faltantes)
        )

    return configuracion


def main() -> int:
    raiz_repositorio = Path(__file__).resolve().parent.parent
    ruta_config = raiz_repositorio / "pipeline" / "config" / "proyecto.yaml"

    try:
        config = cargar_configuracion(ruta_config)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    proyecto = config["proyecto"]
    subvencion = config["subvencion"]
    fechas = config["fechas"]

    print("Configuración cargada correctamente")
    print(f"Proyecto: {proyecto['nombre']}")
    print(f"Expediente: {proyecto['expediente']}")
    print(f"Importe concedido: {subvencion['importe_concedido']:.2f} €")
    print(
        "Periodo de ejecución: "
        f"{fechas['inicio_ejecucion']} — {fechas['fin_ejecucion']}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())