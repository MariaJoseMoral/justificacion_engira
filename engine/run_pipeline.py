from pathlib import Path
import sys
import csv
import json

import yaml

from src.inventario import buscar_documentos, generar_inventario_csv, generar_informe_markdown
from src.entidades import enriquecer_con_entidades_y_relaciones
from src.validacion import (
    ValidadorIncidencias,
    generar_reporte_incidencias,
    validar_plan_y_evidencias,
)
from src.plan import parse_approved_plan
from src.evidencias import aplicar_vinculos_al_inventario, vincular_evidencias
from src.economica import AdaptadorMemoriaEconomica, extraer_gastos_validados
from src.memoria_actividades import GeneradorMemoriaActividades
from src.tabla_incidencias import generar_tabla_incidencias
from src.relacion_gastos import generar_relacion_gastos


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
        "datos",
        "plan_aprobado",
        "plantillas",
    ]

    campos_faltantes = [
        campo for campo in campos_obligatorios if campo not in configuracion
    ]

    if campos_faltantes:
        raise ValueError(
            "Faltan secciones obligatorias en proyecto.yaml: "
            + ", ".join(campos_faltantes)
        )

    # All relative paths are deliberately relative to engine/, not to the caller's CWD.
    configuracion["_base_dir"] = ruta_config.parent.parent.resolve()
    return configuracion


def resolver_ruta(config: dict, value: str) -> Path:
    """Resolve configured paths consistently when invoked from any directory."""
    ruta = Path(value)
    return (ruta if ruta.is_absolute() else Path(config["_base_dir"]) / ruta).resolve()


def ruta_plantilla(config: dict, tipo: str, data_root: Path) -> Path:
    definicion = config["plantillas"][tipo]
    carpeta = config["rutas_entrada"][definicion["carpeta"]]
    return data_root / carpeta / definicion["archivo"]


def main() -> int:
    raiz_repositorio = Path(__file__).resolve().parent
    ruta_config = raiz_repositorio / "config" / "proyecto.yaml"

    try:
        config = cargar_configuracion(ruta_config)
        
        ruta_base = resolver_ruta(config, config["datos"]["raiz"])
        config["_data_root"] = ruta_base
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
            print(f"- {documento['ruta'].relative_to(ruta_base)}")
    
    # Generar inventario CSV e informe markdown
    try:
        ruta_salida_csv = resolver_ruta(config, config["rutas_salida"]["inventario"])
        ruta_salida_informe = resolver_ruta(config, config["rutas_salida"]["informe"])
        
        print("\n📊 Extrayendo metadatos de documentos...")
        inventario_enriquecido = generar_inventario_csv(
            documentos, ruta_salida_csv, ruta_base, config, con_metadatos=True
        )
        print(f"✓ Inventario enriquecido generado: {ruta_salida_csv}")

        print("\n🗺️  Interpretando el cronograma aprobado...")
        plan = parse_approved_plan(config, ruta_base)
        ruta_plan = resolver_ruta(config, config["rutas_salida"]["plan_canonico"])
        ruta_plan.parent.mkdir(parents=True, exist_ok=True)
        ruta_plan.write_text(
            json.dumps(plan.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        links = vincular_evidencias(
            plan, inventario_enriquecido, config.get("evidencias", {}).get("areas")
        )
        aplicar_vinculos_al_inventario(inventario_enriquecido, links)
        _serializar_campos_multivalor(inventario_enriquecido)
        _guardar_inventario_vinculado(ruta_salida_csv, inventario_enriquecido)
        ruta_vinculos = resolver_ruta(config, config["rutas_salida"]["vinculos_evidencias"])
        _guardar_vinculos(ruta_vinculos, links)
        print(f"✓ {len(plan.actions)} acciones aprobadas y {len(links)} vínculos evaluados")

        gastos_validados, avisos_economicos = extraer_gastos_validados(
            inventario_enriquecido, plan, links
        )
        ruta_relacion_gastos = resolver_ruta(
            config, config["rutas_salida"]["relacion_gastos"]
        )
        relacion_gastos = generar_relacion_gastos(
            inventario_enriquecido,
            plan,
            str(ruta_relacion_gastos),
            str(resolver_ruta(
                config, config["rutas_salida"]["extraccion_facturas_campos"]
            )),
            str(resolver_ruta(
                config, config["rutas_salida"]["revision_extraccion_facturas"]
            )),
            config.get("extraccion_facturas"),
        )
        print(f"✓ Relación de gastos: {len(relacion_gastos)} filas")
        
        # Fase 5: Extracción de entidades y Fase 6: Cruce documental
        print("\n🔍 Fase 5: Extrayendo entidades y relaciones...")
        entidades, relaciones = enriquecer_con_entidades_y_relaciones(inventario_enriquecido)
        resumen = entidades.get('resumen', {})
        print(f"✓ {resumen.get('total_nifs_cifs', 0)} NIFs/CIFs identificados")
        print(f"✓ {len(relaciones)} relaciones documentales detectadas")
        
        # Fase 7: Validación e incidencias
        print("\n⚠️  Fase 7: Detectando incidencias...")
        validador = ValidadorIncidencias(inventario_enriquecido, relaciones, entidades, config)
        incidencias = validador.validar() + validar_plan_y_evidencias(
            plan, links, gastos_validados, config
        )
        incidencias.extend(
            {
                "tipo": "gasto_no_cargado_automaticamente",
                "severidad": "media",
                "descripcion": aviso,
                "recomendacion": "Revisar importe, factura y vínculo con la acción aprobada.",
            }
            for aviso in avisos_economicos
        )
        print(f"✓ {len(incidencias)} incidencias detectadas")
        
        # Guardar reporte de incidencias
        reporte_inc = generar_reporte_incidencias(incidencias)
        ruta_incidencias = resolver_ruta(config, config["rutas_salida"]["incidencias"])
        with open(ruta_incidencias, "w", encoding="utf-8") as f:
            f.write(reporte_inc)
        print(f"✓ Reporte de incidencias: {ruta_incidencias}")
        generar_tabla_incidencias(
            incidencias,
            inventario_enriquecido,
            resolver_ruta(config, config["rutas_salida"]["tabla_incidencias_xlsx"]),
            resolver_ruta(config, config["rutas_salida"]["tabla_incidencias_csv"]),
        )
        print("✓ Tabla de incidencias con enlaces generada")
        
        print("\n📝 Generando los modelos normalizados...")
        plantilla_actividades = ruta_plantilla(config, "actividades", ruta_base)
        ruta_memoria_actividades = resolver_ruta(
            config, config["rutas_salida"]["memoria_actividades"]
        )
        generador_actividades = GeneradorMemoriaActividades(
            config, plan, links, gastos_validados
        )
        generador_actividades.generar(plantilla_actividades, ruta_memoria_actividades)
        print(f"✓ Memoria de actividades: {ruta_memoria_actividades}")
        ruta_economica = resolver_ruta(config, config["rutas_salida"]["memoria_economica"])
        AdaptadorMemoriaEconomica(config, plan, gastos_validados).generar(
            ruta_plantilla(config, "economica", ruta_base), ruta_economica
        )
        print(f"✓ Memoria económica: {ruta_economica}")
        print("✓ EDA relación de gastos: hoja EDA_RELACION_GASTOS incluida en el Excel generado")
        
        generar_informe_markdown(documentos, ruta_salida_informe, config, ruta_base)
        print(f"✓ Informe Markdown: {ruta_salida_informe}")
        
        # Resumen final
        print("\n" + "="*80)
        print("PIPELINE COMPLETADO EXITOSAMENTE")
        print("="*80)
        print(f"\n✓ Documentos procesados: {len(documentos)}")
        print(f"✓ Fases completadas: inventario → plan → vínculos → validación → modelos")
        print(f"\nArchivos generados:")
        print(f"  1. 01_inventario/inventario_documental.csv")
        print(f"  2. 01_inventario/informe_inventario.md")
        print(f"  3. 02_plan_y_evidencias/plan_canonico.json")
        print(f"  4. 02_plan_y_evidencias/vinculos_evidencias.csv")
        print(f"  5. 03_economica/relacion_facturas_gastos.csv")
        print(f"  6. 03_economica/extraccion_facturas_campos.csv")
        print(f"  7. 03_economica/revision_extraccion_facturas.csv")
        print(f"  8. 04_incidencias/reporte_incidencias.txt")
        print(f"  9. 05_modelos_normalizados/memoria_de_actividades.docx")
        print(f" 10. 05_modelos_normalizados/memoria_economica.xlsx")
        print(f"\nUbicación: {raiz_repositorio / 'outputs'}/")
        print("="*80 + "\n")
    
    except Exception as error:
        print(f"ERROR al generar archivos de salida: {error}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


def _guardar_vinculos(ruta: Path, links: list) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(
            archivo,
            fieldnames=("action_id", "document_path", "confidence", "review_state", "matched_terms"),
        )
        escritor.writeheader()
        escritor.writerows(link.as_dict() for link in links)


def _guardar_inventario_vinculado(ruta: Path, inventory: list[dict]) -> None:
    """Persist fields added after initial metadata extraction without changing its schema."""
    if not inventory:
        return
    fields = (
        "area", "ruta_relativa", "nombre", "extension", "tamaño", "categoria",
        "fecha_modificacion", "num_paginas", "fechas_detectadas", "importes_detectados",
        "nifs_detectados", "urls_detectadas", "idioma", "texto_preview",
        "tipo_documental", "confianza_tipo", "categorias_funcionales", "es_evidencia",
        "es_gasto", "es_pago", "actividad_asociada", "accion_aprobada_id",
        "confianza_accion", "revision_accion", "ruta_absoluta",
    )
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        writer = csv.DictWriter(
            archivo, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for record in inventory:
            serialized = {
                key: "|".join(value) if isinstance(value, list) else value
                for key, value in record.items()
            }
            writer.writerow(serialized)


def _serializar_campos_multivalor(inventory: list[dict]) -> None:
    """Keep the pipe-delimited record contract consumed by legacy validators."""
    fields = ("fechas_detectadas", "importes_detectados", "nifs_detectados", "urls_detectadas")
    for record in inventory:
        for field in fields:
            if isinstance(record.get(field), list):
                record[field] = "|".join(str(value) for value in record[field])


if __name__ == "__main__":
    raise SystemExit(main())