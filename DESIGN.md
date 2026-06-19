# Design System Specification: The Academic Curator

## 1. Overview & Creative North Star
The research funding landscape is often cluttered with dense information and rigid, antiquated portals. This design system departs from the "form-filler" aesthetic to embrace **"The Digital Curator."** 

The Creative North Star is an editorial-first approach that treats research grants not as database entries, but as curated opportunities. We achieve this through **high-contrast typography scales**, **intentional white space**, and a **layered tonal architecture**. The goal is an "Institutional Editorial" feel: the authority of a prestigious university combined with the clarity and breathability of a high-end digital publication. We break the standard grid by using asymmetric sidebar positioning and overlapping surface tiers to guide the researcher’s eye toward high-priority funding.

---

## 2. Colors
Our palette is anchored in deep, authoritative blues and high-fidelity neutrals. It moves beyond "standard corporate" by utilizing sophisticated tonal transitions rather than flat fills.

### Color Roles
- **Primary (`#002045`)**: Used for high-level branding, primary navigation, and "Must-See" grant categories. It represents the "Institutional" anchor.
- **Tertiary (`#00213e`) & Tertiary Container (`#003762`)**: These provide a sophisticated depth for secondary accents, specifically in the filtering sidebar to distinguish it from the content feed.
- **Functional Accents**: `error` (`#ba1a1a`) is reserved strictly for urgent deadlines and critical status alerts.

### The "No-Line" Rule
**Explicit Instruction:** Traditional 1px solid borders (`#c4c6cf`) are prohibited for sectioning. Structural boundaries must be defined solely through background shifts.
*   *Example:* A `surface-container-low` section sitting directly on a `background` fill.
*   *Why:* Borders create visual "noise" that interrupts the flow of academic reading.

### The "Glass & Gradient" Rule
To elevate CTAs and Hero sections:
- **CTAs:** Use a subtle linear gradient from `primary` (`#002045`) to `primary_container` (`#1a365d`) at a 135-degree angle. This provides a "jewel-like" depth.
- **Glassmorphism:** Floating elements (like "Back to Top" buttons or active filter pills) should use `surface_container_lowest` with an 80% opacity and a `20px` backdrop-blur.

---

## 3. Typography
We utilize a dual-font strategy to balance character with extreme readability.

- **Display & Headlines (Manrope)**: A contemporary sans-serif with geometric foundations. Used for `display-lg` through `headline-sm`. These should be set with tight letter-spacing (-0.02em) to feel authoritative and "editorial."
- **Body & Labels (Inter)**: The industry standard for legibility. Used for all `title`, `body`, and `label` scales. Inter’s tall x-height ensures that complex grant descriptions remain scannable at small sizes.

**Identity through Hierarchy:** Use `display-md` (2.75rem) for section headers to create a "Signature" scale difference between the header and the `body-md` content. This high-contrast scale is the hallmark of a premium experience.

---

## 4. Elevation & Depth
In this system, depth is a function of **Tonal Layering**, not geometry.

- **The Layering Principle:** Treat the UI as stacked sheets of fine paper. 
    - Base Level: `surface` (`#f7fafc`)
    - Layout Sections (Sidebar/Feed): `surface-container-low` (`#f1f4f6`)
    - Grant Cards: `surface-container-lowest` (`#ffffff`)
- **Ambient Shadows:** Shadows are rare. When a card requires a "lift" on hover, use an extra-diffused shadow: `offset-y: 8px, blur: 24px, color: rgba(24, 28, 30, 0.06)`. Note the use of `on_surface` as the shadow tint rather than pure black.
- **The "Ghost Border" Fallback:** For accessibility in input fields, use `outline_variant` at **15% opacity**. Never use a 100% opaque border.

---

## 5. Components

### Cards & Lists
*   **Grant Cards**: Must use `surface-container-lowest`. 
*   **Prohibition**: No dividers. Separate content using the `xl` (0.75rem) spacing or a shift to `surface-container-low`.
*   **Status Tags**: 
    - *High Priority*: `error_container` text on `on_error_container` background.
    - *Medium*: `secondary_fixed` background.
    - *General*: `surface_variant` background.

### Buttons
*   **Primary**: `primary` background with `on_primary` text. `xl` (0.75rem) roundedness.
*   **Secondary**: `secondary_container` background. No border.
*   **Tertiary**: Ghost style—text only using `primary` token, with a `surface_container_high` background on hover.

### Filtering Sidebar
*   **Structure**: Uses `surface_container_low` to anchor the left side of the viewport. 
*   **Filter Chips**: Use `roundedness.full`. Unselected: `surface_variant`. Selected: `primary` with `on_primary` text.

### Input Fields
*   **Styling**: Use `surface_container_highest` for the field fill to create a "recessed" look. Label should use `label-md` in `on_surface_variant`.

---

## 6. Do's and Don'ts

### Do
- **DO** use asymmetric layouts. If the grant list is center-aligned, allow the sidebar to sit slightly further to the left to create breathing room.
- **DO** use `surface_bright` for main content areas to keep the "Institutional" feel fresh and modern.
- **DO** emphasize the "Deadline" using the `error` token only when the date is < 48 hours away.

### Don't
- **DON'T** use 1px dividers between list items; use `0.5rem` of vertical space instead.
- **DON'T** use pure black `#000000`. Use `on_surface` (`#181c1e`) for all primary text to maintain a sophisticated, soft-contrast look.
- **DON'T** use sharp corners. Every interactive element must have at least `md` (0.375rem) roundedness to feel approachable.