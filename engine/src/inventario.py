from pathlib import Path
import csv
import json
from datetime import datetime

from src.extractores import extraer_metadatos, detectar_idioma
from src.clasificadores import enriquecer_con_clasificaciones


def buscar_documentos(config: dict) -> list[Path]:
    """
    Recorre una carpeta de forma recursiva y devuelve todos los archivos encontrados.

    Args:
        ruta_documentos: Ruta de la carpeta que contiene la documentación.

    Returns:
        Lista de objetos Path correspondientes a los archivos encontrados.
    """
    if "repositorio" not in config:
        raise KeyError("No existe la sección 'repositorio' en proyecto.yaml")

    ruta = Path(config["repositorio"]["raiz"]).resolve()

    if not ruta.exists():
        raise FileNotFoundError(
            f"La carpeta de datos no existe: {ruta}"
        )

    if not ruta.is_dir():
        raise NotADirectoryError(
            f"La ruta indicada no es una carpeta: {ruta}"
        )

    documentos = []

    for carpeta in config["rutas_entrada"].values():
        ruta_carpeta = ruta / carpeta

        if not ruta_carpeta.exists():
            continue

        documentos.extend(
            archivo
            for archivo in ruta_carpeta.rglob("*")
            if archivo.is_file()
        )

    return documentos


def enriquecer_inventario(documentos: list[Path], ruta_base: Path, config: dict, verbose: bool = False) -> list[dict]:
    """Enriquece el inventario con metadatos y clasificaciones."""
    inventario = []
    
    for i, doc in enumerate(sorted(documentos), 1):
        extension = doc.suffix.lower()
        categoria = _categorizar_archivo(extension)
        ruta_relativa = doc.relative_to(ruta_base)
        
        if verbose:
            print(f"  [{i}/{len(documentos)}] Procesando: {ruta_relativa}", end="\r")
        
        # Extraer metadatos
        metadatos = extraer_metadatos(doc)
        
        # Detectar idioma si hay texto
        if metadatos.get("texto"):
            metadatos["idioma"] = detectar_idioma(metadatos["texto"])
            # Limitar longitud del texto extraído
            if len(metadatos["texto"]) > 5000:
                metadatos["texto_preview"] = metadatos["texto"][:5000] + "..."
                del metadatos["texto"]
        
        # Preparar registro
        registro = {
            "ruta_relativa": str(ruta_relativa),
            "nombre": doc.name,
            "extension": extension,
            "tamaño": metadatos.get("tamaño", 0),
            "categoria": categoria,
            "fecha_modificacion": metadatos.get("fecha_modificacion"),
            "ruta_absoluta": str(doc),
            **metadatos
        }
        
        inventario.append(registro)
    
    if verbose:
        print("\n✓ Metadatos extraídos")
        print(f"  Clasificando {len(inventario)} documentos...")
    
    # Agregar clasificaciones (Fase 3 y 4)
    inventario = enriquecer_con_clasificaciones(inventario, config)
    
    if verbose:
        print("✓ Clasificaciones completadas\n")
    
    return inventario


def generar_inventario_csv(documentos: list[Path], ruta_salida: Path, ruta_base: Path, config: dict, con_metadatos: bool = True) -> None:
    """Genera un CSV con el inventario de documentos (con o sin metadatos extraídos)."""
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    
    if con_metadatos:
        inventario = enriquecer_inventario(documentos, ruta_base, config, verbose=True)
        
        # Determinar todos los campos posibles
        fieldnames = [
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
            "tipo_documental",
            "confianza_tipo",
            "categorias_funcionales",
            "es_evidencia",
            "es_gasto",
            "es_pago",
            "actividad_asociada",
            "ruta_absoluta"
        ]
        
        with ruta_salida.open("w", newline="", encoding="utf-8") as archivo:
            writer = csv.DictWriter(
                archivo,
                fieldnames=fieldnames,
                extrasaction="ignore"  # Ignorar campos extras
            )
            writer.writeheader()
            
            for registro in inventario:
                # Convertir listas a strings
                registro["fechas_detectadas"] = "|".join(
                    str(f) for f in registro.get("fechas_detectadas", [])
                )
                registro["importes_detectados"] = "|".join(
                    str(i) for i in registro.get("importes_detectados", [])
                )
                registro["nifs_detectados"] = "|".join(
                    str(n) for n in registro.get("nifs_detectados", [])
                )
                registro["urls_detectadas"] = "|".join(
                    str(u) for u in registro.get("urls_detectadas", [])
                )
                
                # Limitar valores
                for key in ["num_paginas", "tamaño"]:
                    if key in registro and registro[key] is None:
                        registro[key] = ""
                
                writer.writerow(registro)
    else:
        # Modo simple sin metadatos
        with ruta_salida.open("w", newline="", encoding="utf-8") as archivo:
            writer = csv.writer(archivo)
            writer.writerow([
                "Ruta Relativa",
                "Nombre Archivo",
                "Extensión",
                "Tamaño (bytes)",
                "Categoría",
                "Fecha Modificación",
                "Ruta Absoluta"
            ])
            
            for doc in sorted(documentos):
                stat = doc.stat()
                ruta_relativa = doc.relative_to(ruta_base)
                extension = doc.suffix.lower()
                categoria = _categorizar_archivo(extension)
                fecha_mod = datetime.fromtimestamp(stat.st_mtime).isoformat()
                
                writer.writerow([
                    str(ruta_relativa),
                    doc.name,
                    extension,
                    stat.st_size,
                    categoria,
                    fecha_mod,
                    str(doc)
                ])


def _categorizar_archivo(extension: str) -> str:
    """Categoriza un archivo por su extensión."""
    categorias = {
        ".pdf": "documento",
        ".doc": "documento",
        ".docx": "documento",
        ".pages": "documento",
        ".xls": "hoja_calculo",
        ".xlsx": "hoja_calculo",
        ".xlsm": "hoja_calculo",
        ".csv": "hoja_calculo",
        ".ods": "hoja_calculo",
        ".jpg": "imagen",
        ".jpeg": "imagen",
        ".png": "imagen",
        ".gif": "imagen",
        ".webp": "imagen",
        ".mp4": "audiovisual",
        ".mov": "audiovisual",
        ".avi": "audiovisual",
        ".mkv": "audiovisual",
        ".m4v": "audiovisual",
        ".webm": "audiovisual",
        ".wav": "audiovisual",
        ".mp3": "audiovisual",
        ".aiff": "audiovisual",
        ".zip": "comprimido",
        ".rar": "comprimido",
        ".7z": "comprimido",
    }
    return categorias.get(extension, "otro")


def generar_informe_markdown(documentos: list[Path], ruta_salida: Path, config: dict, ruta_base: Path) -> None:
    """Genera un informe markdown con estadísticas de los documentos."""
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    
    # Agrupar documentos por categoría
    por_categoria = {}
    tamaño_total = 0
    
    for doc in documentos:
        extension = doc.suffix.lower()
        categoria = _categorizar_archivo(extension)
        
        if categoria not in por_categoria:
            por_categoria[categoria] = []
        
        stat = doc.stat()
        tamaño_total += stat.st_size
        por_categoria[categoria].append({
            "ruta": str(doc.relative_to(ruta_base)),
            "tamaño": stat.st_size
        })
    
    # Generar informe
    with ruta_salida.open("w", encoding="utf-8") as archivo:
        proyecto = config["proyecto"]
        subvencion = config["subvencion"]
        fechas = config["fechas"]
        
        archivo.write(f"# Informe de Inventario Documental\n\n")
        archivo.write(f"**Proyecto:** {proyecto['nombre']}\n\n")
        archivo.write(f"**Expediente:** {proyecto['expediente']}\n\n")
        archivo.write(f"**Organismo:** {subvencion['organismo']}\n\n")
        archivo.write(f"**Periodo de ejecución:** {fechas['inicio_ejecucion']} — {fechas['fin_ejecucion']}\n\n")
        
        archivo.write(f"## Resumen General\n\n")
        archivo.write(f"- **Total de documentos:** {len(documentos)}\n")
        archivo.write(f"- **Tamaño total:** {tamaño_total / (1024*1024):.2f} MB\n")
        archivo.write(f"- **Tamaño promedio por documento:** {(tamaño_total / len(documentos)) / 1024:.2f} KB\n")
        archivo.write(f"- **Fecha del informe:** {datetime.now().isoformat()}\n\n")
        
        archivo.write(f"## Documentos por Categoría\n\n")
        
        for categoria in sorted(por_categoria.keys()):
            docs = por_categoria[categoria]
            tamaño_cat = sum(d["tamaño"] for d in docs)
            archivo.write(f"### {categoria.upper()} ({len(docs)} documentos)\n\n")
            archivo.write(f"**Tamaño total:** {tamaño_cat / (1024*1024):.2f} MB\n\n")
            archivo.write(f"| Archivo | Tamaño (KB) |\n")
            archivo.write(f"|---------|-------------|\n")
            
            for doc in sorted(docs, key=lambda x: x["ruta"]):
                tamaño_kb = doc["tamaño"] / 1024
                archivo.write(f"| {doc['ruta']} | {tamaño_kb:.2f} |\n")
            
            archivo.write(f"\n")