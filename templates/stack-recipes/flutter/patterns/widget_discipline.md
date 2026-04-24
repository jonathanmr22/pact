# Widget Discipline Patterns (Flutter)

A handful of patterns that have repeatedly bitten Flutter projects in production. Adopt them by convention; enforce them via lints/hooks where possible.

## 1. One project-wide PrimaryActionFab — never raw FloatingActionButton

**Problem:** Every screen reinvents the FAB shape, color, position. Inconsistent visual language, divergent tap targets, fragile theming.

**Fix:** Build a single `PrimaryActionFab` widget for the project. Use it everywhere. Allow customization via props (icon, label, customChild).

```dart
class PrimaryActionFab extends StatelessWidget {
  final VoidCallback onPressed;
  final IconData? icon;
  final String? label;
  final Widget? customChild;
  // ...
}
```

**Anti-pattern that needs hook enforcement:** raw `FloatingActionButton(...)` calls in screen files. A `pre-edit-rules.sh` regex can BLOCK any `FloatingActionButton(` literal in `lib/` (allow list: the `PrimaryActionFab` source itself, animation prototypes in `cutting_room/`).

**Exception:** Map screens often need an expandable multi-action FAB that doesn't fit the single-button model. One exception per project is fine; document it.

## 2. No FilledButton / ElevatedButton at the bottom of a pushed route

**Problem:** Flutter apps with a floating bottom nav bar (rendered at `MaterialApp.builder` level) cover the bottom ~70-80px of every pushed route. A primary-action button placed at the bottom of a Scaffold body gets hidden behind the nav bar.

**Fix:** Two options:
- Use `PrimaryActionFab` (which respects nav bar clearance automatically).
- If you must use a button, add explicit padding equal to the nav bar height + safe area:
  ```dart
  EdgeInsets.fromLTRB(24, 16, 24, kBottomActionClearance)
  ```

**Anti-pattern that needs hook enforcement:** `FilledButton(` or `ElevatedButton(` inside a `Scaffold > body` of any non-modal screen file. Hook BLOCKs.

## 3. Theme over manual styleFrom

**Problem:** Every screen overrides `styleFrom(backgroundColor: ..., foregroundColor: ...)` for buttons, cards, chips. Theme stops being the source of truth. Color drift everywhere.

**Fix:** Build all styling into a `ThemeBuilder` (sometimes called AppTheme, ThemeFactory, etc.). Set `MaterialApp.theme` to its output. Never call `styleFrom`/`activeColor`/`selectedColor`/`backgroundColor` on widgets the theme already styles.

**Anti-pattern that needs hook enforcement:** `styleFrom(` literal in screen files. Allow the theme builder source itself.

## 4. Modal scroll wrapper requirement

**Problem:** Modals (`showModalBottomSheet`, dialogs) eventually overflow when the user has many items, the keyboard opens, or the device is narrow. Every modal will overflow at some point.

**Fix:** Build a `showAppBottomSheet` helper that wraps every modal body in `SingleChildScrollView` + bottom-padding for safe area. Project rule: never use raw `showModalBottomSheet`.

```dart
Future<T?> showAppBottomSheet<T>({required BuildContext context, required Widget body}) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    builder: (ctx) => Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).padding.bottom),
      child: SingleChildScrollView(child: body),
    ),
  );
}
```

**Anti-pattern that needs hook enforcement:** raw `showModalBottomSheet(` in screen files. Allow the wrapper source itself.

## 5. SnackBar / AlertDialog helpers

**Problem:** Every screen builds its own one-off snackbar style, dialog confirmation flow, error message format. Inconsistent UX.

**Fix:** Build `SnackBarHelper.show(context, ...)` and `showAppConfirmDialog(...)` helpers. Use them everywhere. Never raw `ScaffoldMessenger.of(context).showSnackBar(SnackBar(...))` or `showDialog(... AlertDialog(...))`.

**Anti-pattern that needs hook enforcement:** raw `SnackBar(` or `AlertDialog(` constructors in screen files.

## 6. No arbitrary Color literals

**Problem:** `Color(0xFF42A5F5)` scattered across the codebase. Themable surfaces stop matching the palette. Dark mode breaks for any widget using a literal.

**Fix:** All colors come from a `Palette` class with named getters (`Palette.primary`, `Palette.accentBlue`, etc.). Use semantic names (`Palette.surface`) for material surfaces and accent names for explicit branding.

**Anti-pattern that needs hook enforcement:** `Color(0x` literal in any non-palette file.

## Hook enforcement template

The patterns above are mostly enforceable via a project's `pre-edit-rules.sh`:

```bash
# Examples (adapt regex to project's actual widget names):

# Block raw FloatingActionButton in screen files
if echo "$FILE_PATH" | grep -qiE 'lib/.*screen.*\.dart$'; then
  if echo "$NEW_STRING" | grep -qE '\bFloatingActionButton\('; then
    echo "BLOCKED: use PrimaryActionFab, not raw FloatingActionButton" >&2
    exit 1
  fi
fi

# Block raw showModalBottomSheet
if echo "$NEW_STRING" | grep -qE 'showModalBottomSheet\('; then
  if ! echo "$FILE_PATH" | grep -qE 'app_bottom_sheet'; then
    echo "BLOCKED: use showAppBottomSheet, not raw showModalBottomSheet" >&2
    exit 1
  fi
fi

# Block arbitrary Color literals
if echo "$NEW_STRING" | grep -qE 'Color\(0x'; then
  if ! echo "$FILE_PATH" | grep -qE 'palette\.dart'; then
    echo "BLOCKED: use Palette.named, not arbitrary Color literals" >&2
    exit 1
  fi
fi
```

Customize the widget names + allow-list paths for your project. The pattern is: any reusable-helper-replacing widget gets a hook.
