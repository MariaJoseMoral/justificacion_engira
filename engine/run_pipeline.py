from pathlib import Path
import sys

import yaml

from src.inventario import buscar_documentos, generar_inventario_csv, generar_informe_markdown
from src.entidades import enriquecer_con_entidades_y_relaciones
from src.validacion import ValidadorIncidencias, generar_reporte_incidencias
from src.memoria import GeneradorMemoria


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
        
        # Recargar inventario enriquecido para las siguientes fases
        import csv
        inventario_enriquecido = []
        with open(ruta_salida_csv, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            inventario_enriquecido = list(reader)
        
        # Fase 5: Extracción de entidades y Fase 6: Cruce documental
        print("\n🔍 Fase 5: Extrayendo entidades y relaciones...")
        entidades, relaciones = enriquecer_con_entidades_y_relaciones(inventario_enriquecido)
        resumen = entidades.get('resumen', {})
        print(f"✓ {resumen.get('total_nifs_cifs', 0)} NIFs/CIFs identificados")
        print(f"✓ {len(relaciones)} relaciones documentales detectadas")
        
        # Fase 7: Validación e incidencias
        print("\n⚠️  Fase 7: Detectando incidencias...")
        validador = ValidadorIncidencias(inventario_enriquecido, relaciones, entidades)
        incidencias = validador.validar()
        print(f"✓ {len(incidencias)} incidencias detectadas")
        
        # Guardar reporte de incidencias
        reporte_inc = generar_reporte_incidencias(incidencias)
        ruta_incidencias = raiz_repositorio / "outputs/reporte_incidencias.txt"
        with open(ruta_incidencias, "w", encoding="utf-8") as f:
            f.write(reporte_inc)
        print(f"✓ Reporte de incidencias: {ruta_incidencias}")
        
        # Fase 8: Generación de memoria
        print("\n📝 Fase 8: Generando memoria justificativa...")
        generador = GeneradorMemoria(config, inventario_enriquecido, entidades, incidencias)
        memoria = generador.generar()
        
        ruta_memoria = raiz_repositorio / "outputs/MEMORIA_JUSTIFICATIVA.md"
        with open(ruta_memoria, "w", encoding="utf-8") as f:
            f.write(memoria)
        print(f"✓ Memoria justificativa: {ruta_memoria}")
        
        generar_informe_markdown(documentos, ruta_salida_informe, config, ruta_base)
        print(f"✓ Informe Markdown: {ruta_salida_informe}")
        
        # Resumen final
        print("\n" + "="*80)
        print("PIPELINE COMPLETADO EXITOSAMENTE")
        print("="*80)
        print(f"\n✓ Documentos procesados: {len(documentos)}")
        print(f"✓ Fases completadas: 1 → 8")
        print(f"\nArchivos generados:")
        print(f"  1. inventario_documental.csv")
        print(f"  2. informe_inventario.md")
        print(f"  3. reporte_clasificaciones.txt")
        print(f"  4. reporte_incidencias.txt")
        print(f"  5. MEMORIA_JUSTIFICATIVA.md")
        print(f"\nUbicación: {raiz_repositorio / 'outputs'}/")
        print("="*80 + "\n")
    
    except Exception as error:
        print(f"ERROR al generar archivos de salida: {error}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())