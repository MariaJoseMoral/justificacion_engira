from pathlib import Path
import sys

import yaml

from src.inventario import buscar_documentos, generar_inventario_csv, generar_informe_markdown


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
    raiz_repositorio = Path(__file__).resolve().parent
    ruta_config = raiz_repositorio / "config" / "proyecto.yaml"

    try:
        config = cargar_configuracion(ruta_config)
        
        documentos = buscar_documentos(config)

    except (
        FileNotFoundError,
        NotADirectoryError,
        ValueError,
        KeyError,
        TypeError,
        yaml.YAMLError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    proyecto = config["proyecto"]
    subvencion = config["subvencion"]
    fechas = config["fechas"]
    ruta_base = Path(config["repositorio"]["raiz"]).resolve()

    print("Configuración cargada correctamente")
    print(f"Proyecto: {proyecto['nombre']}")
    print(f"Expediente: {proyecto['expediente']}")
    print(f"Importe concedido: {subvencion['importe_concedido']:.2f} €")
    print(
        "Periodo de ejecución: "
        f"{fechas['inicio_ejecucion']} — {fechas['fin_ejecucion']}"
    )

    print()
    print(f"Ruta base: {ruta_base}")
    print(f"Documentos encontrados: {len(documentos)}")

    if documentos:
        print()
        print("Primeros documentos encontrados:")

        for documento in documentos[:5]:
            print(f"- {documento.relative_to(ruta_base)}")
    
    # Generar inventario CSV e informe markdown
    try:
        ruta_salida_csv = raiz_repositorio / config["rutas_salida"]["inventario"]
        ruta_salida_informe = raiz_repositorio / config["rutas_salida"]["informe"]
        
        print("\n📊 Extrayendo metadatos de documentos...")
        generar_inventario_csv(documentos, ruta_salida_csv, ruta_base, config, con_metadatos=True)
        print(f"✓ Inventario enriquecido generado: {ruta_salida_csv}")
        
        generar_informe_markdown(documentos, ruta_salida_informe, config, ruta_base)
        print(f"✓ Informe Markdown generado: {ruta_salida_informe}")
    
    except Exception as error:
        print(f"ERROR al generar archivos de salida: {error}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())