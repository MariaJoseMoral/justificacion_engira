# justificacion_engira

Motor para elaborar una justificación trazable a partir de documentación externa del expediente `enGira!`.

## Qué incluye este repositorio

- `engine/`: código del pipeline, configuración, pruebas y salidas organizadas por fase.
- `workflow.md`: descripción del flujo de trabajo completo previsto por fases.
- `../datos_engira/`: documentación de entrada del expediente; no se versiona dentro del repositorio.

## Estado actual del proyecto

La rama actual ya incorpora la automatización completa de:

- inventario documental y enriquecimiento semántico,
- interpretación del cronograma aprobado,
- vinculación de evidencias,
- detección de incidencias,
- generación de memoria de actividades,
- generación de memoria económica con plantilla normalizada.

El módulo económico ha sido corregido para respetar la estructura de la plantilla oficial, incluidos los sumatorios, la clasificación por tabla y la inserción dinámica de filas según el número de gastos.

## Ejecución

Desde `engine/`:

```bash
python run_pipeline.py
```

El motor genera las salidas en `engine/outputs/` según la fase del proceso.

## Documentación adicional

- [`engine/README.md`](engine/README.md)
- [`workflow.md`](workflow.md)

La documentación del proyecto y los documentos fuente del expediente quedan fuera del repositorio para mantener la trazabilidad documental sin versionar archivos de negocio.