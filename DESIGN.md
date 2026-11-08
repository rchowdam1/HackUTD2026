# CallSafe design system: "Light Mirror"

The console's visual language. It is a light, magenta-accented take on the Hallway Mirror look: thin display type, hairline rules instead of cards, small mono labels and big numbers. Mockup: https://claude.ai/artifact/C8mLFnA88C6AMQKiQp8kgD (private until shared).

The console is read from about 2 m away at a judging table, so the important things are large and everything else steps back.

## Principles

1. **One accent, one meaning.** Magenta marks the request CallSafe acted on: the flagged line, the alert, the WRONG key, the primary action. Don't spend it on decoration.
2. **Rules, not boxes.** Group content with 1px hairlines and whitespace. No card backgrounds, no drop shadows on content (the only shadow is under a modal).
3. **Big and thin for numbers, small and mono for labels.** Hierarchy comes from size and weight contrast, not colour.
4. **Never say "safe."** No green "all clear" state exists. A call with no alert reads "No alert detected", never "safe" or "no scam".
5. **Colour never works alone.** Every status colour sits next to a word ("Delivered", "Code request").

## Colour tokens

Paste into `console/src/styles.css`:

```css
:root {
  color-scheme: light;
  --ground: #FBFAF8;      /* page background, warm off-white */
  --surface: #FFFFFF;     /* phone screen only */
  --scrim: #EFECE7;       /* behind a modal */
  --ink: #141413;         /* primary text */
  --ink-2: #4F4C47;       /* secondary text */
  --ink-3: #6B675F;       /* labels, timestamps, meta */
  --ink-4: #CFCAC2;       /* outlines, dashed rules, decorative only */
  --line: #E8E4DD;        /* hairline separators */
  --field: #8A857D;       /* input underline, secondary button outline */

  --magenta: #E20074;     /* fills, big numbers, dots, bars */
  --magenta-text: #C8006A;/* magenta text under 24px */
  --on-magenta: #FFFFFF;

  --good: #2E7D4F;        /* delivered, stream live */
  --info: #3B6585;        /* session, arm, neutral status */
  --warn: #9A5800;        /* simulated SMS, caution */
  --danger: #A3261A;      /* Reset only */
  --bubble-in: #F1EEE9;   /* incoming SMS bubble */

  --display: "Jost", "Futura", "Avenir Next", sans-serif;
  --body: "Instrument Sans", "Helvetica Neue", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
```

Fonts: `https://fonts.googleapis.com/css2?family=Jost:wght@200;300;400;500&family=Instrument+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap`

### Contrast (on `--ground`)

| Token | Ratio | Use |
|---|---|---|
| `--ink` | 17.7:1 | any text |
| `--ink-2` | 8.2:1 | any text |
| `--ink-3` | 5.4:1 | any text, including 12px labels |
| `--magenta-text` | 5.5:1 | magenta text at any size |
| `--magenta` | 4.49:1 | text 24px and up, fills, non-text marks (just under 4.5, so never small text) |
| white on `--magenta` | 4.7:1 | button labels |
| `--good` / `--warn` / `--info` / `--danger` | 4.8 / 5.3 / 6.0 / 7.1:1 | status text |
| `--field` | 3.5:1 | control edges (meets 3:1 non-text) |
| `--ink-4`, `--line` | below 3:1 | never for text or for the only edge of a control |

Magenta is the only T-Mobile element in the console. The intro screen (`#home`, for the demo video) shows CallSafe × T-Mobile (Arnav, 2026-11-08); nowhere else.

## Typography

| Role | Font | Size / weight | Notes |
|---|---|---|---|
| Hero number (call timer, 0.9%) | display | clamp(5rem, 8vw, 8rem) / 200 | line-height .86, tracking -0.02em |
| Headline (verdict, page title) | display | clamp(2.2rem, 3.3vw, 3.2rem) / 300 | `text-wrap: balance` |
| Section lead | display | 26px / 300 | "Bank call replay", "of harmless calls…" |
| Secondary number | display | 20–22px / 300 | stat grids, list values |
| Italic aside | display | 18px / 300 italic | one line under a headline |
| Transcript line | body | 23px / 400 (600 when flagged) | line-height 1.38 |
| Body | body | 15–16px / 400 | line-height 1.5 |
| Label | mono | 12px / 500, UPPERCASE, tracking .14em | section heads, status dots |
| Meta | mono | 12–13px / 400 | timestamps, hints, footer |

Use `font-variant-numeric: tabular-nums` on the page so timers and counts don't jump. Don't go below 12px. Body text never uses weight 200.

## Layout

- Page: `max-width: 1640px`, inline padding `clamp(16px, 4vw, 64px)`, vertical gap between bands `56px`.
- Main band: three columns, roughly `1fr 1.25fr 1fr`, column gap `clamp(32px, 4vw, 72px)`. Build it with `flex-wrap` (left `1 1 300px`, centre `1.25 1 440px`, right `1 1 320px`) so it stacks on narrow screens.
- Inside a column, sections are separated by `48px`.
- Spacing scale: 4, 6, 8, 10, 12, 14, 18, 22, 28, 36, 48, 56.
- Left column holds time and controls, the centre holds the verdict and transcript, and the right holds the headline number and the phone. Results and failures span the full width below.

## Components

**Section label.** A flex row with mono 12px uppercase: the title on the left, a short meta note on the right (tracking .08em). `margin-bottom: 14px`.

**List row.** 1px `--line` top border, 12–14px vertical padding. A grid of `time | dot | content | rel`, where rel is a mono uppercase status on the right.

**Status dot.** 6–8px circle in `currentColor`, followed by a mono uppercase word. Colours: `--good` delivered or live, `--info` arm or session, `--warn` simulated, `--magenta` caller or request.

**Step bar.** 3–4 equal 2px bars with a 4px gap. Done steps are `--ink-2`, the current step `--magenta`, and pending steps `--ink-4`. Mono labels sit underneath.

**Flagged transcript line.** Text turns `--magenta-text` at weight 600, the rel column reads "CODE REQUEST", and the speaker dot is magenta. A dashed `--ink-4` rule follows, with a mono note: "→ ALERT TEXT DELIVERED".

**Buttons.**
- Primary: a pill (`border-radius: 999px`), `--magenta` fill, white 16px/600 label, at least 48px tall. One per screen.
- Secondary: a pill with a 1px `--field` outline and transparent fill.
- Control rows (Run clinic, Run bank, End call): full-width list rows at least 48px tall, laid out as icon then label (no hints: the label says it). The bank row's text is `--magenta-text`. Reset sits last behind a dashed rule, in `--danger`.
- Toggle (SMS mode): mono uppercase pills. The on state is filled `--ink` with `--ground` text; the off state has a `--ink-4` outline. Set `aria-pressed` on both.
- Reply keys (YES / WRONG / SHARED / STOP): four mono pills, 44px tall, with WRONG filled magenta.

**Phone.** A 1px `--ink-4` outer outline with a 36px radius and 8px padding, around a `--surface` screen with a 28px radius. CallSafe's texts are on the left in `--bubble-in`; the subscriber's replies are on the right in `--magenta` with white text. Bubble radius is 16px, with a mono 11px timestamp under each.

**Input.** Underline only: a 1px `--field` bottom border, Jost 24px/300 value text, a mono uppercase label above and help text below (linked with `aria-describedby`). Include a "Show" text toggle and `autocomplete="current-password"`. On focus the underline turns magenta.

**Modal.** Page goes to `--scrim`. The dialog is `--ground` with a 1px `--line` border, a 4px radius, 40px padding and `box-shadow: 0 24px 60px rgba(20,20,19,.08)`. A Jost 40/300 question sits above the choices, which are list rows. Buttons are bottom right, primary last.

**Ticker.** Full-width band between two `--line` rules, scrolling at 70s per loop with the list duplicated. Each item is a mono 11px type tag (coloured by event type) followed by body text. It pauses on hover and stops under `prefers-reduced-motion`.

**Footer.** Mono 12px `--ink-3`, space-between, pulled up `-32px` under the ticker.

## Motion

Keep it quiet. The only continuous motion is the ticker. The transcript types in word by word at `WORD_MS` (100ms, already in `App.tsx`). State changes swap instantly or fade within 150ms. Everything respects `prefers-reduced-motion`.

## Accessibility checklist

- Focus ring: `outline: 1px solid var(--magenta); outline-offset: 3px` on every control.
- Targets are at least 44px tall, with at least 6px between them.
- The WRONG counter has `role="status" aria-atomic="true"` and announces "N WRONG replies", not a bare number.
- Decorative dots and icons get `aria-hidden="true"`. Icon-only buttons get `aria-label`.
- Sections use `aria-labelledby` pointing at their label text, and the transcript is an `<ol>`.
- Results ship as a real `<table>` or `<dl>`; charts are optional extras.

## Don't

- Fill cards or panels with backgrounds, or use rounded "card" containers.
- Use magenta for anything that isn't the request, the alert or the single primary action.
- Show a green or "safe" state for a call.
- Put `--magenta` (rather than `--magenta-text`) on text smaller than 24px.
- Add a dark theme without a separate contrast pass.
