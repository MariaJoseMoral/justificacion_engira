"""Módulo de clasificación documental y funcional."""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class ClasificadorDocumental:
    """Clasifica documentos por tipo (factura, contrato, nómina, etc.)."""
    
    # Patrones para tipos documentales
    PATRONES_TIPOS = {
        "factura": {
            "nombres": r"factura|invoice|bill",
            "contenido": r"factura\s*(\d+|n[oº])|número de factura|importe total|cliente|conceptos",
            "puntaje": 10
        },
        "contrato": {
            "nombres": r"contrato|agreement|contract",
            "contenido": r"contrato\s*(de|entre)?|partes|objeto del contrato|condiciones|servicios|prestaciones",
            "puntaje": 10
        },
        "nomina": {
            "nombres": r"nomina|nómina|payroll|salary",
            "contenido": r"nómina|retribución|bruto|neto|cotizaciones|irpf|percepciones",
            "puntaje": 10
        },
        "transferencia": {
            "nombres": r"transferencia|payment|remittance|justificante",
            "contenido": r"transferencia|date|importe|beneficiario|cta|iban|bic|concepto del pago",
            "puntaje": 10
        },
        "memoria": {
            "nombres": r"memoria|report|informe",
            "contenido": r"memoria|resumen|actividades|resultados|conclusiones|objetivos|indicadores",
            "puntaje": 8
        },
        "fotografía": {
            "extensiones": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
            "puntaje": 15
        },
        "video": {
            "extensiones": [".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"],
            "puntaje": 15
        },
        "certificado": {
            "nombres": r"certificado|certificate|certif",
            "contenido": r"certificado|certif\s+(?:que|que se)|registro|expedido|válido",
            "puntaje": 9
        },
        "resolución": {
            "nombres": r"resoluci[oó]n|resolution|decreto",
            "contenido": r"resoluci[oó]n|considerando|acuerdo|expide|concede|autoriza|ordena",
            "puntaje": 9
        },
        "factura_gasto_viaje": {
            "nombres": r"viaje|travel|meal|accommodation|hotel|flight|transporte|dieta",
            "contenido": r"gasto de viaje|viaje|hotel|vuelo|transporte|manutención|alojamiento",
            "puntaje": 9
        },
        "recibo": {
            "nombres": r"recibo|receipt|comprobante",
            "contenido": r"recibo|he recibido|quantity|total amount",
            "puntaje": 8
        },
        "presupuesto": {
            "nombres": r"presupuesto|budget|estimate|quote",
            "contenido": r"presupuesto|total|partidas|concepto|importe|unidad",
            "puntaje": 8
        },
        "declaración": {
            "nombres": r"declaraci[oó]n|statement|declaration",
            "contenido": r"declaro|declaración|afirmo|certif|responsable",
            "puntaje": 8
        },
    }
    
    def __init__(self, config: Dict = None):
        """Inicializa el clasificador."""
        self.config = config or {}
    
    def clasificar(self, documento: Dict) -> Tuple[str, float]:
        """
        Clasifica un documento retornando (tipo, confianza).
        
        Args:
            documento: Dict con metadatos del documento
        
        Returns:
            Tupla (tipo_documento, confianza_0_a_1)
        """
        nombre = documento.get("nombre", "").lower()
        extension = documento.get("extension", "").lower()
        texto = (documento.get("texto") or documento.get("texto_preview") or "").lower()
        
        scores = {}
        
        for tipo, patrones in self.PATRONES_TIPOS.items():
            score = 0
            
            # Puntuación por extensión
            if "extensiones" in patrones:
                if extension in patrones["extensiones"]:
                    score += patrones.get("puntaje", 10)
                    scores[tipo] = score
                    continue
            
            # Puntuación por nombre
            if "nombres" in patrones:
                if re.search(patrones["nombres"], nombre):
                    score += patrones.get("puntaje", 10)
            
            # Puntuación por contenido
            if "contenido" in patrones and texto:
                matches = len(re.findall(patrones["contenido"], texto))
                score += min(matches * 2, patrones.get("puntaje", 10))
            
            if score > 0:
                scores[tipo] = score
        
        if not scores:
            return ("documento_generico", 0.3)
        
        # Obtener tipo con mayor puntuación
        tipo_max = max(scores, key=scores.get)
        puntaje_max = scores[tipo_max]
        confianza = min(puntaje_max / 15.0, 1.0)  # Normalizar a 0-1
        
        return (tipo_max, confianza)


class ClasificadorFuncional:
    """Relaciona documentos con actividades presupuestarias."""
    
    # Mapeo de tipos de documento a categorías funcionales
    MAPEO_FUNCIONAL = {
        "factura": ["economica", "gasto"],
        "transferencia": ["economica", "pago"],
        "nomina": ["laboral", "economica"],
        "factura_gasto_viaje": ["actividad", "economica"],
        "contrato": ["laboral", "administracion"],
        "certificado": ["evidencia", "actividad"],
        "fotografía": ["evidencia", "comunicacion"],
        "video": ["evidencia", "comunicacion"],
        "memoria": ["documentacion", "actividad"],
        "presupuesto": ["administracion", "economica"],
        "declaración": ["administracion", "documentacion"],
        "recibo": ["economica", "gasto"],
        "resolución": ["administracion"],
        "documento_generico": ["documentacion"],
    }
    
    # Relación con carpetas de entrada (rutas_entrada del config)
    MAPEO_CARPETAS = {
        "00_BASES_Y_RESOLUCION": ["administracion", "legal"],
        "01_PROYECTO_PRESENTADO": ["administracion", "planificacion"],
        "02_ACTIVIDADES_REALIZADAS": ["actividad", "evidencia"],
        "03_RESULTADOS_E_INDICADORES": ["resultado", "indicador"],
        "04_COMUNICACION_Y_DIFUSION": ["comunicacion", "evidencia"],
        "05_PARTICIPANTES_Y_COLABORADORES": ["laboral", "participantes"],
        "06_DESARROLLO_PLATAFORMA": ["actividad", "desarrollo"],
        "07_EVIDENCIAS": ["evidencia"],
        "08_JUSTIFICACION_ECONOMICA": ["economica", "gasto", "justificacion"],
        "09_DESVIACIONES_Y_CAMBIOS": ["administracion", "cambios"],
        "10_MEMORIA_FINAL": ["documentacion", "memoria"],
    }
    
    def __init__(self, config: Dict):
        """Inicializa el clasificador funcional."""
        self.config = config
    
    def clasificar(self, documento: Dict, tipo_documental: str) -> Dict[str, any]:
        """
        Clasifica funcionalmente un documento.
        
        Args:
            documento: Dict con metadatos
            tipo_documental: Tipo de documento (de clasificación documental)
        
        Returns:
            Dict con clasificación funcional
        """
        resultado = {
            "tipo_documental": tipo_documental,
            "categorias": [],
            "carpeta_origen": self._extraer_carpeta(documento),
            "actividad": None,
            "es_evidencia": False,
            "es_gasto": False,
            "es_pago": False,
        }
        
        # Categorías por tipo de documento
        categorias = self.MAPEO_FUNCIONAL.get(tipo_documental, ["documentacion"])
        resultado["categorias"].extend(categorias)
        
        # Categorías por carpeta de origen
        ruta = documento.get("ruta_relativa", "")
        for carpeta, cats in self.MAPEO_CARPETAS.items():
            if carpeta in ruta:
                resultado["categorias"].extend(cats)
                break
        
        # Eliminar duplicados
        resultado["categorias"] = sorted(list(set(resultado["categorias"])))
        
        # Detectar tipos especiales
        resultado["es_evidencia"] = "evidencia" in resultado["categorias"]
        resultado["es_gasto"] = "gasto" in resultado["categorias"] or "economica" in resultado["categorias"]
        resultado["es_pago"] = "pago" in resultado["categorias"]
        
        # Detectar actividad asociada
        resultado["actividad"] = self._detectar_actividad(documento)
        
        return resultado
    
    def _extraer_carpeta(self, documento: Dict) -> Optional[str]:
        """Extrae la carpeta de origen del documento."""
        ruta = documento.get("ruta_relativa", "")
        
        for carpeta in self.MAPEO_CARPETAS.keys():
            if ruta.startswith(carpeta):
                return carpeta
        
        return None
    
    def _detectar_actividad(self, documento: Dict) -> Optional[str]:
        """Detecta la actividad asociada al documento."""
        nombre = documento.get("nombre", "").lower()
        ruta = documento.get("ruta_relativa", "").lower()
        
        # Project-specific terms belong in configuration, never in the engine.
        actividades = self.config.get("clasificacion", {}).get("actividades", {})
        
        for actividad, patron in actividades.items():
            if re.search(patron, nombre) or re.search(patron, ruta):
                return actividad
        
        return None


def enriquecer_con_clasificaciones(inventario: List[Dict], config: Dict) -> List[Dict]:
    """
    Enriquece el inventario con clasificaciones documental y funcional.
    
    Args:
        inventario: Lista de documentos con metadatos
        config: Configuración del proyecto
    
    Returns:
        Inventario enriquecido con clasificaciones
    """
    clasificador_doc = ClasificadorDocumental(config)
    clasificador_fun = ClasificadorFuncional(config)
    
    for doc in inventario:
        # Clasificación documental
        tipo_doc, confianza = clasificador_doc.clasificar(doc)
        doc["tipo_documental"] = tipo_doc
        doc["confianza_tipo"] = round(confianza, 3)
        
        # Clasificación funcional
        clasificacion_fun = clasificador_fun.clasificar(doc, tipo_doc)
        doc["categorias_funcionales"] = "|".join(clasificacion_fun["categorias"])
        doc["es_evidencia"] = clasificacion_fun["es_evidencia"]
        doc["es_gasto"] = clasificacion_fun["es_gasto"]
        doc["es_pago"] = clasificacion_fun["es_pago"]
        doc["actividad_asociada"] = clasificacion_fun.get("actividad")
    
    return inventario
