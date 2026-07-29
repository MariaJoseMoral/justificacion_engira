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

Las salidas se agrupan por fase en `outputs/`:

- `01_inventario/`: inventario enriquecido, informe y clasificación.
- `02_plan_y_evidencias/`: plan canónico y vínculos con las actuaciones.
- `03_economica/`: relación de gastos y revisión de la extracción de facturas.
- `04_incidencias/`: informe y tabla de incidencias.
- `05_modelos_normalizados/`: memorias de actividades y económica listas para
  revisión; `borrador_memoria_legacy.md` se conserva solo como referencia.

Las plantillas configuradas nunca se modifican. Los vínculos heurísticos se
marcan como `automatico`, `pendiente_revision` o `sin_vincular`. La extracción
nativa de cada factura conserva página, tabla/texto, fragmento, confianza y
necesidad de OCR por campo; no se ejecuta OCR ni se crean copias normalizadas
de los originales.
