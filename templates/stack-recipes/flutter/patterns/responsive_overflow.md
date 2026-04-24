# Responsive + Overflow Discipline (Flutter)

Every screen overflows eventually. Build for it from day one.

## The rules

### Column overflow

If a `Column` could grow taller than its parent: wrap in `Expanded(child: SingleChildScrollView(...))` or use a `ListView`.

```dart
// Wrong: overflows when content > screen height
Column(children: [
  HeaderWidget(),
  ContentWidget(),  // tall content
  FooterWidget(),
])

// Right
Column(children: [
  HeaderWidget(),
  Expanded(child: SingleChildScrollView(child: ContentWidget())),
  FooterWidget(),
])
```

### Row overflow

If a `Row` has children whose intrinsic widths could exceed the parent: wrap children in `Expanded` or `Flexible`.

```dart
// Wrong: long text overflows the row
Row(children: [
  Icon(Icons.tag),
  Text(longText),
  IconButton(...),
])

// Right
Row(children: [
  Icon(Icons.tag),
  Expanded(child: Text(longText, overflow: TextOverflow.ellipsis)),
  IconButton(...),
])
```

### Text overflow

Always combine three things: bounded width + `maxLines` + `TextOverflow.ellipsis`.

```dart
SizedBox(
  width: 200,
  child: Text(
    longLabel,
    maxLines: 2,
    overflow: TextOverflow.ellipsis,
  ),
)
```

### Modal overflow

EVERY modal body must be wrapped in `SingleChildScrollView` (or use `ListView`/`DraggableScrollableSheet`). Modals always overflow eventually — small screens, keyboard open, long content.

Plus bottom padding for safe area:

```dart
showModalBottomSheet(
  context: context,
  builder: (ctx) => Padding(
    padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).padding.bottom),
    child: SingleChildScrollView(child: body),
  ),
)
```

(See `widget_discipline.md` for the helper that wraps this once-per-project.)

### Search + list keyboard overflow

Any screen with a search TextField at the top and a scrollable list below MUST set `resizeToAvoidBottomInset: false` on the Scaffold.

```dart
Scaffold(
  resizeToAvoidBottomInset: false,  // CRITICAL — keyboard overlays the list, not pushes it
  body: Column(children: [
    SearchHeader(),
    Expanded(child: SearchResultsList()),
  ]),
)
```

Without this, the Column's fixed-height children (header + search bar + filter chips) overflow when the keyboard compresses the body.

### Floating bottom nav bar clearance

If your app renders a floating nav bar at `MaterialApp.builder` level, it covers ~70-80px of every pushed route. Any non-modal screen with action buttons at the bottom MUST add clearance:

```dart
// Define this constant once in your nav bar file:
const kBottomActionClearance = 96.0;  // 76 (nav bar) + 20 (visual breathing room)

// Use it as bottom padding in screen content:
EdgeInsets.fromLTRB(24, 16, 24, kBottomActionClearance)
```

## Quick checklist (post-edit hook material)

For every screen file, audit these:

- [ ] Any unbounded `Column` wrapped in `Expanded(child: SingleChildScrollView(...))` or `ListView`?
- [ ] Any `Row` with text wrapped in `Expanded`/`Flexible` + `overflow: TextOverflow.ellipsis`?
- [ ] Every modal body in a `SingleChildScrollView` with safe-area bottom padding?
- [ ] Search-and-list screens have `resizeToAvoidBottomInset: false`?
- [ ] Pushed routes account for floating nav bar clearance?

## Anti-pattern detection (warning-level hook)

A `post-edit-warnings.sh` hook can flag suspicious patterns:

```bash
# Modal without scroll wrapper (warns)
if echo "$NEW_STRING" | grep -qE 'showModalBottomSheet\('; then
  if ! echo "$NEW_STRING" | grep -qE 'SingleChildScrollView|ListView|DraggableScrollableSheet'; then
    echo "WARN: modal body missing scroll wrapper" >&2
  fi
fi

# Pushed-screen Scaffold without bottom clearance (warns)
if echo "$FILE_PATH" | grep -qE 'lib/.*screen.*\.dart$'; then
  if echo "$NEW_STRING" | grep -qE 'EdgeInsets\.(fromLTRB|only).*bottom'; then
    if ! echo "$NEW_STRING" | grep -qE 'kBottomActionClearance|MediaQuery\.of\(context\)\.padding\.bottom'; then
      echo "WARN: bottom padding may not account for floating nav bar" >&2
    fi
  fi
fi
```

## Why these matter

Overflow bugs are reported as "looks broken on my phone" — never as "responsive design issue." They cost trust, not just polish. Building for overflow from day one is a tiny tax during construction; retrofitting after launch costs hours per screen.
