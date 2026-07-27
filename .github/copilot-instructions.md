# Copilot Instructions for justificacion_engira

## Project Overview

This is a document discovery and cataloging pipeline for the enGira! project, a cultural funding justification system managed by the Spanish Ministry of Culture. The pipeline scans a hierarchical folder structure containing project documentation and generates an inventory and analysis report.

**Key Context:**
- Project: enGira! (Plataforma digital para la movilidad, distribución y acompañamiento de profesionales de las artes escénicas)
- Grant: Ministry of Culture - Ayudas para la acción y la promoción cultural
- Amount: €25,000 (€34,180 total budget)
- Execution period: 2025-07-01 to 2026-06-30
- Grant ID: 19770-02535886

## Architecture

The pipeline follows a config-driven architecture with three main components:

1. **Configuration Layer** (`engine/config/*.yaml`)
   - `proyecto.yaml` - Central configuration defining the entire document structure, filing deadlines, allowed file types, and processing options
   - `categorias.yaml` - Document classification rules
   - `reglas_proyecto.yaml` - Project-specific rules and validation

2. **Core Logic** (`engine/src/inventario.py`)
   - `buscar_documentos()` - Recursively scans input folders defined in `proyecto.yaml` to locate all files
   - Uses `Path.rglob()` for recursive traversal; respects `rutas_entrada` mapping which maps funding activity areas to folder names

3. **Entry Point** (`engine/run_pipeline.py`)
   - `cargar_configuracion()` - Loads YAML, validates required sections, handles encoding as UTF-8
   - `main()` - Orchestrates the pipeline: loads config → discovers documents → formats output
   - All errors caught and logged to stderr; returns exit code 1 on failure

## Key Conventions

### Configuration System
- All user-facing settings must go in `engine/config/proyecto.yaml`
- Required sections: `proyecto`, `subvencion`, `fechas`, `rutas_entrada`, `rutas_salida`
- File types are extensible via the `tipos_archivos` dict in `proyecto.yaml` (each entry specifies: extensions, category, extractor, editability, text capability)
- Input folder names (e.g., `02_ACTIVIDADES_REALIZADAS`) are defined in `rutas_entrada` and must physically exist or the pipeline continues gracefully

### Path Handling
- Repository root is calculated relative to the pipeline script: `Path(__file__).resolve().parent`
- All paths use `Path` objects (pathlib), not strings
- Path expansion via `.expanduser()` for user home directories
- File discovery uses `rglob("*")` which includes all file types; filtering by extension happens during processing (not during discovery yet)

### Error Handling
- Catches YAML parsing errors, missing config sections, file/directory errors separately
- Logs to stderr with `print(..., file=sys.stderr)`
- Returns exit code 1 on any exception; 0 on success
- Validates config structure at startup (missing required sections raise ValueError immediately)

### Encoding & Localization
- All text I/O assumes UTF-8 encoding (specified in file open calls)
- Dates follow ISO 8601 format (YYYY-MM-DD)
- Currency is EUR; monetary formatting uses `.2f` (e.g., `€25000.00`)
- Spanish language for console output and error messages

## Developer Workflows & Contribution Guidelines

### Branching Strategy

Follow a simplified git flow:
- `main` - Production-ready code, stable state
- `develop` - Integration branch for features, always deployable
- Feature branches - `feature/description` (e.g., `feature/add-hash-extraction`)
- Bugfix branches - `bugfix/description` (e.g., `bugfix/config-path-mismatch`)

**Branch naming convention:** `<type>/<kebab-case-description>` prefixed with your username when working locally (e.g., `usuario/feature/add-text-extraction`)

### Commit Messages

Use clear, imperative-mood commit messages (Spanish preferred):
```
<type>(<scope>): <description>

<optional detailed explanation>

Closes #<issue_number> (if applicable)
```

**Types:** `feat` (new feature), `fix` (bug fix), `refactor` (code restructure), `docs` (documentation), `test` (tests), `chore` (config/deps)

**Scope examples:** `config`, `inventario`, `pipeline`, `docs`

Example:
```
feat(inventario): implementar extracción de hash SHA256

Añade cálculo automático de hash SHA256 para todos los archivos descubiertos.
Implementa deduplicación basada en hash en run_pipeline.py.

Closes #42
```

### Pull Request Workflow

1. Create feature branch from `develop`
2. Make changes and commit with clear messages
3. Push to remote and open a pull request against `develop`
4. Request review from maintainers
5. Pass all checks (tests, linting, config validation)
6. Merge to `develop` once approved
7. Periodically merge `develop` → `main` for releases

### Code Review Expectations

- Verify config changes don't break the YAML schema
- Check path handling uses `pathlib.Path` consistently
- Ensure UTF-8 encoding is specified for all file I/O
- Review error handling for proper exception capture and stderr logging
- Validate that new features respect existing conventions (dates ISO 8601, currency EUR, Spanish output)

### Local Development Setup

```bash
# Clone and navigate
git clone <repo-url>
cd pipeline

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r engine/requirements.txt

# Run pipeline locally
cd engine
python run_pipeline.py

# When ready to commit
git add .
git commit -m "feat(scope): description"
git push origin feature/branch-name
```

### Issue Tracking

- Open issues for bugs, feature requests, and documentation gaps
- Use issue labels: `bug`, `feature`, `enhancement`, `documentation`, `question`
- Link related PRs to issues in commit messages or PR description

## Build, Test & Run Commands

### Running the Pipeline

```bash
cd engine
python run_pipeline.py
```

This will:
1. Load configuration from `config/proyecto.yaml`
2. Scan all folders listed in `rutas_entrada`
3. Output results to console and log to `outputs/` directory

### Dependencies

Install from `engine/requirements.txt`:
```bash
pip install -r engine/requirements.txt
```

Currently requires: `PyYAML>=6.0,<7.0`

### Testing

The `engine/tests/` directory exists but is currently empty. When adding tests, follow this pattern:

```bash
# Run single test file
python -m pytest engine/tests/test_inventario.py -v

# Run all tests
python -m pytest engine/tests/ -v
```

### Code Structure Inspection

```bash
# Find all Python modules
find engine -name "*.py" | grep -v __pycache__

# Check config file structure
cat engine/config/proyecto.yaml
```

## Important Quirks & Gotchas

- **Config Path Mismatch**: `run_pipeline.py` builds the config path relative to itself: `raiz_repositorio / "pipeline" / "config"`, but the actual script is in `engine/`. This suggests the script expects to be one level up or symlinked.
- **Duplicate Logic**: The `buscar_documentos()` call appears twice in `main()` (lines 50 and 56) with different arguments—this is likely unintentional and should be deduplicated.
- **Missing Extension Filtering**: `buscar_documentos()` returns all files; extension-based filtering happens elsewhere (not yet visible in current code).
- **No Output Generation Yet**: The pipeline prints document lists to console but doesn't actually write the `inventario_documental.csv` or `informe_inventario.md` files defined in config yet.

## Notes for Future Development

- Consider adding parallelization for large folder scans using `concurrent.futures`
- File hashing (SHA256) and duplicate detection are configured but not yet implemented
- Text extraction for PDFs/Word/Excel is configured but not yet coded
- Consider integrating with a logging module (e.g., Python `logging`) instead of print-based errors
