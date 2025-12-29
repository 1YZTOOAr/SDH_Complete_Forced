"""Pipeline para limpiar subtítulos SDH y generar versiones Full/Forced.

Modos disponibles (CLI y API):
- sdh_to_full: limpia SDH eliminando acotaciones según la configuración.
- full_to_forced: filtra un subtítulo limpio para quedarse con cues forzados (mayúsculas).
- sdh_to_forced: combina los dos pasos anteriores en un solo comando.

El script preserva etiquetas HTML, saltos `<br>`, overrides ASS `{...}` y saltos de linea
"""

from __future__ import annotations

import argparse
import dataclasses
import re
import sys
from pathlib import Path
from typing import Callable, Iterable, List


# Conjunto de símbolos musicales que indican cues no hablados
MUSIC_SYMBOLS = {"♪", "♫", "♬", "♩", "♭", "♯"}
# Patrones para preservar etiquetas/overrides antes de limpiar
BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
ASS_OVERRIDE_RE = re.compile(r"\{[^}]*\}")
ASS_NEWLINE_RE = re.compile(r"\\[Nn]")
# Forced detector regex: all caps (permit símbolos/espacios/dígitos) o override {\an8}
FORCED_RE = re.compile(r"^[A-ZÁÉÍÓÚÑÜ\s\d\W]+$|^\{\\an8\}")


@dataclasses.dataclass
class SDHConfig:
    """Configura las reglas de limpieza SDH.

    - remove_between_square / remove_between_paren: elimina contenido entre [] o ().
    - between_only_if_separate_line: solo elimina si la línea es solo el bloque.
    - remove_text_before_colon: elimina prefijos antes de ':' (speaker tags).
    - colon_only_if_uppercase: aplica la regla anterior solo si el prefijo está en mayúsculas.
    - remove_if_only_music_symbols: descarta líneas que solo contienen símbolos de música.
    """

    remove_between_square: bool = True
    remove_between_paren: bool = True
    between_only_if_separate_line: bool = False
    remove_text_before_colon: bool = True
    colon_only_if_uppercase: bool = True
    remove_if_only_music_symbols: bool = True


PRESETS: dict[str, SDHConfig] = {
    "aggressive": SDHConfig(),
    "netflix": SDHConfig(),
    "conservative": SDHConfig(
        between_only_if_separate_line=True,
    ),
}


SPEAKER_RE = re.compile(r"^\s*([A-ZÁÉÍÓÚÜÑ0-9 '\"&().-]{2,}):\s*(.+)$")


def _strip_speaker(line: str, cfg: SDHConfig) -> str:
    """Elimina el prefijo antes de ':' si coincide con un speaker tag."""
    if not cfg.remove_text_before_colon:
        return line
    match = SPEAKER_RE.match(line)
    if not match:
        return line
    speaker, rest = match.groups()
    if cfg.colon_only_if_uppercase and speaker != speaker.upper():
        return line
    return rest


def _only_music(line: str) -> bool:
    """True si la línea contiene únicamente símbolos musicales definidos."""
    stripped = line.strip()
    if not stripped:
        return False
    return all(char in MUSIC_SYMBOLS for char in stripped)


def _remove_inline_brackets(line: str, cfg: SDHConfig) -> str:
    """Elimina contenido entre [] o () cuando no se exige línea completa."""
    if cfg.remove_between_square and not cfg.between_only_if_separate_line:
        line = re.sub(r"\[[^\]]*\]", "", line)
    if cfg.remove_between_paren and not cfg.between_only_if_separate_line:
        line = re.sub(r"\([^)]*\)", "", line)
    return line


def _should_drop_line_for_brackets(line: str, cfg: SDHConfig) -> bool:
    """Descarta líneas que son solo un bloque []/() si así se configuró."""
    if not cfg.between_only_if_separate_line:
        return False
    stripped = line.strip()
    if cfg.remove_between_square and re.fullmatch(r"\[[^\]]*\]", stripped):
        return True
    if cfg.remove_between_paren and re.fullmatch(r"\([^)]*\)", stripped):
        return True
    return False


def clean_line(line: str, cfg: SDHConfig) -> str | None:
    """Limpia una línea SDH preservando etiquetas/overrides; devuelve None si se elimina."""
    if _should_drop_line_for_brackets(line, cfg):
        return None

    # proteger etiquetas/overrides antes de normalizar espacios
    placeholders: list[str] = []

    def _store(m: re.Match[str]) -> str:
        placeholders.append(m.group(0))
        return f"__TAG_{len(placeholders)-1}__"

    line = BR_TAG_RE.sub(_store, line)
    line = HTML_TAG_RE.sub(_store, line)
    # preserva cualquier override {\...} evitando que se elimine
    line = ASS_OVERRIDE_RE.sub(_store, line)
    line = ASS_NEWLINE_RE.sub(_store, line)

    line = _remove_inline_brackets(line, cfg)
    line = _strip_speaker(line, cfg)
    line = re.sub(r"\s+", " ", line).strip()

    if cfg.remove_if_only_music_symbols and _only_music(line):
        return None

    # restaurar etiquetas y saltos preservando el texto original
    for idx, original in enumerate(placeholders):
        line = line.replace(f"__TAG_{idx}__", original)

    return line


def sdh_to_full_lines(lines: Iterable[str], cfg: SDHConfig) -> List[str]:
    """Aplica limpieza SDH a múltiples líneas y devuelve las resultantes."""
    cleaned: List[str] = []
    for line in lines:
        result = clean_line(line.rstrip("\n"), cfg)
        if result:
            cleaned.append(result)
    return cleaned


def is_all_caps_cue(line: str) -> bool:
    """Detecta cues forced usando la regex FORCED_RE, exige ≥2 letras."""
    text = line.strip()
    if not text:
        return False
    if not FORCED_RE.fullmatch(text):
        return False

    # exigir al menos 2 letras alfabéticas en mayúsculas para evitar monosílabos
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 2:
        return False
    return all(c.isupper() for c in letters)


def full_to_forced_lines(lines: Iterable[str], cue_checker: Callable[[str], bool] | None = None) -> List[str]:
    """Filtra líneas dejando solo las que cumplen el detector de forced."""
    checker = cue_checker or is_all_caps_cue
    return [line for line in lines if checker(line)]


@dataclasses.dataclass
class SRTBlock:
    """Bloque SRT simple (índice, timing y textos)."""
    index: str
    timing: str
    texts: List[str]


def parse_srt(lines: Iterable[str]) -> List[SRTBlock]:
    """Parsea líneas en bloques SRT sin modificar el contenido de texto."""
    blocks: List[SRTBlock] = []
    buffer: List[str] = []
    for line in lines:
        if line.strip() == "":
            if buffer:
                blocks.append(_make_block(buffer))
                buffer = []
        else:
            buffer.append(line.rstrip("\n"))
    if buffer:
        blocks.append(_make_block(buffer))
    return blocks


def _make_block(lines: List[str]) -> SRTBlock:
    if len(lines) < 2:
        return SRTBlock(index="", timing="", texts=lines)
    index = lines[0]
    timing = lines[1]
    texts = lines[2:]
    return SRTBlock(index=index, timing=timing, texts=texts)


def format_srt(blocks: List[SRTBlock], renumber: bool = True) -> List[str]:
    """Convierte bloques SRT a líneas formateadas, renumerando si se desea."""
    output: List[str] = []
    counter = 1
    for block in blocks:
        if not block.texts:
            continue
        output.append(str(counter if renumber else block.index or counter))
        output.append(block.timing)
        output.extend(block.texts)
        output.append("")
        counter += 1
    return output


def sdh_to_full_blocks(blocks: Iterable[SRTBlock], cfg: SDHConfig) -> List[SRTBlock]:
    """Limpia textos de cada bloque SDH y descarta los vacíos."""
    cleaned_blocks: List[SRTBlock] = []
    for block in blocks:
        new_texts: List[str] = []
        for text in block.texts:
            cleaned = clean_line(text, cfg)
            if cleaned:
                new_texts.append(cleaned)
        if new_texts:
            cleaned_blocks.append(SRTBlock(index=block.index, timing=block.timing, texts=new_texts))
    return cleaned_blocks


def full_to_forced_blocks(blocks: Iterable[SRTBlock], cue_checker: Callable[[str], bool] | None = None) -> List[SRTBlock]:
    """Conserva bloques donde todas las líneas pasan el detector de forced."""
    checker = cue_checker or is_all_caps_cue
    forced: List[SRTBlock] = []
    for block in blocks:
        if block.texts and all(checker(_text_without_overrides(t)) for t in block.texts):
            forced.append(block)
    return forced


def _text_without_overrides(text: str) -> str:
    # Preserva el contenido con llaves en la salida, pero lo ignora al decidir mayúsculas
    return ASS_OVERRIDE_RE.sub("", text)


def _read_lines(path: Path | None) -> List[str]:
    """Lee líneas desde un archivo utf-8 o stdin si path es None."""
    if path is None:
        return [line.rstrip("\n") for line in sys.stdin]
    return path.read_text(encoding="utf-8").splitlines()


def _write_lines(path: Path | None, lines: List[str]) -> None:
    """Escribe líneas a disco (utf-8) o stdout si path es None."""
    text = "\n".join(lines) + ("\n" if lines else "")
    if path is None:
        print(text, end="")
    else:
        path.write_text(text, encoding="utf-8")


def _apply_overrides(cfg: SDHConfig, args: argparse.Namespace) -> SDHConfig:
    cfg = dataclasses.replace(cfg)

    if args.remove_between_square is not None:
        cfg.remove_between_square = args.remove_between_square
    if args.remove_between_paren is not None:
        cfg.remove_between_paren = args.remove_between_paren
    if args.between_only_if_separate_line is not None:
        cfg.between_only_if_separate_line = args.between_only_if_separate_line
    if args.remove_text_before_colon is not None:
        cfg.remove_text_before_colon = args.remove_text_before_colon
    if args.colon_only_if_uppercase is not None:
        cfg.colon_only_if_uppercase = args.colon_only_if_uppercase
    if args.remove_if_only_music_symbols is not None:
        cfg.remove_if_only_music_symbols = args.remove_if_only_music_symbols
    return cfg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Procesa subtítulos SDH → Full/Forced con reglas configurables (preserva etiquetas HTML/ASS)",
    )
    parser.add_argument(
        "--mode",
        choices=["sdh_to_full", "full_to_forced", "sdh_to_forced"],
        default="sdh_to_full",
        help="sdh_to_full: limpia SDH; full_to_forced: filtra forzados; sdh_to_forced: ambos pasos",
    )
    parser.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        default="aggressive",
        help="Preset base de limpieza (aggressive/netflix o conservative)",
    )
    parser.add_argument("-i", "--input", type=Path, help="Ruta del archivo de entrada (por defecto stdin)")
    parser.add_argument("-o", "--output", type=Path, help="Ruta del archivo de salida (por defecto stdout)")

    parser.add_argument(
        "--remove-between-square",
        dest="remove_between_square",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Eliminar texto dentro de []",
    )
    parser.add_argument(
        "--remove-between-paren",
        dest="remove_between_paren",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Eliminar texto dentro de ()",
    )
    parser.add_argument(
        "--between-only-if-separate-line",
        dest="between_only_if_separate_line",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Solo borrar bloques []/() si están en línea separada",
    )
    parser.add_argument(
        "--remove-text-before-colon",
        dest="remove_text_before_colon",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Eliminar texto antes de ':' (speaker tags)",
    )
    parser.add_argument(
        "--colon-only-if-uppercase",
        dest="colon_only_if_uppercase",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Aplicar la regla anterior solo si el prefijo está en mayúsculas",
    )
    parser.add_argument(
        "--remove-if-only-music-symbols",
        dest="remove_if_only_music_symbols",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Eliminar líneas que solo tengan símbolos de música",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = PRESETS[args.preset]
    cfg = _apply_overrides(cfg, args)

    lines = _read_lines(args.input)
    blocks = parse_srt(lines)

    if args.mode == "sdh_to_full":
        result_blocks = sdh_to_full_blocks(blocks, cfg)
    elif args.mode == "full_to_forced":
        result_blocks = full_to_forced_blocks(blocks)
    else:
        full_blocks = sdh_to_full_blocks(blocks, cfg)
        result_blocks = full_to_forced_blocks(full_blocks)

    output_lines = format_srt(result_blocks, renumber=True)
    _write_lines(args.output, output_lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
