# Copilot Instructions for `justificacion_engira`

## Project model

This repository contains the Python engine for producing a traceable grant-justification record from project documents. Source documents are intentionally kept outside Git; the configured data root (`datos.raiz` in `engine/config/proyecto.yaml`) is the input to the process. Do not add source project documentation to the repository.

`workflow.md` defines the target phase model: inventory, metadata extraction, classification, entity extraction and document cross-referencing, incidence detection, and memory generation. The inventory is the source of truth: preserve each generated statement's traceability to its source document.

## Architecture and data flow

- `engine/run_pipeline.py` is the orchestration entry point. It loads `config/proyecto.yaml`, discovers documents, writes outputs, then invokes entity extraction, validation, and `GeneradorMemoria`.
- `engine/src/inventario.py` discovers files under each configured `rutas_entrada` directory and tags every record with its logical area. It currently returns dictionaries with `area` and `ruta`.
- `engine/src/extractores.py` extracts text and metadata from PDFs, Office files, and images, then detects dates, monetary amounts, NIF/CIFs, and URLs.
- `engine/src/clasificadores.py` applies built-in heuristic document and functional classifications. `engine/src/entidades.py` normalizes extracted entities and creates relations by amount, NIF/CIF, activity, and date. `engine/src/validacion.py` reports document, payment, evidence, duplication, amount, and date issues. `engine/src/memoria.py` renders the final Markdown memory from those enriched records.
- `engine/config/proyecto.yaml` is the runtime configuration. It defines project metadata, external input folders, output paths, and file-type metadata. `categorias.yaml` and `reglas_proyecto.yaml` define the intended taxonomy and project-specific rule set; they are not loaded by the current Python runtime, so wire them in explicitly when implementing configuration-driven classification.

## Commands

Install the engine dependencies:

```bash
python -m pip install -r engine/requirements.txt
```

Run the entry point from `engine/`, so the `src` imports resolve:

```bash
cd engine
python run_pipeline.py
```

The entry point generates the enriched CSV inventory, Markdown reports, the legacy Markdown memory, and `outputs/memoria_de_actividades.docx`. The DOCX output uses the configured normalized template and leaves phase amounts marked as pending until they can be reconciled with the financial memory.

There is no configured test suite, linter, or formatter, and `engine/tests/` is absent. Use the following focused validation when changing Python or YAML:

```bash
python -m compileall -q engine
python - <<'PY'
from pathlib import Path
import yaml

for path in Path("engine/config").glob("*.yaml"):
    with path.open(encoding="utf-8") as source:
        yaml.safe_load(source)
    print(f"valid: {path}")
PY
```

## Repository-specific conventions

- Use `pathlib.Path` for file-system operations. Keep input and output locations configured in `proyecto.yaml`; do not hard-code project-document paths.
- Read and write text as UTF-8. Console messages, generated reports, error messages, and rule vocabulary are Spanish; retain that language for user-facing additions.
- Preserve the record shape used between phases. Metadata fields that must survive CSV serialization are consumed by later phases as pipe-delimited strings (for example, `nifs_detectados`, `fechas_detectadas`, `importes_detectados`, and `urls_detectadas`).
- Classification and validation are heuristic. Keep confidence/severity values and the evidence used for a relation explicit; do not turn uncertain matches into definitive assertions in generated reports.
- The configured `rutas_entrada` keys represent logical grant areas and are part of the document-context model. A missing physical input directory is intentionally skipped during discovery.
