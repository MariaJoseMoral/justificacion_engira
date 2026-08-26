# Resultados del pipeline

Cada ejecución genera o actualiza resultados en la carpeta correspondiente a su
fase:

- `01_inventario`: inventario documental, informe y clasificación.
- `02_plan_y_evidencias`: plan aprobado interpretado y vínculos de evidencia.
- `03_economica`: relación de gastos, trazabilidad y revisión de facturas.
- `04_incidencias`: incidencias detectadas y tabla de revisión.
- `05_modelos_normalizados`: documentos entregables y el borrador legado.

Las rutas se definen en `../config/proyecto.yaml`. Para regenerar todos los
artefactos, ejecutar `python run_pipeline.py` desde `engine/`.
