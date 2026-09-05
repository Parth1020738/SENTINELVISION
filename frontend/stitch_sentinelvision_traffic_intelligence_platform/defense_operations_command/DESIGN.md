---
name: Defense Operations Command
colors:
  surface: '#10131a'
  surface-dim: '#10131a'
  surface-bright: '#363941'
  surface-container-lowest: '#0b0e15'
  surface-container-low: '#191b23'
  surface-container: '#1d1f27'
  surface-container-high: '#272a32'
  surface-container-highest: '#32353d'
  on-surface: '#e1e2ec'
  on-surface-variant: '#bec8d2'
  inverse-surface: '#e1e2ec'
  inverse-on-surface: '#2d3038'
  outline: '#88929b'
  outline-variant: '#3e4850'
  surface-tint: '#89ceff'
  primary: '#89ceff'
  on-primary: '#00344d'
  primary-container: '#0ea5e9'
  on-primary-container: '#003751'
  inverse-primary: '#006591'
  secondary: '#4edea3'
  on-secondary: '#003824'
  secondary-container: '#00a572'
  on-secondary-container: '#00311f'
  tertiary: '#ffb3ad'
  on-tertiary: '#68000a'
  tertiary-container: '#ff6c66'
  on-tertiary-container: '#6e000c'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#c9e6ff'
  primary-fixed-dim: '#89ceff'
  on-primary-fixed: '#001e2f'
  on-primary-fixed-variant: '#004c6e'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffdad7'
  tertiary-fixed-dim: '#ffb3ad'
  on-tertiary-fixed: '#410004'
  on-tertiary-fixed-variant: '#930013'
  background: '#10131a'
  on-background: '#e1e2ec'
  surface-variant: '#32353d'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 2rem
    fontWeight: '700'
    lineHeight: 2.5rem
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 1.5rem
    fontWeight: '600'
    lineHeight: 2rem
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 1.125rem
    fontWeight: '600'
    lineHeight: 1.5rem
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 0.875rem
    fontWeight: '600'
    lineHeight: 1.25rem
    letterSpacing: 0.02em
  body-lg:
    fontFamily: JetBrains Mono
    fontSize: 0.875rem
    fontWeight: '400'
    lineHeight: 1.375rem
    letterSpacing: 0em
  body-md:
    fontFamily: JetBrains Mono
    fontSize: 0.8125rem
    fontWeight: '400'
    lineHeight: 1.25rem
    letterSpacing: 0em
  body-sm:
    fontFamily: JetBrains Mono
    fontSize: 0.75rem
    fontWeight: '400'
    lineHeight: 1.125rem
    letterSpacing: 0em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 0.6875rem
    fontWeight: '600'
    lineHeight: 1rem
    letterSpacing: 0.08em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 0.625rem
    fontWeight: '600'
    lineHeight: 0.875rem
    letterSpacing: 0.1em
  code-telemetry:
    fontFamily: JetBrains Mono
    fontSize: 0.75rem
    fontWeight: '500'
    lineHeight: 1rem
    letterSpacing: 0.02em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  space-2xs: 0.125rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-base: 1rem
  space-lg: 1.25rem
  space-xl: 1.5rem
  space-2xl: 2rem
  gutter: 0.75rem
  panel-padding: 0.875rem
---

## Brand & Style

This design system delivers a disciplined defense-grade command terminal engineered for high-density surveillance, AI-assisted video telemetry, and continuous municipal situational awareness. The emotional profile is authoritative, cold, precise, and vigilantly operational. It eliminates ornamental flourish, speculative web3 glows, and gratuitous gradients in favor of absolute signal fidelity, structural contrast, and instant split-second comprehension under intense operational loads.

The visual style blends modern technical minimalism with tactical utility:
- **Disciplined Precision:** Information architecture favors tabular discipline, technical density, and strict 1px boundary definitions.
- **Instrument-First Ergonomics:** UI surfaces recede into matte, non-reflective deep charcoal and abyss-navy strata, ensuring high-priority optical alerts (critical breaches, vehicle track alerts, system degradations) achieve instantaneous visual pop.
- **Dual Typeform Hierarchy:** Inter provides rapid, clear scanning for macro operational controls, contextual groupings, and incident briefs; JetBrains Mono enforces columnar alignment and zero-ambiguity character differentiation for timestamps, vehicle license plates, speed telemetry, and geospatial coordinates.

## Colors

The color architecture is built strictly for dark-adapted mission control centers, tactical trailers, and real-time operations hubs. Backgrounds operate across precise charcoal-slate tiers to define structural elevation without light scattering.

### Surface System
- **Base Canvas (`#0A0D14`):** The primary non-reflective void background for root viewports and full-bleed camera arrays.
- **Panel Surface (`#101522`):** Primary structural surface for telemetry docks, sidebar controls, and data cards.
- **Raised/Modal Surface (`#161D2E`):** Secondary layer for flyout drawers, hovering contextual readouts, and dropdown inspection overlays.
- **Border/Structure (`#222F46`):** Precision 1px grid separator establishing tactical boundaries without visual glare.
- **Border Active/Focused (`#384E74`):** Elevated edge for active panels or focused tracking sectors.

### Tactical Accent Palette
- **System / Primary (`#0EA5E9`):** Tactical cyan-blue reserved for cursor reticles, primary active toggles, target locks, and confirmed operational routes.
- **Operational / Live (`#10B981`):** Verified green signifying clear nodes, live feeds, active engine inferences, and synchronized clock gates.
- **Critical Severity (`#EF4444`):** Pure emergency red reserved strictly for perimeter breaches, wrong-way vehicles, high-speed collisions, and hardware drops.
- **High Severity (`#F97316`):** Tactical amber indicating severe congestion, stalled vehicles in active lanes, and unregistered plates.
- **Medium Severity (`#FBBF24`):** Yellow alert for speed threshold warnings, pedestrian near-miss incursions, and weather-degraded optical sensors.
- **Info / Low Severity (`#06B6D4` / `#3B82F6`):** Subdued telemetry readouts, lane reassignment notifications, and routine tracking events.

### Monochromatic Signal Rules
- Text primary (`#F8FAFC`): 100% legibility for critical headings, license plate text, and active alert headers.
- Text secondary (`#94A3B8`): Subdued labels, sensor specifications, and inactive metadata.
- Text tertiary (`#475569`): Auxiliary grid labels, axis ticks, and unit notations.
- Under no circumstance should decorative gradients, pulsing bloom effects, or ambient neon blurs be deployed. Alerts must be crisp, high-contrast, and immediate.

## Typography

The typographic hierarchy balances instant structural scanning with zero-error technical accuracy.

### Font Pairing Rules
- **Inter (Headlines & Summaries):** Clean, neutral neo-grotesque sans-serif. Used for command bar headers, metric titles, modal headers, filter category titles, and executive incident summaries. It keeps dense interfaces calm and eliminates the fatigue associated with pure monospaced layouts.
- **JetBrains Mono (Telemetry, Readouts, System Logs):** Employed for all tabular rows, plate identifiers, confidence percentage scores, GPS coordinates, camera IDs, timestamps, and active status tags.
- **Tabular Figures (`tnum`):** All numbers throughout the UI must be rendered with tabular numerals enabled to ensure numerical values do not shift column alignment as values update in real time.
- **Uppercase Labels:** System-level telemetry descriptors (e.g., `LAT/LONG`, `FPS`, `CONFIDENCE`, `FEED_ID`, `STATUS`) must be rendered using `label-sm` or `label-md` with uppercase transformation and extended letter spacing (`0.08em` to `0.1em`).

## Layout & Spacing

The layout is built on a high-density, multi-panel workstation grid intended for 1080p, 1440p, 4K multi-monitor, and tactical terminal setups. The grid maximizes screen real estate while enforcing clean, unambiguous visual margins.

### Grid & Density Principles
- **Base Increment:** A strict 4px grid system (`0.25rem`). Standard telemetry rows use compact `28px` to `32px` vertical heights to display maximum operational rows without scrolling.
- **Command Layout Framework:**
  - **Top Utility Rail:** Fixed `44px` bar housing system health metrics, overall alert counters, global search/plate lookup, and coordinated UTC time display.
  - **Primary Feeds (Main Center):** Fluid multi-viewport (1x1, 2x2, 3x3, or 1+5 focus mode) maintaining aspect ratio with absolute 1px `#222F46` steel separation dividers.
  - **Telemetry Dock (Right/Left Rail):** Fixed `340px` to `420px` width. Modular, scrollable container stack containing event streams, AI detection logs, and sector controls.
  - **Timeline Scrubber (Bottom Drawer):** Fixed `48px` collapsed or `180px` expanded multi-track scrubber for multi-camera synchronous playback.
- **Responsive Adaptations:**
  - **Desktop / Multi-Monitor (>= 1440px):** Simultaneous multi-feed video matrix, persistent right telemetry log, and left tactical navigation rail.
  - **Laptop Workstation (1024px - 1439px):** Main feed grid with collapsible side rails and tabbed telemetry docks.
  - **Field Tablet (768px - 1023px):** Single active camera focus with overlay HUD toggles; telemetry panel converted into an off-canvas slide-out sheet.

## Elevation & Depth

This system avoids soft consumer drop shadows and floating skeuomorphic effects. Elevation is articulated through **tonal structural layering**, **subtle high-contrast outlines**, and **tactical depth offsets**.

### Elevation Stack
1. **Floor 0 (Canvas Void - `#0A0D14`):** Background layer for the camera stream canvas, map views, and inactive workspace edges.
2. **Floor 1 (Docked Containers - `#101522`):** Base panels, table containers, sidebar panes, and static command surfaces. Defined by a crisp `1px solid #222F46` border. No shadow.
3. **Floor 2 (Interactive & Hover Surfaces - `#161D2E`):** Active card states, hovered table rows, and selected camera tiles. Border increases in priority to `1px solid #384E74`.
4. **Floor 3 (Tactical Overlays & Drawers - `#161D2E`):** Contextual target cards, vehicle plate inspection drawers, and dropdown toolbars. Surface uses a crisp `1px solid #0EA5E9` (or relevant severity color) plus a controlled, non-diffuse ambient depth shadow: `0 8px 24px -4px rgba(0, 0, 0, 0.65)`.
5. **Floor 4 (Optical HUD Annotations):** Semi-transparent vector overlays directly on video streams (`rgba(10, 13, 20, 0.85)` with `backdrop-filter: blur(4px)`), framed with high-contrast tactical corner brackets.

## Shapes

The design system enforces a precision mechanical aesthetic with `roundedness: 1`. 
- Base elements (buttons, inputs, status pills, and list containers) utilize a tight `0.25rem` (`4px`) corner radius.
- Structural panels, video frames, and modals utilize `0.375rem` (`6px`) to `0.5rem` (`8px`) max corner radius (`rounded-lg`).
- Zero fully-rounded pill shapes are permitted for functional controls, reinforcing the tactical, instrumented feel of military and defense hardware consoles.
- Video overlays incorporate micro-notched or chamfered framing motifs, where target-bounding boxes display defined right-angle crosshair corners rather than rounded containers.

## Components

### Buttons & Action Triggers
- **Primary Action:** Background `#0EA5E9`, text `#0A0D14` (Inter 600, uppercase, tracking `0.05em`), border `1px solid transparent`, radius `4px`. Hover: background `#38BDF8`. Focus: outline `2px solid #0EA5E9` with 2px offset.
- **Tactical Secondary:** Background `#161D2E`, text `#F8FAFC`, border `1px solid #222F46`. Hover: border `#384E74`, background `#1E293B`.
- **Destructive / Emergency Lock:** Background `rgba(239, 68, 68, 0.12)`, text `#EF4444`, border `1px solid #EF4444`. Hover: background `#EF4444`, text `#FFFFFF`.
- **Button Group / Segmented Control:** Unified `1px solid #222F46` housing; active state sets background `#222F46` with primary cyan indicator pip.

### Telemetry Cards & Metric Panels
- Rigid `#101522` surface framed by `1px solid #222F46`.
- Header row contains micro label (`label-sm`, `#94A3B8`) and an operational status indicator (e.g., 6px solid circle: emerald for active, red for offline).
- Metric values rendered in `Inter` bold tabular numerals, accompanied by sub-metrics in `JetBrains Mono` (`#0EA5E9` or trend status colors).

### AI Bounding Boxes & Camera Overlays
- **Target Reticles:** Non-occluding 1.5px vectors directly over target objects (vehicles, pedestrians, cargo).
- **Corner Brackets:** 4-corner L-shaped reticle marks rather than enclosed continuous lines to maximize underlying visual clarity.
- **Bounding Tag:** Attached micro-hud at top-left of the bounding box: background `rgba(10, 13, 20, 0.9)`, border `1px solid [severity_color]`, font `JetBrains Mono 10px`, uppercase (`"SEDAN // PLATE: 7XYZ89 // CONF: 94.2%"`).

### Status Badges & Pills
- Compact rectangular chips (`4px` radius, padding `2px 6px`).
- Monospaced typography (`label-sm`, weight `600`).
- Background: 12% opacity tint of semantic color.
- Border: `1px solid` matching semantic hue at 40% opacity.
- Text: 100% semantic color value (e.g., Critical: `#EF4444`, Operational: `#10B981`, Amber: `#F97316`).

### Telemetry Tables & Incident Logs
- Header row: height `28px`, uppercase monospaced labels (`#475569`), bottom border `1px solid #222F46`.
- Data rows: height `32px` to `36px`, font `JetBrains Mono 12px`, alternating row striping forbidden; visual separation relies on `1px solid rgba(34, 47, 70, 0.5)` borders.
- Hover row state: background `#161D2E` with an absolute `2px` vertical cyan highlight along the leftmost edge.

### Inputs & Sensor Filters
- Background `#0A0D14`, border `1px solid #222F46`, font `JetBrains Mono 12px`, text `#F8FAFC`, placeholder `#475569`.
- Active focus: border `1px solid #0EA5E9`, box shadow `none`.
- Prefix/Suffix labels: `#94A3B8` enclosed in technical bracket syntax (e.g., `[CAM_ID]`, `[SPEED_GT]`).

### Modal Drawers & Inspection Sheets
- Right-aligned slide-out drawers (`480px` width) for deep plate inspection, vehicle trajectory analysis, and playback scrubbers.
- Background `#101522`, left border `1px solid #222F46`.
- Header contains close trigger (`ESC`), camera node identifier, and real-time synchronized UTC timestamp.