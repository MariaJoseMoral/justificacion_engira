# Flujo de trabajo para la elaboración automatizada de memorias justificativas

## Objetivo

Construir un pipeline reutilizable capaz de transformar una carpeta de documentación de un proyecto subvencionado en una memoria justificativa completa, verificable y trazable.

El flujo se divide en fases independientes, donde la salida de cada una constituye la entrada de la siguiente.

---

# Arquitectura general

```
Proyecto
│
├── datos_proyecto/
│   ├── 00_...
│   ├── 01_...
│   ├── ...
│   └── 10_...
│
└── engine/
    ├── config/
    ├── src/
    ├── templates/
    ├── outputs/
    ├── logs/
    └── tests/
```

El repositorio únicamente contiene el motor del pipeline.

Toda la documentación del proyecto permanece fuera del repositorio y constituye la entrada del proceso.

---

# Fase 1. Inventario semántico

## Objetivo

Construir un inventario estructurado de toda la documentación del proyecto.

A diferencia de un simple listado de archivos, el inventario conserva desde el primer momento el contexto documental de cada archivo.

## Entrada

Directorio del proyecto:

```
datos_proyecto/
```

y su estructura lógica definida en:

```yaml
rutas_entrada:
```

Por ejemplo:

```yaml
rutas_entrada:

  bases_y_resolucion

  proyecto_presentado

  actividades

  resultados_indicadores

  comunicacion

  participantes

  desarrollo_plataforma

  evidencias

  justificacion_economica

  desviaciones

  memoria_final
```

## Procesos

Para cada carpeta lógica:

- recorrido recursivo
- identificación de archivos
- generación de un inventario único
- asociación del documento con su área de procedencia

Se almacenan inicialmente:

- identificador
- área lógica
- ruta absoluta
- ruta relativa
- nombre
- extensión
- tamaño
- fechas del sistema

Todavía no existe clasificación documental.

El inventario únicamente representa la realidad física de la documentación.

## Salida

`inventario.csv`

---

# Fase 2. Extracción de metadatos

## Objetivo

Enriquecer el inventario con información obtenida automáticamente.

Procesos:

- lectura de PDFs
- OCR
- extracción de texto
- idioma
- páginas
- tablas
- fechas
- importes
- CIF/NIF
- personas
- organismos
- URLs

## Salida

Inventario enriquecido.

---

# Fase 3. Clasificación documental

## Objetivo

Determinar qué tipo de documento representa cada archivo.

Ejemplos:

- factura
- contrato
- nómina
- transferencia
- memoria
- fotografía
- correo
- captura web
- certificado
- informe
- resolución

La clasificación utiliza:

- reglas YAML
- nombre del archivo
- contenido
- metadatos
- OCR

## Salida

Inventario clasificado.

---

# Fase 4. Clasificación funcional

## Objetivo

Relacionar cada documento con la actividad financiada.

Ejemplos:

- administración
- comunicación
- desarrollo software
- alianzas estratégicas
- investigación
- formación
- comercialización
- gestoría
- laboral

La clasificación combina:

- área de procedencia (inventario)
- reglas YAML
- entidades detectadas
- contenido textual

## Salida

Inventario vinculado al presupuesto del proyecto.

---

# Fase 5. Extracción de entidades

## Objetivo

Normalizar toda la información relevante del proyecto.

Extracción de:

- empresas
- personas
- proveedores
- administraciones
- expedientes
- importes
- fechas
- cuentas
- URLs
- NIF/CIF

Las entidades se almacenan de forma normalizada para evitar duplicidades.

## Salida

Base de entidades.

---

# Fase 6. Cruce documental

## Objetivo

Relacionar automáticamente documentos que forman parte de una misma evidencia administrativa.

Ejemplos:

Factura ↔ Transferencia

Contrato ↔ Nómina

Factura ↔ Pedido

Actividad ↔ Fotografías

Actividad ↔ Publicaciones

Actividad ↔ Indicadores

Actividad ↔ Evidencias

## Resultado

Grafo documental del proyecto.

---

# Fase 7. Detección automática de incidencias

## Objetivo

Comprobar que la justificación está completa.

Ejemplos:

- gastos sin factura
- factura sin pago
- pago sin factura
- actividad sin evidencia
- publicación sin captura
- indicadores sin soporte
- documentos duplicados
- documentos inconsistentes

## Salida

Informe de incidencias.

---

# Fase 8. Generación automática de la memoria

## Objetivo

Construir un primer borrador completo.

Incluye:

- narrativa de actividades
- cronología
- indicadores
- resultados
- tablas
- anexos
- referencias cruzadas
- relación documental

Toda afirmación debe poder trazarse hasta uno o varios documentos del inventario.

## Salida

Memoria justificativa editable.

---

# Fase 9. Validación final

## Objetivo

Realizar una comprobación integral antes de la entrega.

Verificaciones:

- presupuesto
- importes
- fechas
- actividades
- indicadores
- anexos
- coherencia narrativa
- documentación obligatoria

## Salida

Memoria lista para revisión y presentación.

---

# Flujo completo

```
datos_proyecto
        │
        ▼
Inventario semántico
        │
        ▼
Extracción de metadatos
        │
        ▼
Clasificación documental
        │
        ▼
Clasificación funcional
        │
        ▼
Extracción de entidades
        │
        ▼
Cruce documental
        │
        ▼
Detección de incidencias
        │
        ▼
Generación automática de memoria
        │
        ▼
Validación final
```

---

# Principios de diseño

- El motor del pipeline es completamente independiente del proyecto.
- La configuración específica se define mediante archivos YAML.
- Los documentos nunca se almacenan dentro del repositorio Git.
- El inventario constituye la fuente única de verdad del sistema.
- Cada fase es ejecutable y verificable de forma independiente.
- La trazabilidad debe mantenerse desde cada frase de la memoria hasta el documento que la sustenta.
- La clasificación debe ser reproducible, explicable y configurable sin modificar el código Python.