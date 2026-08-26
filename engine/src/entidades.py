"""Módulo de extracción y normalización de entidades."""

import re
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict


class ExtractorEntidades:
    """Extrae y normaliza entidades del proyecto."""
    
    def __init__(self):
        """Inicializa el extractor."""
        self.entidades = {
            "personas": set(),
            "empresas": set(),
            "nifs_cifs": {},  # cif -> nombre
            "fechas": set(),
            "importes": [],  # lista de (cantidad, contexto)
            "cuentas": set(),
            "urls": set(),
        }
    
    def procesar_inventario(self, inventario: List[Dict]) -> Dict[str, any]:
        """
        Procesa el inventario completo y extrae entidades.
        
        Args:
            inventario: Lista de documentos con metadatos
        
        Returns:
            Dict con entidades normalizadas
        """
        for doc in inventario:
            # Extraer NIFs/CIFs
            nifs = doc.get("nifs_detectados", "").split("|")
            for nif in nifs:
                if nif:
                    self.entidades["nifs_cifs"][nif.upper()] = doc.get("nombre", "")
            
            # Extraer fechas
            fechas = doc.get("fechas_detectadas", "").split("|")
            for fecha in fechas:
                if fecha:
                    self.entidades["fechas"].add(fecha)
            
            # Extraer importes
            importes = doc.get("importes_detectados", "").split("|")
            for importe in importes:
                if importe:
                    cantidad = self._normalizar_importe(importe)
                    if cantidad:
                        self.entidades["importes"].append({
                            "valor": cantidad,
                            "original": importe,
                            "documento": doc.get("nombre", ""),
                            "tipo": doc.get("tipo_documental", "")
                        })
            
            # Extraer URLs
            urls = doc.get("urls_detectadas", "").split("|")
            for url in urls:
                if url:
                    self.entidades["urls"].add(url)
            
            # Extraer personas de nombre de archivo o contenido
            personas = self._extraer_personas(doc)
            self.entidades["personas"].update(personas)
            
            # Extraer empresas
            empresas = self._extraer_empresas(doc)
            self.entidades["empresas"].update(empresas)
        
        return self._normalizar_entidades()
    
    def _normalizar_importe(self, importe_str: str) -> Optional[float]:
        """Normaliza un string de importe a float."""
        # Limpiar
        importe = importe_str.strip()
        
        # Remover símbolos de moneda
        importe = re.sub(r'[€EUR]', '', importe).strip()
        
        # Convertir formato europeo (1.234,56) a float
        if ',' in importe and '.' in importe:
            # Formato: 1.234,56 → 1234.56
            partes = importe.split('.')
            importe = ''.join(partes[:-1]) + '.' + partes[-1].replace(',', '')
        elif ',' in importe:
            # Formato: 1234,56 → 1234.56
            importe = importe.replace(',', '.')
        
        try:
            return float(importe)
        except ValueError:
            return None
    
    def _extraer_personas(self, doc: Dict) -> Set[str]:
        """Extrae nombres de personas del documento."""
        personas = set()
        nombre = doc.get("nombre", "").lower()
        
        # Patrones comunes de nombres en contexto de facturación/nómina
        patterns = [
            r"(?:sr\.?|sra\.?|d\.?|dña\.?)\s+([a-záéíóúñü\s]+?)(?:\s+(?:garcía|lópez|martínez|hernández|pérez|sánchez|torres|romero|flores|rivera|cruz|morales|silva|vega|león|reyes|moreno|castillo|iglesias|ruiz|rodrígues|rodríguez|fernández|jiménez|gómez|díaz|suárez|delgado|campos|santos|vargas|herrera|medina|valerio|soto|aguilar|guerrero|ortega|ramos|montoya|cabrera|correa|cortés|valencia|lara|fuentes|espinoza))?(?:\s|$|,)",
            r"([a-záéíóúñü]+(?:\s+[a-záéíóúñü]+)?)\s+(?:garcía|López|martínez|hernández|pérez|sánchez|torres|romero|flores|rivera|cruz|morales|silva|vega|león|reyes|moreno|castillo|iglesias|ruiz|rodrígues|rodríguez|fernández|jiménez|gómez|díaz|suárez|delgado|campos|santos|vargas|herrera|medina|valerio|soto|aguilar|guerrero|ortega|ramos|montoya|cabrera|correa|cortés|valencia|lara|fuentes|espinoza)",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, nombre, re.IGNORECASE)
            personas.update(m.strip() for m in matches if len(m.strip()) > 3)
        
        return personas
    
    def _extraer_empresas(self, doc: Dict) -> Set[str]:
        """Extrae nombres de empresas/proveedores."""
        empresas = set()
        nombre = doc.get("nombre", "").lower()
        
        # Palabras clave que indican empresa
        keywords = [
            "sl", "slu", "slne", "sa", "sap", "sarl", "ltda", "limited",
            "inc", "corp", "consulting", "gestoria", "agencia", "estudio",
            "gestoría", "empresa", "grupo", "centro", "sociedad"
        ]
        
        for keyword in keywords:
            if keyword in nombre:
                empresas.add(nombre.split(keyword)[0].strip())
        
        return empresas
    
    def _normalizar_entidades(self) -> Dict[str, any]:
        """Normaliza las entidades extraídas."""
        resultado = {
            "personas": sorted(list(self.entidades["personas"])),
            "empresas": sorted(list(self.entidades["empresas"])),
            "nifs_cifs": self.entidades["nifs_cifs"],
            "fechas": sorted(list(self.entidades["fechas"])),
            "importes": sorted(
                self.entidades["importes"],
                key=lambda x: x["valor"]
            ),
            "urls": sorted(list(self.entidades["urls"])),
            "resumen": {
                "total_personas": len(self.entidades["personas"]),
                "total_empresas": len(self.entidades["empresas"]),
                "total_nifs_cifs": len(self.entidades["nifs_cifs"]),
                "total_fechas": len(self.entidades["fechas"]),
                "total_importes": len(self.entidades["importes"]),
                "suma_importes": sum(i["valor"] for i in self.entidades["importes"]),
                "total_urls": len(self.entidades["urls"]),
            }
        }
        
        return resultado


class CruzadorDocumental:
    """Relaciona documentos que forman parte de una misma evidencia."""
    
    def __init__(self, inventario: List[Dict]):
        """Inicializa el cruzador."""
        self.inventario = inventario
        self.relaciones = []
    
    def crear_grafo(self) -> List[Dict]:
        """
        Crea relaciones entre documentos.
        
        Ejemplos:
        - Factura ↔ Transferencia (mismo importe, fecha próxima)
        - Contrato ↔ Nómina (misma persona)
        - Actividad ↔ Fotografía (misma carpeta)
        - Actividad ↔ Memoria (referencias cruzadas)
        
        Returns:
            Lista de relaciones encontradas
        """
        relaciones = []
        
        # Buscar relaciones por importe
        relaciones.extend(self._relacionar_por_importe())
        
        # Buscar relaciones por persona/NIF
        relaciones.extend(self._relacionar_por_entidad())
        
        # Buscar relaciones por actividad
        relaciones.extend(self._relacionar_por_actividad())
        
        # Buscar relaciones por fecha
        relaciones.extend(self._relacionar_por_fecha())
        
        self.relaciones = relaciones
        return relaciones
    
    def _relacionar_por_importe(self) -> List[Dict]:
        """Relaciona documentos con importes similares."""
        relaciones = []
        importes_dict = defaultdict(list)
        
        # Agrupar por importe
        for doc in self.inventario:
            importes = doc.get("importes_detectados", "").split("|")
            for importe in importes:
                if importe and importe.strip():
                    # Normalizar importe
                    norm = importe.replace(",", ".").replace("€", "").strip()
                    importes_dict[norm].append(doc)
        
        # Buscar pares de documentos con mismo importe
        for importe, docs in importes_dict.items():
            if len(docs) >= 2:
                # Buscar factura + transferencia
                facturas = [d for d in docs if d.get("tipo_documental") == "factura"]
                transferencias = [d for d in docs if d.get("tipo_documental") == "transferencia"]
                
                if facturas and transferencias:
                    for fact in facturas:
                        for transf in transferencias:
                            relaciones.append({
                                "tipo": "factura_pago",
                                "documento1": fact.get("nombre"),
                                "documento2": transf.get("nombre"),
                                "criterio": f"importe_coincidente_{importe}",
                                "confianza": 0.8
                            })
        
        return relaciones
    
    def _relacionar_por_entidad(self) -> List[Dict]:
        """Relaciona documentos por persona/empresa común."""
        relaciones = []
        nifs_dict = defaultdict(list)
        
        # Agrupar por NIF/CIF
        for doc in self.inventario:
            nifs = doc.get("nifs_detectados", "").split("|")
            for nif in nifs:
                if nif and nif.strip():
                    nifs_dict[nif.upper()].append(doc)
        
        # Buscar pares con mismo NIF
        for nif, docs in nifs_dict.items():
            if len(docs) >= 2:
                for i, doc1 in enumerate(docs):
                    for doc2 in docs[i+1:]:
                        relaciones.append({
                            "tipo": "entidad_comun",
                            "documento1": doc1.get("nombre"),
                            "documento2": doc2.get("nombre"),
                            "criterio": f"nif_cif_{nif}",
                            "confianza": 0.7
                        })
        
        return relaciones
    
    def _relacionar_por_actividad(self) -> List[Dict]:
        """Relaciona documentos de la misma actividad."""
        relaciones = []
        actividades_dict = defaultdict(list)
        
        # Agrupar por actividad
        for doc in self.inventario:
            actividad = doc.get("actividad_asociada")
            if actividad and actividad.strip():
                actividades_dict[actividad].append(doc)
        
        # Buscar evidencias de actividad
        for actividad, docs in actividades_dict.items():
            if len(docs) >= 2:
                # Buscar: memoria + fotografías/videos
                memorias = [d for d in docs if d.get("tipo_documental") == "memoria"]
                evidencias = [d for d in docs if d.get("es_evidencia")]
                
                for mem in memorias:
                    for evid in evidencias:
                        if mem != evid:
                            relaciones.append({
                                "tipo": "actividad_evidencia",
                                "documento1": mem.get("nombre"),
                                "documento2": evid.get("nombre"),
                                "criterio": f"actividad_{actividad}",
                                "confianza": 0.6
                            })
        
        return relaciones
    
    def _relacionar_por_fecha(self) -> List[Dict]:
        """Relaciona documentos con fechas próximas."""
        relaciones = []
        
        # Agrupar por fecha (rango de 15 días)
        for i, doc1 in enumerate(self.inventario):
            fechas1 = doc1.get("fechas_detectadas", "").split("|")
            
            for doc2 in self.inventario[i+1:]:
                fechas2 = doc2.get("fechas_detectadas", "").split("|")
                
                # Simple: buscar misma fecha
                for f1 in fechas1:
                    for f2 in fechas2:
                        if f1 == f2 and f1.strip():
                            relaciones.append({
                                "tipo": "fecha_comun",
                                "documento1": doc1.get("nombre"),
                                "documento2": doc2.get("nombre"),
                                "criterio": f"fecha_{f1}",
                                "confianza": 0.5
                            })
        
        return relaciones


def enriquecer_con_entidades_y_relaciones(inventario: List[Dict]) -> Tuple[Dict, List[Dict]]:
    """
    Enriquece el inventario con entidades y relaciones.
    
    Returns:
        (entidades_normalizadas, relaciones_documentales)
    """
    # Extraer entidades
    extractor = ExtractorEntidades()
    entidades = extractor.procesar_inventario(inventario)
    
    # Crear grafo documental
    cruzador = CruzadorDocumental(inventario)
    relaciones = cruzador.crear_grafo()
    
    return entidades, relaciones
