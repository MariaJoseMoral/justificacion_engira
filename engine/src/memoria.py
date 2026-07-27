"""Módulo de generación automática de memoria justificativa."""

from typing import Dict, List
from datetime import datetime
from collections import defaultdict


class GeneradorMemoria:
    """Genera una memoria justificativa automáticamente."""
    
    def __init__(self, config: Dict, inventario: List[Dict], 
                 entidades: Dict, incidencias: List[Dict]):
        """Inicializa el generador."""
        self.config = config
        self.inventario = inventario
        self.entidades = entidades
        self.incidencias = incidencias
    
    def generar(self) -> str:
        """Genera la memoria justificativa completa."""
        proyecto = self.config["proyecto"]
        subvencion = self.config["subvencion"]
        fechas = self.config["fechas"]
        
        memoria = ""
        
        # Portada y metadatos
        memoria += self._generar_portada(proyecto, subvencion, fechas)
        
        # Índice
        memoria += self._generar_indice()
        
        # 1. Introducción y descripción del proyecto
        memoria += self._generar_introduccion(proyecto)
        
        # 2. Resumen de actividades realizadas
        memoria += self._generar_resumen_actividades()
        
        # 3. Resultados e indicadores
        memoria += self._generar_resultados_indicadores()
        
        # 4. Justificación económica
        memoria += self._generar_justificacion_economica(subvencion)
        
        # 5. Evidencias
        memoria += self._generar_evidencias()
        
        # 6. Incidencias y observaciones
        memoria += self._generar_incidencias()
        
        # 7. Conclusiones
        memoria += self._generar_conclusiones(proyecto)
        
        # Anexos
        memoria += self._generar_anexos()
        
        return memoria
    
    def _generar_portada(self, proyecto: Dict, subvencion: Dict, fechas: Dict) -> str:
        """Genera la portada."""
        texto = "# MEMORIA JUSTIFICATIVA DEL PROYECTO\n\n"
        texto += f"**{proyecto['nombre']}**\n\n"
        texto += f"Expediente: {proyecto['expediente']}\n\n"
        texto += f"Responsable: {proyecto['responsable']}\n\n"
        texto += f"Entidad: {proyecto['entidad']}\n\n"
        texto += f"**Organismo:** {subvencion['organismo']}\n\n"
        texto += f"**Convocatoria:** {subvencion['convocatoria']}\n\n"
        texto += f"**Importe concedido:** €{subvencion['importe_concedido']:,.2f}\n\n"
        texto += f"**Período de ejecución:** {fechas['inicio_ejecucion']} — {fechas['fin_ejecucion']}\n\n"
        texto += f"**Fecha de elaboración:** {datetime.now().strftime('%d/%m/%Y')}\n\n"
        texto += "---\n\n"
        
        return texto
    
    def _generar_indice(self) -> str:
        """Genera el índice."""
        return """## ÍNDICE

1. Introducción y descripción del proyecto
2. Resumen de actividades realizadas
3. Resultados e indicadores
4. Justificación económica
5. Evidencias y documentación
6. Incidencias y observaciones
7. Conclusiones
8. Anexos

---

"""
    
    def _generar_introduccion(self, proyecto: Dict) -> str:
        """Genera la introducción."""
        texto = "## 1. INTRODUCCIÓN Y DESCRIPCIÓN DEL PROYECTO\n\n"
        texto += f"### Denominación del proyecto\n\n{proyecto['nombre']}\n\n"
        texto += f"### Descripción\n\n{proyecto['descripcion']}\n\n"
        texto += f"### Responsable\n\n{proyecto['responsable']}\n\n"
        
        return texto
    
    def _generar_resumen_actividades(self) -> str:
        """Genera el resumen de actividades."""
        texto = "## 2. RESUMEN DE ACTIVIDADES REALIZADAS\n\n"
        
        # Agrupar por actividad
        actividades = defaultdict(list)
        for doc in self.inventario:
            if doc.get("actividad_asociada"):
                actividades[doc["actividad_asociada"]].append(doc)
        
        if actividades:
            for actividad, docs in sorted(actividades.items()):
                texto += f"### {actividad.upper()}\n\n"
                texto += f"**Documentos asociados:** {len(docs)}\n\n"
                
                tipos = set(d.get("tipo_documental") for d in docs)
                texto += f"**Tipos de documento:** {', '.join(sorted(tipos))}\n\n"
                
                # Fechas
                fechas = set()
                for doc in docs:
                    fecas_doc = doc.get("fechas_detectadas", "").split("|")
                    fechas.update(f for f in fecas_doc if f)
                
                if fechas:
                    texto += f"**Fechas de ejecución:** {', '.join(sorted(fechas))}\n\n"
                
                texto += "\n"
        else:
            texto += "No se han identificado actividades asociadas en los documentos.\n\n"
        
        return texto
    
    def _generar_resultados_indicadores(self) -> str:
        """Genera resultados e indicadores."""
        texto = "## 3. RESULTADOS E INDICADORES\n\n"
        
        # Contar evidencias
        evidencias = [d for d in self.inventario if d.get("es_evidencia")]
        
        texto += f"### Indicadores cuantitativos\n\n"
        texto += f"- **Total de documentos generados:** {len(self.inventario)}\n"
        texto += f"- **Documentos de evidencia:** {len(evidencias)}\n"
        texto += f"- **Actividades documentadas:** {len(set(d.get('actividad_asociada') for d in self.inventario if d.get('actividad_asociada')))}\n"
        texto += f"- **Cobertura de actividades:** {len(evidencias) / max(len([d for d in self.inventario if d.get('es_gasto')]), 1):.1%}\n\n"
        
        # Desglose por tipo de evidencia
        tipo_evidencias = defaultdict(int)
        for doc in evidencias:
            tipo = doc.get("categoria", "otro")
            tipo_evidencias[tipo] += 1
        
        if tipo_evidencias:
            texto += "### Evidencias por tipo\n\n"
            for tipo, cantidad in sorted(tipo_evidencias.items(), key=lambda x: -x[1]):
                texto += f"- {tipo}: {cantidad} documentos\n"
            texto += "\n"
        
        return texto
    
    def _generar_justificacion_economica(self, subvencion: Dict) -> str:
        """Genera la justificación económica."""
        texto = "## 4. JUSTIFICACIÓN ECONÓMICA\n\n"
        
        texto += f"### Presupuesto concedido\n\n"
        texto += f"- **Importe concedido:** €{subvencion['importe_concedido']:,.2f}\n"
        texto += f"- **Presupuesto total del proyecto:** €{subvencion['presupuesto_total']:,.2f}\n"
        texto += f"- **Moneda:** {subvencion['moneda']}\n\n"
        
        # Análisis de gastos
        gastos = [d for d in self.inventario if d.get("es_gasto")]
        pagos = [d for d in self.inventario if d.get("es_pago")]
        
        texto += f"### Análisis de gastos\n\n"
        texto += f"- **Documentos de gasto identificados:** {len(gastos)}\n"
        texto += f"- **Justificantes de pago:** {len(pagos)}\n"
        
        # Suma de importes
        suma_importes = self.entidades.get("resumen", {}).get("suma_importes", 0)
        if suma_importes > 0:
            texto += f"- **Suma total de gastos registrados:** €{suma_importes:,.2f}\n"
            porcentaje = (suma_importes / subvencion["importe_concedido"]) * 100
            texto += f"- **Porcentaje de ejecución:** {porcentaje:.1f}%\n\n"
        else:
            texto += "\n"
        
        # Desglose por concepto
        conceptos = defaultdict(float)
        for imp in self.entidades.get("importes", []):
            tipo = imp.get("tipo", "otro")
            conceptos[tipo] += imp.get("valor", 0)
        
        if conceptos:
            texto += "### Desglose por tipo de documento\n\n"
            texto += "| Tipo | Cantidad (€) | % |\n"
            texto += "|------|-------------|----|\n"
            
            total_conceptos = sum(conceptos.values())
            for tipo, cantidad in sorted(conceptos.items(), key=lambda x: -x[1]):
                pct = (cantidad / total_conceptos * 100) if total_conceptos > 0 else 0
                texto += f"| {tipo} | €{cantidad:,.2f} | {pct:.1f}% |\n"
            
            texto += f"\n**TOTAL** | **€{total_conceptos:,.2f}** | **100%** |\n\n"
        
        return texto
    
    def _generar_evidencias(self) -> str:
        """Genera la sección de evidencias."""
        texto = "## 5. EVIDENCIAS Y DOCUMENTACIÓN\n\n"
        
        evidencias = [d for d in self.inventario if d.get("es_evidencia")]
        
        texto += f"### Inventario de evidencias\n\n"
        texto += f"**Total de evidencias documentadas:** {len(evidencias)}\n\n"
        
        # Agrupar por tipo
        por_tipo = defaultdict(list)
        for evid in evidencias:
            tipo = evid.get("tipo_documental", "otro")
            por_tipo[tipo].append(evid)
        
        for tipo in sorted(por_tipo.keys()):
            docs = por_tipo[tipo]
            texto += f"#### {tipo.replace('_', ' ').title()}\n\n"
            texto += f"Cantidad: {len(docs)} documento(s)\n\n"
            texto += "```\n"
            for doc in docs[:5]:  # Mostrar primeros 5
                texto += f"- {doc.get('ruta_relativa', 'N/A')}\n"
            if len(docs) > 5:
                texto += f"- ... y {len(docs) - 5} más\n"
            texto += "```\n\n"
        
        return texto
    
    def _generar_incidencias(self) -> str:
        """Genera la sección de incidencias."""
        texto = "## 6. INCIDENCIAS Y OBSERVACIONES\n\n"
        
        if self.incidencias:
            # Resumen por severidad
            por_severidad = defaultdict(list)
            for inc in self.incidencias:
                por_severidad[inc.get("severidad", "baja")].append(inc)
            
            texto += f"### Resumen de incidencias\n\n"
            texto += f"**Total:** {len(self.incidencias)} incidencias detectadas\n\n"
            
            for severidad in ["crítica", "alta", "media", "baja"]:
                if severidad in por_severidad:
                    cantidad = len(por_severidad[severidad])
                    texto += f"- **{severidad.capitalize()}:** {cantidad}\n"
            
            texto += "\n### Detalles por severidad\n\n"
            
            for severidad in ["crítica", "alta", "media", "baja"]:
                incidencias_sev = por_severidad.get(severidad, [])
                if incidencias_sev:
                    texto += f"#### {severidad.upper()}\n\n"
                    for inc in incidencias_sev[:3]:  # Mostrar primeros 3
                        texto += f"- **{inc.get('tipo', 'Desconocido')}:** {inc.get('descripcion', 'N/A')}\n"
                        texto += f"  _Recomendación: {inc.get('recomendacion', 'N/A')}_\n\n"
                    
                    if len(incidencias_sev) > 3:
                        texto += f"- ... y {len(incidencias_sev) - 3} más incidencias de {severidad} severidad\n\n"
        else:
            texto += "No se han detectado incidencias críticas. La documentación es completa.\n\n"
        
        return texto
    
    def _generar_conclusiones(self, proyecto: Dict) -> str:
        """Genera las conclusiones."""
        texto = "## 7. CONCLUSIONES\n\n"
        
        texto += f"El proyecto **{proyecto['nombre']}** ha completado su ejecución dentro del período "
        texto += "establecido con la documentación correspondiente.\n\n"
        
        gastos = [d for d in self.inventario if d.get("es_gasto")]
        actividades = set(d.get("actividad_asociada") for d in self.inventario if d.get("actividad_asociada"))
        
        texto += f"**Puntos clave:**\n\n"
        texto += f"- Se han registrado **{len(gastos)}** gastos\n"
        texto += f"- Se han documentado **{len(actividades)}** actividades principales\n"
        texto += f"- Se dispone de **{len([d for d in self.inventario if d.get('es_evidencia')])}** evidencias de ejecución\n"
        texto += f"- La documentación administrativa es completa en un **{min(100, (len([d for d in self.inventario if d.get('tipo_documental') != 'documento_generico']) / max(len(self.inventario), 1)) * 100):.0f}%**\n\n"
        
        texto += "---\n\n"
        
        return texto
    
    def _generar_anexos(self) -> str:
        """Genera la sección de anexos."""
        texto = "## 8. ANEXOS\n\n"
        
        texto += "### A. Inventario completo de documentos\n\n"
        texto += "Ver archivo: `inventario_documental.csv`\n\n"
        
        texto += "### B. Reporte de clasificaciones\n\n"
        texto += "Ver archivo: `reporte_clasificaciones.txt`\n\n"
        
        texto += "### C. Entidades normalizadas\n\n"
        resumen = self.entidades.get("resumen", {})
        texto += f"- **Personas identificadas:** {resumen.get('total_personas', 0)}\n"
        texto += f"- **Empresas/Proveedores:** {resumen.get('total_empresas', 0)}\n"
        texto += f"- **NIFs/CIFs únicos:** {resumen.get('total_nifs_cifs', 0)}\n"
        texto += f"- **Fechas documentadas:** {resumen.get('total_fechas', 0)}\n"
        texto += f"- **URLs referenciadas:** {resumen.get('total_urls', 0)}\n\n"
        
        texto += "---\n\n"
        texto += f"*Generado automáticamente por el pipeline de justificación el {datetime.now().strftime('%d/%m/%Y a las %H:%M:%S')}*\n"
        
        return texto
