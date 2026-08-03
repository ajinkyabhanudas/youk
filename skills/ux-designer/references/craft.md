# Craft layer — the systems that separate competent from exceptional

Read during TEAM SESSION (Agent D — Craft) and CRAFT GATE.

The existing `patterns.md` and `cognition.md` cover whether an interface *works*.
This file covers whether it is *good*. Those are different questions, and most
design that passes the first fails the second.

---

## 0. The premise

Competent design is the absence of problems. Exceptional design is the presence
of a decision. An interface with no errors, no dead ends, and no confusion can
still be entirely forgettable — and forgettable is the failure mode this file
exists to prevent.

Everything below is a mechanism for forcing decisions where the default is drift.

---

## 1. Typography

Type is 90% of most interfaces. It is also the first place amateur work reveals
itself, because the defaults are all slightly wrong and nobody notices until
they see them corrected.

### 1.1 The scale

Never pick sizes ad hoc. Choose a ratio and derive every size from it.

| Ratio | Name | Feel | Use when |
|---|---|---|---|
| 1.200 | Minor third | Tight, dense | Data-heavy tools, dashboards |
| 1.250 | Major third | Balanced | General product UI |
| 1.333 | Perfect fourth | Editorial, spacious | Reading surfaces, documents |
| 1.414 | Augmented fourth | Dramatic | Marketing, landing pages |

Derive from a 16px base. A 1.25 scale gives: 10.24 / 12.8 / 16 / 20 / 25 / 31.25 /
39.06 / 48.83. Round to whole px and **stop** — if a size is not on the scale,
it does not exist.

> **Check:** count distinct font sizes in the spec. More than 6 means no system.
> Exactly 1–2 usually means insufficient hierarchy.

### 1.2 Weight

Two weights carry almost every interface. Three is the maximum before it reads
as noise.

Weight is a *stronger* hierarchy signal than size and it costs no vertical space.
Reach for weight before size when establishing emphasis in dense layouts.

Never use more than one weight for body-length text. Never fake bold with a
heavier colour, and never fake a heading by capitalising body text.

### 1.3 Measure (line length)

**45–75 characters for body text. 60 is the target.** This is not a preference;
it is a legibility finding that holds across languages and centuries of
typesetting.

A full-width paragraph on a 1440px viewport is roughly 180 characters and is
genuinely hard to read — the eye loses its place on the return sweep. Constrain
with `max-width: 65ch`, not with a pixel value.

### 1.4 Leading (line height)

| Content | Line height |
|---|---|
| Display / headings ≥32px | 1.05–1.2 |
| Body text | 1.5–1.65 |
| Dense UI labels, table cells | 1.3–1.4 |
| Long-form reading | 1.6–1.75 |

Leading is **inversely** proportional to size. Large text with body leading looks
loose and unresolved; small text with tight leading is unreadable. A single
`line-height: 1.5` applied globally is the signature of an unconsidered design.

### 1.5 Tracking (letter spacing)

Default tracking is tuned for body sizes. It is wrong everywhere else.

- Display text ≥32px: tighten, `-0.02em` to `-0.03em`. Large type looks gappy at
  default tracking.
- All-caps or small labels: loosen, `+0.05em` to `+0.1em`. Capitals need air.
- Body text: leave alone.

### 1.6 Numerals

Any interface showing numbers in a column MUST use tabular figures
(`font-variant-numeric: tabular-nums`). Proportional figures make columns jitter
and destroy scannability. This single line fixes a problem most people can see
but cannot name.

Use `font-feature-settings` for true small caps rather than transforming case.

---

## 2. Space

Space is the second system, and unlike type it is invisible when correct — which
is why it goes unexamined.

### 2.1 The spatial unit

Pick one base unit — 4px or 8px — and derive every gap, pad, and margin as a
multiple. A value off the grid is a bug.

An 8px base gives: 4 (half step) / 8 / 16 / 24 / 32 / 48 / 64 / 96 / 128.

> **Check:** any spacing value in the spec not on the scale is a defect, not a
> refinement.

### 2.2 Proximity encodes relationship

The single highest-leverage spatial rule: **space between groups must exceed
space within a group**, and by a clear factor, not a hair.

If a label sits 8px from its input, the next field must start at least 24px
below. When these are equal, the eye cannot parse structure and the user reads a
flat list of parts instead of a set of related things. Most "cluttered" interfaces
are actually just badly grouped.

### 2.3 Optical alignment

Mathematical centring is sometimes visually wrong. A triangular play icon centred
by its bounding box looks left-heavy and must shift right. Text next to a circular
avatar aligns to the text baseline, not the box.

Punctuation, bullets, and quote marks should hang outside the text block
(`text-indent` negative, or `hanging-punctuation`) so the text edge stays optically
straight.

### 2.4 Density is a decision

State it explicitly per surface: **comfortable** (generous padding, reading
surfaces), **compact** (dense tables, power users), or **responsive** (shifts by
breakpoint).

Never mix densities within one visual region. A comfortable card containing a
compact table reads as two designs colliding.

---

## 3. Colour

See the bundled `dataviz` skill for chart and series colour. This section covers
interface colour.

### 3.1 Build a ramp, not a palette

For each hue, define 9–11 steps from lightest to darkest, and reference only
those steps. Ad-hoc hex values are how interfaces drift into incoherence.

Semantic assignment, not literal naming: `--surface`, `--surface-raised`,
`--text-primary`, `--text-secondary`, `--border-subtle`, `--accent`. Never
`--blue-500` in component code, because the day the accent changes you edit
one token instead of 200 usages.

### 3.2 Restraint

**One accent colour.** Chrome in neutrals. If everything is emphasised, nothing is.

A second accent must earn its place semantically (destructive red, success green)
and must never be used decoratively.

> **Check:** count saturated colours in a single view. More than two, excluding
> data visualisation and user content, indicates decoration rather than meaning.

### 3.3 Contrast is a floor, not a target

WCAG AA (4.5:1 body, 3:1 large text) is the **minimum**. Passing it does not make
type comfortable. Secondary text at exactly 4.5:1 on a white surface is legally
accessible and still tiring to read.

Never signal state by colour alone — pair with icon, weight, or text.

### 3.4 Dark mode is not inversion

Mandatory rules:

- Never pure black (`#000`) surfaces. Use `#0a0a0b`–`#151517`. Pure black creates
  halation against light text and looks like a void, not a surface.
- Never pure white text. Use ~`#ededef` at 90% opacity equivalent. Full-white on
  near-black vibrates.
- **Elevation inverts.** In light mode, raised surfaces cast shadows. In dark
  mode, shadows are nearly invisible — raised surfaces get *lighter* instead.
- Saturated colours must be desaturated ~10–15% and lightened for dark surfaces,
  or they glow.
- Test both. A dark-mode screenshot is required before any spec is APPROVED.

---

## 4. Motion

Motion either explains a relationship or it is decoration. There is no third case.

### 4.1 Duration

| Change | Duration |
|---|---|
| Micro-feedback (hover, press) | 100–150ms |
| State change (toggle, reveal) | 200–300ms |
| Entering / exiting element | 250–400ms |
| Full page or view transition | 400–600ms |

Anything over 600ms feels broken regardless of how good it looks in isolation.
Users wait through animation on every single use; design for the thousandth
viewing, not the first.

### 4.2 Easing

- **Never `linear`** for anything spatial. Nothing physical moves at constant
  velocity, and it reads as mechanical.
- Entering: decelerate (`cubic-bezier(0.16, 1, 0.3, 1)`) — fast in, settle.
- Exiting: accelerate (`cubic-bezier(0.4, 0, 1, 1)`) — leave quickly, nobody is
  watching something go.
- Movement should ease; opacity may be linear.

### 4.3 Purpose test

Every animation answers: *what relationship does this explain?* A modal scaling
from the button that opened it explains origin. A list item sliding out explains
removal. A spinning logo explains nothing.

**`prefers-reduced-motion` is not optional.** Replace transforms with opacity
changes; never remove feedback entirely.

---

## 5. Depth and surface

### 5.1 Shadows model light

One light source, from above. Therefore: shadows fall downward, larger elevation
means larger *and softer* shadow, and a shadow with zero blur reads as a border.

Two-layer shadows read as real: a tight dark shadow for contact, a wide soft one
for ambient occlusion.

```
box-shadow:
  0 1px 2px rgba(0,0,0,0.06),
  0 8px 24px rgba(0,0,0,0.08);
```

Define 3–4 elevation levels and use only those. Shadows on shadows — a raised
card inside a raised panel inside a modal — flatten into mud.

### 5.2 Radius

Radius must be consistent per component class and should scale with size. A 4px
radius on a small button and a 4px radius on a large card look unrelated;
proportional radius reads as one family.

Nested radius: inner radius = outer radius − padding. Equal radii on nested
elements produce a visibly wrong gap at the corner.

### 5.3 Borders

Prefer a subtle border *or* a shadow, rarely both. `1px solid rgba(0,0,0,0.08)`
usually does what a heavy grey border does, without the visual weight.

---

## 6. The unified idea

The hardest and least mechanical requirement.

**Every screen has exactly one thing it is for.** That thing gets the strongest
position, the most contrast, and the most space. Everything else is subordinate
and visibly so.

Interfaces fail this in a specific way: every element is defensible in isolation,
and together they have no centre. The reviewer's eye lands nowhere first. This is
the most common failure in otherwise-competent work and it is why "it's fine but
forgettable" happens.

> **Check — the squint test:** blur the layout until text is illegible. What is
> still clearly dominant? If the answer is "nothing" or "the wrong thing", the
> hierarchy is decorative rather than structural.

> **Check — the removal test:** for each element, ask what breaks if it is
> deleted. If nothing breaks, delete it. Run this until every remaining element
> is load-bearing. Most interfaces survive losing 20–30% of their elements and
> improve for it.

---

## 7. Defaults that reveal amateur work

A rapid audit list. Each is individually small and collectively decisive.

| Default | Why it is wrong | Fix |
|---|---|---|
| System font stack unexamined | Fine, but unconsidered — verify it suits the content | State the decision explicitly |
| `line-height: normal` on headings | Too loose at display sizes | 1.05–1.2 |
| Default tracking on large type | Looks gappy | −0.02em |
| Proportional numerals in tables | Columns jitter | `tabular-nums` |
| Full-width body text | Exceeds 75ch, hard to read | `max-width: 65ch` |
| Pure black / pure white | Harsh, halates | Near-black / near-white |
| `linear` easing | Reads mechanical | Cubic-bezier |
| Uniform spacing everywhere | No grouping information | Proximity hierarchy |
| Placeholder as label | Vanishes on focus, fails a11y | Persistent label |
| Icon-only buttons, no label | Ambiguous, fails a11y | Label or `aria-label` + tooltip |
| Focus ring removed | Breaks keyboard use | Style it, never remove |
| Disabled buttons with no reason | User is stuck with no explanation | Explain the condition |
| Centred body paragraphs | Ragged left edge kills scannability | Left-align |
| Text over busy imagery, no scrim | Fails contrast unpredictably | Scrim or solid surface |

---

## 8. Reading surfaces

Load when the primary job is *reading* rather than *operating* — documents,
reports, evidence, long-form output.

Reading surfaces have different rules from tools, and applying tool conventions
to a reading surface is a common and serious error.

- Measure discipline is non-negotiable: 60–70ch.
- Vertical rhythm: paragraph spacing should relate to line height (e.g. `1em`
  margin at `1.6` leading), producing an even grey texture.
- Generous leading, 1.6–1.75.
- **Fewer, larger** type sizes than a tool UI. Reading surfaces need less
  hierarchy, not more.
- Tables and figures are set *within* the measure, or deliberately break it
  full-bleed — never accidentally 10% wider.
- Time-to-first-word matters: no interstitial, no animation before content, no
  layout shift.
