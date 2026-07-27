"""Módulo de extracción de metadatos de documentos."""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

from docx import Document as DocxDocument
from openpyxl import load_workbook
import pdfplumber


def extraer_metadatos(ruta_archivo: Path) -> Dict[str, Any]:
    """Extrae metadatos de un archivo según su tipo."""
    extension = ruta_archivo.suffix.lower()
    
    metadatos = {
        "ruta": str(ruta_archivo),
        "nombre": ruta_archivo.name,
        "extension": extension,
        "tamaño": ruta_archivo.stat().st_size,
        "fecha_modificacion": datetime.fromtimestamp(
            ruta_archivo.stat().st_mtime
        ).isoformat(),
        "texto": None,
        "num_paginas": None,
        "fechas_detectadas": [],
        "importes_detectados": [],
        "nifs_detectados": [],
        "personas_detectadas": [],
        "organismos_detectados": [],
        "urls_detectadas": [],
        "idioma": None,
    }
    
    if extension == ".pdf":
        metadatos.update(_extraer_pdf(ruta_archivo))
    elif extension in [".docx", ".doc"]:
        metadatos.update(_extraer_word(ruta_archivo))
    elif extension in [".xlsx", ".xls"]:
        metadatos.update(_extraer_excel(ruta_archivo))
    elif extension in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
        metadatos.update(_extraer_imagen(ruta_archivo))
    
    # Detectar patrones en texto
    if metadatos.get("texto"):
        metadatos["fechas_detectadas"] = _detectar_fechas(metadatos["texto"])
        metadatos["importes_detectados"] = _detectar_importes(metadatos["texto"])
        metadatos["nifs_detectados"] = _detectar_nifs(metadatos["texto"])
        metadatos["urls_detectadas"] = _detectar_urls(metadatos["texto"])
    
    return metadatos


def _extraer_pdf(ruta: Path) -> Dict[str, Any]:
    """Extrae texto y metadatos de PDF."""
    resultado = {
        "num_paginas": 0,
        "texto": "",
    }
    
    try:
        with pdfplumber.open(ruta) as pdf:
            resultado["num_paginas"] = len(pdf.pages)
            textos = []
            
            for page in pdf.pages:
                texto_pagina = page.extract_text() or ""
                textos.append(texto_pagina)
            
            resultado["texto"] = "\n".join(textos)
    except Exception as e:
        resultado["error"] = str(e)
    
    return resultado


def _extraer_word(ruta: Path) -> Dict[str, Any]:
    """Extrae texto y metadatos de archivos Word."""
    resultado = {
        "texto": "",
    }
    
    try:
        doc = DocxDocument(ruta)
        
        # Extraer párrafos
        parrafos = [p.text for p in doc.paragraphs if p.text.strip()]
        
        # Extraer de tablas
        tabla_textos = []
        for tabla in doc.tables:
            for fila in tabla.rows:
                fila_texto = " | ".join(
                    celda.text for celda in fila.cells
                )
                tabla_textos.append(fila_texto)
        
        resultado["texto"] = "\n".join(parrafos + tabla_textos)
        
        # Metadatos
        if doc.core_properties:
            props = doc.core_properties
            resultado["autor"] = props.author
            resultado["titulo"] = props.title
            resultado["fecha_creacion"] = props.created.isoformat() if props.created else None
    
    except Exception as e:
        resultado["error"] = str(e)
    
    return resultado


def _extraer_excel(ruta: Path) -> Dict[str, Any]:
    """Extrae texto y metadatos de archivos Excel."""
    resultado = {
        "texto": "",
        "hojas": [],
    }
    
    try:
        wb = load_workbook(ruta)
        textos = []
        
        for hoja_nombre in wb.sheetnames:
            ws = wb[hoja_nombre]
            resultado["hojas"].append(hoja_nombre)
            
            # Extraer valores de celdas
            for fila in ws.iter_rows(values_only=True):
                fila_texto = " | ".join(
                    str(celda) if celda is not None else ""
                    for celda in fila
                )
                if fila_texto.strip():
                    textos.append(fila_texto)
        
        resultado["texto"] = "\n".join(textos)
    
    except Exception as e:
        resultado["error"] = str(e)
    
    return resultado


def _extraer_imagen(ruta: Path) -> Dict[str, Any]:
    """Extrae metadatos de archivos de imagen."""
    resultado = {}
    
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        
        img = Image.open(ruta)
        resultado["dimensiones"] = img.size
        resultado["formato"] = img.format
        
        # Extraer EXIF si existe
        exif_data = img._getexif()
        if exif_data:
            exif_dict = {}
            for tag_id, valor in exif_data.items():
                tag_nombre = TAGS.get(tag_id, tag_id)
                exif_dict[tag_nombre] = str(valor)[:100]  # Limitar a 100 caracteres
            resultado["exif"] = exif_dict
    
    except Exception as e:
        resultado["error"] = str(e)
    
    return resultado


def _detectar_fechas(texto: str) -> List[str]:
    """Detecta fechas en formato ISO 8601 y otros formatos comunes."""
    fechas = set()
    
    # ISO 8601: YYYY-MM-DD
    iso_pattern = r"\d{4}-\d{2}-\d{2}"
    fechas.update(re.findall(iso_pattern, texto))
    
    # DD/MM/YYYY
    dmya_pattern = r"\d{1,2}/\d{1,2}/\d{4}"
    fechas.update(re.findall(dmya_pattern, texto))
    
    # DD-MM-YYYY
    dmyb_pattern = r"\d{1,2}-\d{1,2}-\d{4}"
    fechas.update(re.findall(dmyb_pattern, texto))
    
    return sorted(list(fechas))


def _detectar_importes(texto: str) -> List[str]:
    """Detecta importes monetarios."""
    importes = set()
    
    # EUR, €, €, formato: 1234.56, 1.234,56
    patterns = [
        r"€\s*[\d.,]+",  # € 1234.56
        r"EUR\s*[\d.,]+",  # EUR 1234.56
        r"[\d.,]+\s*€",  # 1234.56 €
        r"[\d.]+,\d{2}",  # 1234,56 (formato europeo)
        r"[\d,]+\.\d{2}",  # 1,234.56 (formato anglosajón)
    ]
    
    for pattern in patterns:
        importes.update(re.findall(pattern, texto))
    
    return sorted(list(importes))


def _detectar_nifs(texto: str) -> List[str]:
    """Detecta NIFs, CIFs y números de identidad españoles."""
    nifs = set()
    
    # NIF: 8 dígitos + letra
    nif_pattern = r"\b\d{8}[A-Za-z]\b"
    nifs.update(re.findall(nif_pattern, texto))
    
    # CIF: 1-2 caracteres + 7 dígitos + 1-2 caracteres
    cif_pattern = r"\b[A-ZJ-UVW]\d{7}[0-9A-J]\b"
    nifs.update(re.findall(cif_pattern, texto))
    
    return sorted(list(nifs))


def _detectar_urls(texto: str) -> List[str]:
    """Detecta URLs en el texto."""
    urls = set()
    
    url_pattern = r"https?://[^\s]+"
    urls.update(re.findall(url_pattern, texto))
    
    return sorted(list(urls))


def detectar_idioma(texto: str) -> Optional[str]:
    """Detecta el idioma probable del texto (básico)."""
    if not texto or len(texto) < 50:
        return None
    
    # Palabras comunes en español
    palabras_es = {
        "el", "la", "de", "y", "a", "en", "que", "es", "se", 
        "por", "con", "su", "para", "una", "del", "al", "un",
        "este", "proyecto", "actividad", "documento", "memoria"
    }
    
    # Palabras comunes en inglés
    palabras_en = {
        "the", "and", "to", "of", "a", "in", "is", "it", "for",
        "with", "be", "that", "on", "are", "this", "project", "activity"
    }
    
    palabras_texto = set(texto.lower().split())
    
    matches_es = len(palabras_texto & palabras_es)
    matches_en = len(palabras_texto & palabras_en)
    
    if matches_es > matches_en:
        return "es"
    elif matches_en > matches_es:
        return "en"
    
    return None
