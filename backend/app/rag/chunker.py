"""
rag/chunker.py - split the expense-policy document into chunks (owner: Piyush, M2).

Rules (Agile Spec v2.0, "Expense-policy RAG"):
  * A chunk starts at a line beginning with [POL-, [GUIDE- or [FAQ-. One rule = one chunk,
    and its id (e.g. POL-6.2) is the citation Vera shows.
  * A chunk ends at the next rule line or at a section separator (----- / =====).
  * Each chunk's content is prefixed with its section header, so the embedding knows the context.
  * Rules longer than 800 characters are split with 100 characters of overlap (chunk_index 0, 1 ...).
Pure functions: no I/O, easy to unit-test.
"""
import hashlib
import re
from dataclasses import dataclass

RULE_LINE = re.compile(r"^\[((?:POL|GUIDE|FAQ)-[\d.]+)\]\s*(.*)$")   # "[POL-6.2] Review thresholds ..."
SECTION_LINE = re.compile(r"^SECTION\s+\d+\s*-\s*(.+)$")              # "SECTION 6 - EXPENSE CATEGORIES ..."
SEPARATOR = re.compile(r"^[-=]{10,}")                                 # "-------" or "======" lines

MAX_CHARS = 800
OVERLAP = 100


@dataclass
class Chunk:
    ref_id: str          # citation id, e.g. "POL-6.2"
    section_title: str   # rule title, e.g. "Review thresholds per expense line"
    chunk_index: int
    content: str         # section header + "[ref] title" + rule text

    @property
    def content_hash(self) -> str:
        """sha256 of the text: same text -> same hash, so ingestion can skip unchanged chunks."""
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def _split_long(body: str) -> list[str]:
    """Cut a long rule into ~800-character windows that overlap by 100 characters,
    moving each cut back to the previous space so words are not broken."""
    if len(body) <= MAX_CHARS:
        return [body]
    parts, start = [], 0
    while start < len(body):
        end = min(start + MAX_CHARS, len(body))
        if end < len(body):
            space = body.rfind(" ", start + OVERLAP + 1, end)
            end = space if space > 0 else end
        parts.append(body[start:end].strip())
        if end >= len(body):
            break
        # next window starts ~100 characters back, at the start of a word
        space = body.find(" ", end - OVERLAP, end)
        start = space + 1 if space != -1 else end - OVERLAP
    return parts


def chunk_policy(text: str) -> list[Chunk]:
    """Parse the whole document and return its chunks in document order."""
    chunks: list[Chunk] = []
    section = ""
    current: tuple[str, str] | None = None     # (ref_id, title) of the rule being read
    body: list[str] = []

    def flush() -> None:
        # Close the rule being read and turn it into one or more chunks.
        if current is None:
            return
        ref_id, title = current
        rule_text = "\n".join(body).strip()
        for i, part in enumerate(_split_long(rule_text)):
            header = f"{section}\n[{ref_id}] {title}".strip()
            chunks.append(Chunk(ref_id=ref_id, section_title=title, chunk_index=i,
                                content=f"{header}\n{part}".strip()))

    for raw in text.splitlines():
        line = raw.rstrip()
        rule = RULE_LINE.match(line)
        if rule:                                  # a new rule starts
            flush()
            current, body = (rule.group(1), rule.group(2).strip()), []
        elif SEPARATOR.match(line):               # end of a section block
            flush()
            current, body = None, []
        elif (sec := SECTION_LINE.match(line)) and current is None:
            section = f"Section: {sec.group(1).strip().title()}"
        elif current is not None:
            body.append(line)
    flush()
    return chunks
