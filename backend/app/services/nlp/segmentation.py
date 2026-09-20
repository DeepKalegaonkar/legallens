import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class _Unit:
    start: int
    end: int
    text: str
    parent: str


_PAGE_MARKER = re.compile(r"^[ \t]*page\s+\d+\s+of\s+\d+[ \t]*$", re.IGNORECASE | re.MULTILINE)
_BLANK_FIELD = re.compile(r"_{3,}")

# A line that starts a new clause: "8. Heading", "8.1 text", "(a) text",
# "A. text", "Section 3", "ARTICLE IV", or an ALL-CAPS heading line.
_CLAUSE_START = re.compile(
    r"""^[ \t]*(?:
        \d{1,2}\.[ \t]+\S
      | \d{1,2}(?:\.\d{1,2})+\.?[ \t]+\S
      | \([ \t]*(?:[a-z]|[ivx]{1,4}|\d{1,2})[ \t]*\)[ \t]+\S
      | (?-i:[A-Z]\.)(?:[ \t]+\S|(?=[A-Z][a-z]))
      | (?:section|article)[ \t]+[\dIVXLC]+
      | (?-i:[A-Z][A-Z0-9 ,&'/()-]{3,90})[ \t]*$
    )""",
    re.IGNORECASE | re.VERBOSE,
)
_LEADING_NUMBER = re.compile(r"^\s*(?:(\d{1,2}(?:\.\d{1,2})+)\.?|(\d{1,2})\.)\s+")
_SUBCLAUSE_LABEL = re.compile(r"^\(\s*([a-z]|[ivx]{1,4}|\d{1,2})\s*\)\s*", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\[\"'])")

# Clauses longer than this are cut at sentence boundaries into chunks of about TARGET.
MAX_CLAUSE_CHARS = 1500
TARGET_CHUNK_CHARS = 900
# Pieces with fewer letters than this (stray headers, page furniture) aren't clauses.
MIN_LETTERS = 40
# A short line that is mostly underscores ("Signed: ______") is a fill-in field, not text.
FILL_LINE_RATIO = 0.4
FILL_LINE_MAX_WORDS = 8
# A short unit that doesn't end a sentence is a heading or introduction.
HEADING_MAX_CHARS = 100


def slugify(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def split_into_clauses(document_text: str) -> list[str]:
    """Best-effort segmentation of raw contract text into individual clauses.

    Clauses start at numbered headings ("8.", "8.1"), lettered or bracketed
    sub-points ("(a)", "A."), "Section"/"ARTICLE" lines, ALL-CAPS headings and
    blank lines. Sub-points are labelled with their parent number ("6(c) ..."),
    headings are attached to the text that follows them, very long clauses are
    cut at sentence boundaries, and page markers, blank fill-in fields and
    signature-line fragments are cleaned out.
    """
    return [piece.text for piece in segment(document_text)]


def segment(document_text: str) -> list[Segment]:
    """Like split_into_clauses, but keeps each clause's character offsets in the input."""
    working = _blank_out_noise(document_text)
    units = _label_parents(_units(working), working)

    segments: list[Segment] = []
    index = 0
    while index < len(units):
        unit = units[index]
        follower = units[index + 1] if index + 1 < len(units) else None
        if follower is not None and _is_heading(unit.text):
            index += 1
            if _starts_with_marker(follower.text):
                # The follower carries its own number/label, so the heading is only a lead-in.
                continue
            units[index] = _Unit(unit.start, follower.end, unit.text + " " + follower.text, unit.parent)
            continue
        segments.extend(_emit(unit, working))
        index += 1
    return segments


def _units(working: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start: int | None = None
    last_end = 0
    position = 0
    for line in working.splitlines(keepends=True):
        line_start = position
        position += len(line)
        if not line.strip():
            if start is not None:
                spans.append((start, last_end))
                start = None
            continue
        if start is not None and _CLAUSE_START.match(line):
            spans.append((start, last_end))
            start = None
        if start is None:
            start = line_start + len(line) - len(line.lstrip())
        last_end = line_start + len(line.rstrip())
    if start is not None:
        spans.append((start, last_end))
    return spans


def _label_parents(spans: list[tuple[int, int]], working: str) -> list[_Unit]:
    units: list[_Unit] = []
    parent = ""
    for start, end in spans:
        text = _normalize(working[start:end])
        number = _LEADING_NUMBER.match(text)
        if number:
            parent = number.group(1) or number.group(2)
        units.append(_Unit(start, end, text, parent))
    return units


def _blank_out_noise(text: str) -> str:
    """Overwrite page markers and signature/fill-in lines with spaces, keeping offsets intact."""
    text = _PAGE_MARKER.sub(lambda match: " " * len(match.group()), text)
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.count("_") > FILL_LINE_RATIO * len(stripped) and len(stripped.split()) <= FILL_LINE_MAX_WORDS:
            lines[index] = re.sub(r"[^\r\n]", " ", line)
    return "".join(lines)


def _starts_with_marker(text: str) -> bool:
    return bool(_LEADING_NUMBER.match(text) or _SUBCLAUSE_LABEL.match(text))


def _emit(unit: _Unit, working: str) -> list[Segment]:
    segments = []
    for chunk_start, chunk_end in _chunks(working, unit.start, unit.end):
        text = _normalize(working[chunk_start:chunk_end])
        if chunk_start == unit.start:
            text = _with_parent_label(text, unit.parent)
        if _has_content(text):
            segments.append(Segment(text, chunk_start, chunk_end))
    return segments


def _with_parent_label(text: str, parent: str) -> str:
    label = _SUBCLAUSE_LABEL.match(text)
    if label and parent:
        return f"{parent}({label.group(1).lower()}) {text[label.end():]}"
    return text


def _chunks(working: str, start: int, end: int) -> list[tuple[int, int]]:
    if end - start <= MAX_CLAUSE_CHARS:
        return [(start, end)]

    text = working[start:end]
    chunks: list[tuple[int, int]] = []
    chunk_start = 0
    previous_cut = None
    for match in _SENTENCE_END.finditer(text):
        cut = match.end()
        if cut - chunk_start > TARGET_CHUNK_CHARS and previous_cut is not None:
            chunks.append((chunk_start, previous_cut))
            chunk_start = previous_cut
        previous_cut = cut
    chunks.append((chunk_start, len(text)))
    return [(start + a, start + b) for a, b in chunks if text[a:b].strip()]


def _is_heading(text: str) -> bool:
    return len(text) < HEADING_MAX_CHARS and not text.rstrip().endswith((".", ";"))


def _normalize(text: str) -> str:
    text = _BLANK_FIELD.sub("___", text)
    return re.sub(r"\s+", " ", text).strip()


def _has_content(text: str) -> bool:
    return len(re.findall(r"[A-Za-z]", text)) >= MIN_LETTERS
