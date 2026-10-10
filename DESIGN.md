---
name: Cadence
description: A plain, precise control desk for event-call outreach; white work surfaces on pale grey, black ink, hairlines, one yellow highlight.
colors:
  canvas: "#f6f6f5"
  surface: "#ffffff"
  ink: "#111113"
  ink-2: "#3d3d42"
  muted: "#77777e"
  line: "#e5e5e7"
  line-soft: "#efeff1"
  brand-soft: "#f1f1f2"
  highlight-yellow: "#ffe53b"
  highlight-yellow-soft: "#fff7c2"
  signal-pink: "#e03a6b"
  signal-pink-soft: "#fde4ec"
  progress-purple: "#6a4fe0"
  good-green: "#1f9d55"
  bad-red: "#d2453a"
  warn-amber: "#a0650a"
  neutral-grey: "#7a7a82"
  unreached-grey: "#b9b9c0"
typography:
  display:
    fontFamily: "Hanken Grotesk, Noto Sans Malayalam, system-ui, sans-serif"
    fontSize: "clamp(44px, 6vw, 68px)"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Hanken Grotesk, Noto Sans Malayalam, system-ui, sans-serif"
    fontSize: "24px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Hanken Grotesk, Noto Sans Malayalam, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: "Hanken Grotesk, Noto Sans Malayalam, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Hanken Grotesk, Noto Sans Malayalam, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.5
rounded:
  chip: "5px"
  control: "6px"
  card: "8px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "20px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "#ffffff"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "{colors.ink-2}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.bad-red}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "20px"
  stat-cell:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    padding: "16px"
  badge:
    backgroundColor: "{colors.line-soft}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.chip}"
    padding: "2px 6px"
  nav-item-active:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  nav-count:
    backgroundColor: "{colors.highlight-yellow}"
    textColor: "{colors.ink}"
    rounded: "{rounded.chip}"
  sidebar:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-2}"
    width: "15.5rem"
---

# Design System: Cadence

## Overview

**Creative North Star: "The Plain Ledger"**

Cadence is a clean neutral product UI: white work surfaces on a pale grey ground, near-black ink, black primary buttons, hairline borders. Nothing is decorated. Colour is rationed so an organizer scanning between other tasks reads state before words: yellow marks the single thing to look at, pink means a person is needed, purple means in progress or open, green means settled.

Density is moderate and tabular. Cards are lightly rounded (8px) with a 1px line and no shadow. One typeface family (Hanken Grotesk, with Noto Sans Malayalam as a first-class companion) carries every role; hierarchy comes from size, weight and tight tracking, not from a second face. Motion explains cause and is disabled under `prefers-reduced-motion`.

The signature is the concentric-ring outcome chart (Pookalam), kept from the earlier identity but now drawn on plain white with grey tracks. The three-ring brand mark is a miniature of it.

**Key Characteristics:**
- Pale grey canvas, white surfaces, 1px hairline borders, no resting shadows.
- Black primary button, outlined secondary; underline tabs; tinted small status chips.
- Yellow = the one highlight; pink = needs a person; purple = in progress/open; green = settled.
- Light sidebar with collapsible sub-navigation, top bar with command search, event select and bell, then a breadcrumb row.
- Hanken Grotesk and Noto Sans Malayalam only.

## Colors

A monochrome ground with four meaningful signal colours.

### Primary
- **Ink Black** (`ink`): text, primary buttons, focus outline and caret, checked controls, selected tab rule. Hover step is **Ink 2** (`ink-2`).

### Secondary
- **Highlight Yellow** (`highlight-yellow`): the single highlight. Used for the nav count badge on the follow-up queue, the floor of the attending range, empty-state icon disc, text selection, input focus halo (55% mix), the "Acknowledged" ring and the warn chip tint (45%). Text on it is always Ink. **Highlight Yellow Soft** is its pale tint.
- **Signal Pink** (`signal-pink`): needs a person and nothing else: accented stat value with dot, the "Needs human" ring, the brand-mark inner ring. **Signal Pink Soft** is its tint.
- **Progress Purple** (`progress-purple`): open or in-progress (callback or info requested ring, info tone).

### Neutral
- **Canvas** (`canvas`): page ground, hover and active nav fill. **Surface** (`surface`): cards, top bar, sidebar, inputs.
- **Ink 2** and **Muted**: secondary text and captions/labels/table heads.
- **Line** and **Line Soft**: card borders, then inner dividers, skeleton and chip-neutral fill. **Brand Soft** is a rarely used pale fill.

### Status
- **Good Green**, **Bad Red**, **Warn Amber** (text on yellow tint), **Neutral Grey**, with Progress Purple as info. Rendered as coloured text on a 10% tint of itself (warn: yellow 45%). **Unreached Grey** colours the "Not reached" ring and hatch.

### Named Rules
**The One Highlight Rule.** Yellow marks the single thing to look at on a screen (count, range floor, empty icon). It is never a fill for large areas or a second action colour.

**The Pink Means A Person Rule.** Pink marks what needs a human and nothing else.

**The Meaning-Not-Mood Rule.** Tones come from `labels.ts`; ring colours come from `GROUPS` in `OutcomeChart.tsx`. Do not pick a tone ad hoc.

**The Hatch Rule.** An uncertain share of a bar is a diagonal grey hatch, meaning "not yet known".

## Typography

**Display Font / Body Font / Label Font:** Hanken Grotesk (with Noto Sans Malayalam, system-ui, sans-serif)

**Character:** Neutral and exact. One family; weight 600 for emphasis, 500 for labels, tight negative tracking on large sizes. Numbers are tabular everywhere.

### Hierarchy
- **Display** (600, clamp(44px, 6vw, 68px), 1, -0.03em): the attending range on the dashboard. Event title uses clamp(24px, 3vw, 34px).
- **Headline** (600, 24px, 1.25, -0.02em): page titles; stat values 28px; ring centre number 40px.
- **Title** (600, 14px): card and section headers; empty-state title 16px.
- **Body** (400, 14px, 1.5): default; subtitles 13.5px; tables 13px; inputs 13.5px.
- **Label** (500, 12 to 13px): buttons and tabs 13px, field labels 12.5px, muted stat labels and table heads 12px, chips 11.5px.

### Named Rules
**The Tabular Numbers Rule.** Counts and rates are tabular so strips and tables align.

**The Two-Script Rule.** Never clip or truncate Malayalam; give it line-height room (native uses 15px on 26px lines).

## Layout

Desktop is a sticky 15.5rem white sidebar plus a fluid column; below `md` the sidebar becomes a top block with a horizontally scrolling nav. The column stacks a sticky blurred top bar (command search left; event select and bell right), a white breadcrumb row (back arrow, parent, current page, event name), then content capped at max-w-6xl with 16px (32px from `md`) side padding and 28px top. Page sections sit 32px apart. Pages open with a bordered white overview card or a title row ruled by a 1px line, not a coloured band. Metrics sit in hairline-divided strips (cells split by 1px gaps inside one bordered frame), 2 columns on mobile and 3 to 4 from `md`. Tables scroll horizontally inside their card. Native uses a single centred column (max 880px) with 24px gaps and separate bordered stat cards.

## Elevation & Depth

Flat and tonal. Depth is canvas grey versus white surface plus a 1px line; cards have no shadow at rest. Only floating layers lift.

### Shadow Vocabulary
- **Floating panel** (`box-shadow: 0 12px 32px -12px rgba(17,17,19,.25)`): the command-search dropdown (and similar menus).
- **Focus halo** (`box-shadow: 0 0 0 3px color-mix(in srgb, #ffe53b 55%, transparent)`): focused input, with an ink border.

### Named Rules
**The Hairline-First Rule.** Separate regions with canvas/surface steps and 1px lines before reaching for a shadow.

## Shapes

Small, even radii: 6px controls (buttons, inputs, select, nav items), 8px cards and strips, 5px status chips and count badges, full-round only for dots, the empty-state disc and chart rings (round caps). Borders are always 1px (Line, then Line Soft inside cards). Recurring geometry is the circle: concentric rings and the three-ring mark.

## Components

Precise and quiet: black actions, outlined alternatives, tinted chips.

### Buttons
- **Shape:** 6px radius, 13px medium, 8px 14px padding.
- **Primary:** Ink fill, white text, hover Ink 2. **Secondary:** white, 1px near-ink border, hover Canvas. **Danger:** white, Bad Red text, 50% red border. **Ghost:** Ink 2 text, Line Soft hover.
- **Press:** `translateY(1px) scale(.985)`. Disabled: 45% opacity.

### Inputs / Fields
- 1px Line, white, 6px radius, 13.5px. Hover border ink at 40%; focus border Ink plus the yellow halo. Errors: 12px medium Bad Red text with `role="alert"`. Command search is a borderless Line Soft field that turns white with an ink border on focus.

### Cards / Containers
- 8px radius, 1px Line, white, 20px padding; header row 14px semibold over a Line Soft rule.

### Stat strip
- One bordered frame, cells separated by 1px rules; 12px muted label, 28px semibold value that counts up, 11.5px hint. Needs-a-person cell: pink value plus a pink dot. Linked cells hover to Canvas.

### Status chips
- 5px radius, dot plus label, 11.5px medium, coloured text on a 10% tint; no border.

### Tabs (Segmented)
- Underline tabs: 13px medium; selected is Ink with a 2px Ink rule, others Muted.

### Navigation
- White sidebar, 13.5px items, 6px radius. Active or open group: Canvas fill, semibold Ink. Groups (Campaigns, People) collapse to children indented under a 1px rule with a rotating chevron. A yellow count badge sits on Follow-up queue. Foot holds Settings and provider status dot. Breadcrumb row sits under the top bar.

### Pookalam chart (signature)
- SVG of concentric rings, 9px stroke, 15px step, round caps, each filled to its share of participants over a Line Soft track; colours from `GROUPS`; the key number (40px semibold) and a muted label at the centre; rings draw in with a staggered 1.1s ease-out. A legend with counts and the table beside it are the accessible reading.

### Empty state
- Yellow disc with an Ink icon, 16px semibold title, muted body.

## Do's and Don'ts

### Do:
- **Do** keep pages white-on-grey with 1px lines; radii at 5 / 6 / 8px.
- **Do** make the black primary button the single main action per view.
- **Do** use Pink only for items needing a human and Yellow for one highlight per area.
- **Do** show status as a tinted chip with dot and label, tone from `labels.ts`.
- **Do** give any outcome chart a table or legend with the same data.
- **Do** honor `prefers-reduced-motion`; mask phone numbers and mark simulated activity visibly.

### Don't:
- **Don't** add another saturated colour without a meaning to attach to it.
- **Don't** use yellow or pink as decoration or as large fills.
- **Don't** truncate or clip Malayalam text.
- **Don't** hard-code status colours outside the semantic set.
- **Don't** add resting card shadows or a second typeface.
