# Canonical Resume Object Model

## Problem

The export pipeline is text-centric. Exporters are forced to infer document semantics from damaged flat text:

- Is this a bullet or a wrapped continuation?
- Is this prose or a list?
- Is this a grouped skills line or paragraph text?
- Is this summary content or orphaned text?

Patching rendering first improves symptoms but duplicates guessing logic across TXT/PDF/DOCX exporters.

## Architecture

```
extraction text → normalization → semantic document model → renderers
```

Instead of:

```
extraction text → renderer guesses what this meant
```

## Implementation Order

### 1. Define the canonical resume object model

Explicitly represent:
- Section type and order
- Entry kind (discriminated, not polymorphic)
- Bullet items as arrays of logical bullets, not raw newline blobs
- Paragraph/prose blocks
- Summary/profile block
- Skills groups with display intent (advisory, not authoritative)
- Structured provenance and normalization events
- Semantic dates with partial date support

### 2. Add a normalization layer

Standalone module (`backend/services/resume_normalizer.py`), not inside ExportService.

Solve:
- Continuation-line joining (multi-line bullets → single logical bullet)
- Pipe-delimited skills parsing (`| Python | Bash |` → grouped skills)
- Category detection
- PDF extraction cleanup (e.g., "Pr esent" → "Present", "customer -ready" → "customer-ready")
- Whitespace/hyphen artifact normalization where safely possible

Converts messy extracted content into the canonical structure.

### 3. Make exporters dumb

Exporters just render from `ResumeDocument`:
- Summary → prose paragraphs
- Experience → structured entries with bullet lists
- Skills → grouped inline lists or categorized lines
- Certifications → compact list entries

Exporters should not be deciding document meaning.

## Model

All models are **Pydantic** for validation, serialization, artifact persistence, and debugging.

### Top-level

```python
class ResumeDocument(BaseModel):
    basics: Basics
    sections: list[Section]  # ordered by Section.order
    metadata: DocumentMetadata
```

### Basics

```python
class Basics(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    headline: str | None = None  # one-line professional headline
```

### Section

```python
class SectionCategory(str, Enum):
    summary = "summary"
    skills = "skills"
    experience = "experience"
    education = "education"
    certifications = "certifications"
    projects = "projects"
    awards = "awards"
    other = "other"

class Section(BaseModel):
    category: SectionCategory
    heading: str              # display heading (may differ from category)
    entries: list[Entry]
    order: int
```

Section category is a semantic bucket. It guides defaults but does not rigidly determine entry shape. A `projects` section may contain structured headers + bullets. An `education` section may contain structured entries + optional honors as items.

### Entry (discriminated union)

```python
class EntryKind(str, Enum):
    experience = "experience"
    prose = "prose"
    skills = "skills"
    list_items = "list"
    education = "education"
    project = "project"

class EntryHeader(BaseModel):
    title: str | None = None           # job title, degree, project name
    organization: str | None = None    # company, school
    location: str | None = None
    start_date: PartialDate | None = None
    end_date: PartialDate | None = None
    is_current: bool = False           # semantic "Present", not textual

class Entry(BaseModel):
    kind: EntryKind
    header: EntryHeader | None = None
    content: EntryContent              # discriminated union
    source: SourceProvenance | None = None
```

### EntryContent (true discriminated union)

```python
class BulletsContent(BaseModel):
    type: Literal["bullets"] = "bullets"
    bullets: list[str]  # each bullet is a single logical string, continuation-joined

class ProseContent(BaseModel):
    type: Literal["prose"] = "prose"
    paragraphs: list[str]

class SkillsContent(BaseModel):
    type: Literal["skills"] = "skills"
    groups: list[SkillsGroup]

class ItemsContent(BaseModel):
    type: Literal["items"] = "items"
    items: list[str]  # simple list (certs, awards, honors)

EntryContent = Annotated[
    BulletsContent | ProseContent | SkillsContent | ItemsContent,
    Field(discriminator="type")
]
```

### SkillsGroup

```python
class SkillsGroup(BaseModel):
    label: str | None = None     # e.g., "Technical Proficiencies", "Key Skills"
    items: list[str]             # individual skills
    display_style: str = "inline"  # advisory render hint: "inline", "list", "chips"
```

`display_style` is a **render hint**, not a semantic identity. Exporters may degrade gracefully if the style is unsupported.

### PartialDate

```python
class PartialDate(BaseModel):
    year: int | None = None
    month: int | None = None
    day: int | None = None
    raw_text: str | None = None  # preserve original text (e.g., "September 2021")
```

"Present" is not a date — it is represented by `EntryHeader.is_current = True` with `end_date = None`. Renderers choose how to display this.

### Provenance

```python
class SourceProvenance(BaseModel):
    source_block_id: int | None = None
    source_section_hint: str | None = None
    source_text: str | None = None       # raw text before normalization
    line_start: int | None = None
    line_end: int | None = None
    confidence: float | None = None
```

### Normalization events

```python
class NormalizationEvent(BaseModel):
    rule_id: str                  # e.g., "bullet_continuation_join", "skills_pipe_parse"
    description: str
    before: str | None = None
    after: str | None = None
    severity: str = "info"        # "info" or "warning"

class DocumentMetadata(BaseModel):
    source_filename: str | None = None
    extraction_method: str | None = None   # "llm", "stub", "manual"
    extraction_warnings: list[str] = []
    normalization_events: list[NormalizationEvent] = []
    generated_at: str | None = None
```

## Model Invariants

- `ResumeDocument.sections` must be ordered and stable (by `Section.order`)
- Every `Entry` must contain exactly one `content` payload type (enforced by discriminated union)
- `summary` sections should only contain `prose` entries
- `skills` sections should only contain `skills` entries
- `experience` entries should have at least one of `title` or `organization` in header
- Bullet content must already be continuation-joined before rendering
- Renderers must not mutate semantic content
- Normalization must be idempotent on already-normalized input

## Normalization Rules

### Bullet continuation joining
Lines following a bullet that don't start with a bullet character are continuations:
```
● Serve as primary support contact for strategic FlashArray customers, specializing in root-cause
analysis, timeline forensics, and triage of complex break/fix issues
```
→ single bullet: `"Serve as primary support contact for strategic FlashArray customers, specializing in root-cause analysis, timeline forensics, and triage of complex break/fix issues"`

### Skills parsing
```
| Python | Bash | JSON | YAML | Windows | Linux |
```
→ `SkillsGroup(label=None, items=["Python", "Bash", "JSON", "YAML", "Windows", "Linux"], display_style="inline")`

### Summary as prose
Summary/profile blocks → `Entry(kind="prose", content=ProseContent(paragraphs=[...]))`, never bullets.

### PDF extraction artifact cleanup
- `"Pr esent"` → `"Present"` (broken word joins)
- `"customer -ready"` → `"customer-ready"` (spurious spaces before hyphens)
- Every cleanup recorded as a `NormalizationEvent`, not silently applied

### Section detection
Category guides default content type:
- `summary` → prose
- `experience` → structured header + bullets
- `education` → structured header + optional bullets or prose
- `skills` → skills_groups
- `certifications` → items list
- `awards` → items list
- `projects` → structured header + bullets
- `other` → prose or items (infer from content)

Section category guides defaults, but entries may use any appropriate content type.

## Normalization Non-Goals

Normalization does **not**:
- Rewrite content for style or tone
- Infer missing facts or achievements
- Invent dates, roles, or organizations
- Reorder sections unless explicitly configured
- Aggressively "correct" ambiguous OCR/PDF damage without recording it as a `NormalizationEvent`
- Apply prompt-like behavior (no creative rewriting)

## Normalization Scope Boundaries

Normalization **should**:
- Join continuation lines
- Collapse safe extraction artifacts (with traceability)
- Parse grouped skill delimiters
- Classify section content type
- Preserve source provenance for every entry

## What to Avoid

Do NOT:
- Patch DOCX bullets separately from PDF bullets
- Add special cases for skills in HTML only
- Add special cases for summary in PDF only
- Keep TXT as accidental source of truth
- Let exporters contain normalization logic
- Let the model absorb layout concerns (fonts, spacing, pagination)

## Architectural Decisions

### Normalization location
**Standalone module**: `backend/services/resume_normalizer.py`

Not inside ExportService. Normalization is independently testable and feeds every renderer the same canonical object. It may later serve preview, editing, diffing, validation, and persistence.

### Model framework
**Pydantic models** for validation, serialization, artifact persistence, and predictable error surfaces.

### Persistence
**Persist normalized documents as artifacts** (`derived/resume_document.json`).

Artifact chain:
1. Raw extracted blocks (in DB)
2. Normalized `resume_document.json` (artifact)
3. Rendered outputs (PDF, DOCX, TXT)

Enables: debuggability, reproducibility, diffing before/after normalization, stable export inputs, regression testing.

### Tailor step integration
The tailor step should ultimately produce or update a canonical `ResumeDocument`, not raw text that gets normalized again downstream.

Best flow:
1. Source resume extraction → normalization → canonical base resume
2. Tailor step operates on canonical structure
3. Tailored result emits canonical structure
4. Exporters render canonical tailored document

ATS text may remain as an intermediate artifact, but it should not be the final semantic source of truth.
