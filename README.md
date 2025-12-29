# SDH_Complete_Forced
Motor de limpieza SDH configurable con CLI para convertir SDH → Full, Full → Forced y SDH → Forced, preservando etiquetas HTML/ASS y saltos.

## Características
- Limpieza SDH configurable vía presets y flags puntuales.
- Preserva etiquetas `<br>`, HTML genéricas, overrides ASS `{…}` y saltos `\N`.
- Detector de forced basado en cues en mayúsculas (ignora overrides y letras sueltas).
- CLI sencilla con tres modos (`sdh_to_full`, `full_to_forced`, `sdh_to_forced`).
- Sin dependencias externas (solo Python estándar).

## Requisitos
- Python 3.10+ (probado con `.venv` local).
- Sistema operativo: cualquier con Python; ejemplos en PowerShell.

## Instalación rápida (opcional, con venv)
```pwsh
cd E:/RUTA/SDH_Complete_Forced
python -m venv .venv
.venv/Scripts/Activate.ps1
```

## Uso rápido (CLI)
```pwsh
# SDH → Full (preset aggressive por defecto)
python srt_pipeline.py --mode sdh_to_full -i input.srt -o full.srt

# SDH → Full con preset conservative
python srt_pipeline.py --mode sdh_to_full --preset conservative -i input.srt -o full.srt

# Full → Forced (solo detector de mayúsculas)
python srt_pipeline.py --mode full_to_forced -i full.srt -o forced.srt

# SDH → Forced en un paso (limpia y filtra forzados)
python srt_pipeline.py --mode sdh_to_forced --preset aggressive -i input.srt -o forced.srt
```

### Ejemplo con rutas reales
```pwsh
E:/RUTA/SDH_Complete_Forced/.venv/Scripts/python.exe srt_pipeline.py --mode full_to_forced -i "e:/RUTA/SDH_Complete_Forced/Younger S06E01 [NF WEB-DL 1080p AVC ES AAC 2.0][HDO]Compl.srt" -o "e:/RUTA/SDH_Complete_Forced/Younger S06E01 forced_calc.srt"
```

## Instrucciones paso a paso
1) Opcional: crea/activa el entorno virtual:
```pwsh
cd ./SDH_Complete_Forced
python -m venv .venv
.venv/Scripts/Activate.ps1
```
2) Elige el modo:
	- `sdh_to_full`: limpia SDH y devuelve subtítulo completo sin acotaciones.
	- `full_to_forced`: filtra un Full ya limpio para quedarse solo con cues en mayúsculas.
	- `sdh_to_forced`: limpia SDH y luego filtra forced en un paso.
3) Ejecuta el comando con rutas de entrada/salida. Ejemplo SDH → Forced en un paso:
```pwsh
python srt_pipeline.py --mode sdh_to_forced --preset aggressive -i input.srt -o forced.srt
```
4) Ajusta reglas si hace falta (añade `--no-` para invertir una opción del preset). Ejemplo para conservar paréntesis inline:
```pwsh
python srt_pipeline.py --mode sdh_to_full --preset aggressive --between-only-if-separate-line -i input.srt -o full.srt
```
5) El resultado queda en el archivo indicado con `-o` (o en pantalla si omites `-o`).

## Presets
- **aggressive / netflix** (por defecto): quita `[]` y `()` inline, speaker tags en mayúsculas antes de `:`, y líneas con solo símbolos de música.
- **conservative**: solo elimina `[]`/`()` cuando la línea es solo ese bloque; deja paréntesis inline.

## Flags configurables (se pueden negar con `--no-`)
- `--remove-between-square`
- `--remove-between-paren`
- `--between-only-if-separate-line`
- `--remove-text-before-colon`
- `--colon-only-if-uppercase`
- `--remove-if-only-music-symbols`

Ejemplo de override puntual:
```pwsh
python srt_pipeline.py --mode sdh_to_full --preset aggressive --no-remove-text-before-colon -i input.srt -o full.srt
```

## Cómo funciona
- **Limpieza SDH**: aplica `SDHConfig` (preset + overrides) para eliminar bracketed cues, speaker tags en mayúsculas antes de `:`, y líneas que solo contienen símbolos musicales (`♪♫♬♩♭♯`).
- **Preservación de formato**: protege `<br>`, cualquier etiqueta HTML, overrides ASS `{...}` y saltos `\N`; se restauran tras normalizar espacios.
- **Detector forced** (`is_all_caps_cue`):
	- Requiere al menos dos letras alfabéticas.
	- Todas las letras deben estar en mayúsculas (ignora signos/puntuación).
	- Ignora el contenido de overrides `{...}` para decidir.
- **full_to_forced_blocks**: un bloque entra si **todas** sus líneas cumplen el detector.

## API en código
```python
from srt_pipeline import SDHConfig, sdh_to_full_lines, full_to_forced_lines

cfg = SDHConfig(  # preset aggressive/netflix
		remove_between_square=True,
		remove_between_paren=True,
		between_only_if_separate_line=False,
		remove_text_before_colon=True,
		colon_only_if_uppercase=True,
		remove_if_only_music_symbols=True,
)

lines = [
		"[MUSIC PLAYING]",
		"(sigh)",
		"JOHN: Hi there",
		"Normal dialogue (leave this)",
		"♪ ♫",
]

full = sdh_to_full_lines(lines, cfg)  # -> ['Hi there', 'Normal dialogue']
forced = full_to_forced_lines(full)    # filtra cues en mayúsculas
```

## Consejos y solución de problemas
- Si la salida forced queda vacía, revisa que las líneas estén en mayúsculas; el detector ignora cues con una sola letra.
- En Windows/PowerShell, pon las rutas entre comillas si incluyen espacios.
- Si quieres conservar paréntesis inline, usa `--preset conservative` o `--between-only-if-separate-line`.

## Desarrollo
- Script único `srt_pipeline.py`, sin dependencias externas.
- Ejecuta `python srt_pipeline.py -h` para ver todas las opciones.

## Licencia
Consulta `LICENSE.md`.
