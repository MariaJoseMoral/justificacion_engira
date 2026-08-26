# Motor de justificación

El cronograma aprobado de `01_PROYECTO_PRESENTADO` define el plan canónico.
Rutas lógicas, selectores de plantillas y salidas se configuran en
`config/proyecto.yaml`; otro expediente con la misma estructura solo requiere
sustituir `datos_engira`.

Desde `engine/`:

```bash
python run_pipeline.py
python -m unittest discover -s tests -v
```

## Flujo actual

El pipeline ejecuta las fases de:

1. inventario documental,
2. extracción de metadatos,
3. clasificación documental,
4. clasificación funcional,
5. extracción de entidades,
6. validación de incidencias,
7. generación de memoria narrativa y económica.

## Salidas por fase

Las salidas se agrupan en `outputs/`:

- `01_inventario/`: inventario enriquecido, informe y clasificación.
- `02_plan_y_evidencias/`: plan canónico y vínculos con las actuaciones.
- `03_economica/`: relación de gastos y revisión de la extracción de facturas.
- `04_incidencias/`: informe y tabla de incidencias.
- `05_modelos_normalizados/`: memorias de actividades y económica listas para
  revisión; `borrador_memoria_legacy.md` se conserva solo como referencia.

## Ajuste económico actual

La generación de la memoria económica tiene una validación específica para la
plantilla oficial del Ministerio. El generador debe:

- separar gastos con carga a la ayuda y otros gastos del proyecto,
- mantener la estructura de tablas y combinaciones de celdas de la plantilla,
- clasificar por tipo (`nómina`, `autónoma`, `proveedores`, `gastos ordinarios`),
- mantener la numeración por sección y reiniciarla según clasificación,
- insertarse dinámicamente según el número real de filas necesarias,
- recalcular los totales y desvíos con fórmulas coherentes.

Esto evita los errores de formato y de cálculo que aparecían al generar el Excel
`08_MODELOS_NORMALIZADOS_memoria_economica.xlsx`.

## Reglas de operación

- Las plantillas configuradas nunca se modifican.
- Los vínculos heurísticos se marcan como `automatico`, `pendiente_revision` o
  `sin_vincular`.
- La extracción nativa de cada factura conserva página, tabla/texto, fragmento,
  confianza y necesidad de OCR por campo; no se ejecuta OCR ni se crean copias
  normalizadas de los originales.
- Los archivos de proyecto y la documentación externa no se suben al repositorio.
