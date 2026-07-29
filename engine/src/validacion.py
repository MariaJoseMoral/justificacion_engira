"""Módulo de detección de incidencias y validación."""

from typing import Any, Dict, Iterable, List, Tuple, Optional
from collections import defaultdict
from datetime import date

from .economica import FinancialRecord
from .evidencias import EvidenceLink
from .plan import CanonicalPlan


class ValidadorIncidencias:
    """Detecta inconsistencias y problemas en la documentación."""
    
    def __init__(
        self, inventario: List[Dict], relaciones: List[Dict], entidades: Dict, config: Dict | None = None
    ):
        """Inicializa el validador."""
        self.inventario = inventario
        self.relaciones = relaciones
        self.entidades = entidades
        self.config = config or {}
        self.incidencias = []
    
    def validar(self) -> List[Dict]:
        """
        Valida la documentación completa.
        
        Returns:
            Lista de incidencias encontradas
        """
        self.incidencias = []
        
        # Validaciones
        self._validar_gastos_sin_justificar()
        self._validar_pagos_sin_factura()
        self._validar_actividades_sin_evidencia()
        self._validar_documentacion_obligatoria()
        self._validar_duplicados()
        self._validar_importes()
        self._validar_fechas()
        
        return sorted(
            self.incidencias,
            key=lambda x: {"crítica": 0, "alta": 1, "media": 2, "baja": 3}.get(
                x.get("severidad", "baja"), 4
            )
        )
    
    def _validar_gastos_sin_justificar(self):
        """Detecta gastos (facturas) sin transferencia asociada."""
        facturas = [d for d in self.inventario if d.get("tipo_documental") == "factura"]
        
        # Extraer importes de transferencias
        importes_pagados = set()
        for doc in self.inventario:
            if doc.get("tipo_documental") == "transferencia":
                importes = doc.get("importes_detectados", "").split("|")
                for imp in importes:
                    if imp:
                        importes_pagados.add(imp.strip())
        
        # Buscar facturas sin pago
        for factura in facturas:
            importes = factura.get("importes_detectados", "").split("|")
            
            encontrada = False
            for imp in importes:
                if imp and imp.strip() in importes_pagados:
                    encontrada = True
                    break
            
            if not encontrada and importes and importes[0]:
                self.incidencias.append({
                    "tipo": "gasto_sin_justificacion",
                    "documento": factura.get("nombre"),
                    "severidad": "alta",
                    "descripcion": f"Factura sin transferencia de pago detectada: {factura.get('nombre')}",
                    "importe": importes[0] if importes else None,
                    "recomendacion": "Adjuntar justificante de pago"
                })
    
    def _validar_pagos_sin_factura(self):
        """Detecta pagos (transferencias) sin factura asociada."""
        transferencias = [d for d in self.inventario 
                         if d.get("tipo_documental") == "transferencia"]
        
        # Extraer importes de facturas
        importes_facturados = set()
        for doc in self.inventario:
            if doc.get("tipo_documental") == "factura":
                importes = doc.get("importes_detectados", "").split("|")
                for imp in importes:
                    if imp:
                        importes_facturados.add(imp.strip())
        
        # Buscar transferencias sin factura
        for transf in transferencias:
            importes = transf.get("importes_detectados", "").split("|")
            
            encontrada = False
            for imp in importes:
                if imp and imp.strip() in importes_facturados:
                    encontrada = True
                    break
            
            if not encontrada and importes and importes[0]:
                self.incidencias.append({
                    "tipo": "pago_sin_factura",
                    "documento": transf.get("nombre"),
                    "severidad": "media",
                    "descripcion": f"Transferencia sin factura de referencia: {transf.get('nombre')}",
                    "importe": importes[0] if importes else None,
                    "recomendacion": "Adjuntar factura o justificante del gasto"
                })
    
    def _validar_actividades_sin_evidencia(self):
        """Detecta actividades sin evidencias (fotografías/videos)."""
        actividades = [d for d in self.inventario 
                      if d.get("tipo_documental") == "memoria" 
                      and d.get("actividad_asociada")]
        
        for actividad in actividades:
            act_nombre = actividad.get("actividad_asociada")
            
            # Buscar evidencias de la actividad
            evidencias = [d for d in self.inventario 
                         if d.get("actividad_asociada") == act_nombre 
                         and d.get("es_evidencia")]
            
            if not evidencias:
                self.incidencias.append({
                    "tipo": "actividad_sin_evidencia",
                    "documento": actividad.get("nombre"),
                    "severidad": "media",
                    "descripcion": f"Actividad '{act_nombre}' sin evidencias (fotos/videos)",
                    "actividad": act_nombre,
                    "recomendacion": "Adjuntar fotografías o vídeos de la actividad"
                })
    
    def _validar_documentacion_obligatoria(self):
        """Verifica que existe documentación obligatoria."""
        obligatorios = {
            "memoria_final": ["memoria-de-actividades", "declaración-responsable"],
            "justificacion_economica": ["justificación económica", "nómina", "factura"],
        }
        
        docs_nombres = [d.get("nombre", "").lower() for d in self.inventario]
        docs_texto = " ".join(docs_nombres)
        
        for categoria, palabras_clave in obligatorios.items():
            encontrada = False
            for palabra in palabras_clave:
                if palabra.lower() in docs_texto:
                    encontrada = True
                    break
            
            if not encontrada:
                self.incidencias.append({
                    "tipo": "documentacion_faltante",
                    "categoria": categoria,
                    "severidad": "crítica",
                    "descripcion": f"Falta documentación obligatoria: {categoria}",
                    "palabras_clave": palabras_clave,
                    "recomendacion": "Añadir documentación requerida por el Ministerio"
                })
    
    def _validar_duplicados(self):
        """Detecta documentos duplicados."""
        doc_dict = defaultdict(list)
        
        for doc in self.inventario:
            tamaño = int(doc.get("tamaño", 0)) if isinstance(doc.get("tamaño", 0), (int, str)) else 0
            # Agrupar por tamaño similar (rango de 1 KB)
            for size_key in range(max(0, tamaño - 1024), tamaño + 1024, 1024):
                doc_dict[size_key].append(doc)
        
        for size, docs in doc_dict.items():
            if len(docs) > 1:
                # Verificar si realmente son duplicados (mismo nombre parcial)
                nombres = [d.get("nombre", "") for d in docs]
                
                for i, doc1 in enumerate(docs):
                    for doc2 in docs[i+1:]:
                        # Considerar duplicados si tienen nombre similar
                        if self._son_similares(doc1.get("nombre", ""), 
                                             doc2.get("nombre", "")):
                            self.incidencias.append({
                                "tipo": "documento_duplicado",
                                "documento1": doc1.get("nombre"),
                                "documento2": doc2.get("nombre"),
                                "severidad": "baja",
                                "descripcion": f"Posible duplicado detectado",
                                "recomendacion": "Verificar y eliminar si es necesario"
                            })
    
    def _validar_importes(self):
        """Valida coherencia de importes."""
        importes = self.entidades.get("importes", [])
        
        # Buscar importes anómalamente grandes o pequeños
        if importes:
            valores = [i.get("valor", 0) for i in importes if i.get("valor")]
            
            if valores:
                promedio = sum(valores) / len(valores)
                desv_tipica = (sum((x - promedio) ** 2 for x in valores) / len(valores)) ** 0.5
                
                for imp in importes:
                    valor = imp.get("valor", 0)
                    
                    # Valores anómalamente grandes
                    if valor > promedio + (3 * desv_tipica):
                        self.incidencias.append({
                            "tipo": "importe_anomalo",
                            "documento": imp.get("documento"),
                            "valor": valor,
                            "severidad": "baja",
                            "descripcion": f"Importe inusualmente alto: {valor}€",
                            "recomendacion": "Verificar la cantidad"
                        })
    
    def _validar_fechas(self):
        """Valida fechas de los documentos."""
        fechas = self.entidades.get("fechas", [])
        
        # Buscar fechas fuera del período de ejecución
        fechas_config = self.config.get("fechas", {})
        periodo_inicio = str(fechas_config.get("inicio_ejecucion", ""))[:7]
        periodo_fin = str(fechas_config.get("fin_ejecucion", ""))[:7]
        if not periodo_inicio or not periodo_fin:
            return
        
        for fecha in fechas:
            # Validar formato ISO (YYYY-MM-DD)
            if len(fecha) >= 7:
                año_mes = fecha[:7]
                
                # Buscar documentos con esta fecha
                for doc in self.inventario:
                    if fecha in (doc.get("fechas_detectadas", "") or ""):
                        if año_mes < periodo_inicio or año_mes > periodo_fin:
                            self.incidencias.append({
                                "tipo": "fecha_fuera_periodo",
                                "documento": doc.get("nombre"),
                                "fecha": fecha,
                                "severidad": "media",
                                "descripcion": f"Fecha fuera del período de ejecución: {fecha}",
                                "recomendacion": "Verificar que la fecha es correcta"
                            })
                        break
    
    def _son_similares(self, nombre1: str, nombre2: str) -> bool:
        """Verifica si dos nombres de archivo son similares."""
        # Remover números y extensiones
        n1 = "".join(c for c in nombre1.lower() if c.isalpha())
        n2 = "".join(c for c in nombre2.lower() if c.isalpha())
        
        # Calcular similitud simple
        if not n1 or not n2:
            return False
        
        coincidencias = sum(1 for c1, c2 in zip(n1, n2) if c1 == c2)
        similitud = coincidencias / max(len(n1), len(n2))
        
        return similitud > 0.8


def generar_reporte_incidencias(incidencias: List[Dict]) -> str:
    """Genera un reporte de incidencias en formato texto."""
    reporte = "╔════════════════════════════════════════════════════════════════════════════╗\n"
    reporte += "║                    REPORTE DE INCIDENCIAS Y VALIDACIÓN                    ║\n"
    reporte += "╚════════════════════════════════════════════════════════════════════════════╝\n\n"
    
    # Resumen por severidad
    por_severidad = defaultdict(list)
    for inc in incidencias:
        por_severidad[inc.get("severidad", "baja")].append(inc)
    
    reporte += "RESUMEN\n"
    reporte += "─" * 80 + "\n"
    reporte += f"Total de incidencias: {len(incidencias)}\n"
    reporte += f"  • Críticas: {len(por_severidad.get('crítica', []))}\n"
    reporte += f"  • Altas: {len(por_severidad.get('alta', []))}\n"
    reporte += f"  • Medias: {len(por_severidad.get('media', []))}\n"
    reporte += f"  • Bajas: {len(por_severidad.get('baja', []))}\n\n"
    
    # Detalles por severidad
    for severidad in ["crítica", "alta", "media", "baja"]:
        incidencias_sev = por_severidad.get(severidad, [])
        if incidencias_sev:
            reporte += f"\n{severidad.upper()}\n"
            reporte += "─" * 80 + "\n"
            
            for inc in incidencias_sev:
                reporte += f"\n• {inc.get('tipo', 'Desconocido')}\n"
                reporte += f"  Documento: {inc.get('documento', 'N/A')}\n"
                reporte += f"  Descripción: {inc.get('descripción', 'N/A')}\n"
                reporte += f"  Recomendación: {inc.get('recomendacion', 'N/A')}\n"
    
    return reporte


def validar_plan_y_evidencias(
    plan: CanonicalPlan,
    links: Iterable[EvidenceLink],
    financial_records: Iterable[FinancialRecord],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate traceability rules specific to plan-led final outputs."""
    incidencias: list[dict[str, Any]] = []
    action_ids = [action.id for action in plan.actions]
    if len(action_ids) != len(set(action_ids)):
        incidencias.append({
            "tipo": "ids_accion_duplicados",
            "severidad": "crítica",
            "descripcion": "El plan canónico contiene identificadores de acción duplicados.",
            "recomendacion": "Revisar las actuaciones del cronograma aprobado.",
        })
    start = str(config.get("fechas", {}).get("inicio_ejecucion", ""))
    end = str(config.get("fechas", {}).get("fin_ejecucion", ""))
    for action in plan.actions:
        if action.approved_budget is not None and action.approved_budget < 0:
            incidencias.append({
                "tipo": "presupuesto_aprobado_invalido",
                "severidad": "alta",
                "descripcion": f"La acción {action.id} tiene presupuesto negativo.",
                "recomendacion": "Revisar el cronograma aprobado.",
            })
        if action.period_start and action.period_end and start and end:
            if action.period_start > end or action.period_end < start:
                incidencias.append({
                    "tipo": "accion_fuera_periodo",
                    "severidad": "alta",
                    "actividad": action.id,
                    "descripcion": f"La acción aprobada '{action.title}' queda fuera del periodo configurado.",
                    "recomendacion": "Verificar configuración o cronograma aprobado.",
                })

    links_by_action: dict[str, list[EvidenceLink]] = defaultdict(list)
    for link in links:
        if link.action_id:
            links_by_action[link.action_id].append(link)
        if link.review_state == "pendiente_revision":
            incidencias.append({
                "tipo": "vinculo_evidencia_pendiente",
                "severidad": "media",
                "documento": link.document_path,
                "actividad": link.action_id,
                "descripcion": "El vínculo entre evidencia y actuación aprobada requiere revisión humana.",
                "recomendacion": "Confirmar o corregir la actuación asociada.",
            })
    for action in plan.actions:
        if not links_by_action.get(action.id):
            incidencias.append({
                "tipo": "accion_sin_evidencia_vinculada",
                "severidad": "media",
                "actividad": action.id,
                "descripcion": f"No hay evidencia vinculada a la acción aprobada '{action.title}'.",
                "recomendacion": "Aportar evidencia o documentar la no ejecución.",
            })

    for record in financial_records:
        if record.action_id not in action_ids:
            incidencias.append({
                "tipo": "gasto_sin_accion_aprobada",
                "severidad": "alta",
                "documento": record.document_path,
                "descripcion": "Un gasto cargado no tiene acción aprobada válida.",
                "recomendacion": "Revisar la trazabilidad económica.",
            })
    return incidencias
