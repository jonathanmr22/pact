# Riverpod Dispose Safety Pattern

## The bug

Inside a `ConsumerStatefulWidget`, `ref.read(...)` from `dispose()` throws:

```
Bad state: No element
StateError: tried to use ConsumerState.ref after dispose() was called
```

…or worse, when the widget is reached via `Navigator.pushAndRemoveUntil(...)`, you get the red-screen `_dependents.isEmpty` error before dispose even runs.

## Why it happens

`ConsumerState.ref` resolves through `ProviderScope.containerOf(context)`, which depends on `BuildContext`. When the widget is being disposed (or pushed-and-replaced in a way that deactivates its ancestors first), `containerOf` can't traverse anymore — the inherited widgets are gone.

Calling `ref` from `initState()` is *also* illegal — you can't depend on inherited widgets there because the framework hasn't completed the binding yet.

## The fix

Cache the `ProviderContainer` in `didChangeDependencies()` (the legal place to depend on inherited widgets). Use the cached reference in `dispose()`.

```dart
class _MyScreenState extends ConsumerState<MyScreen> {
  ProviderContainer? _container;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _container ??= ProviderScope.containerOf(context);
  }

  @override
  void dispose() {
    // Use cached _container, NOT ref
    _container?.read(somethingProvider.notifier).cleanup();
    super.dispose();
  }
}
```

## Why not `initState()` instead of `didChangeDependencies()`?

`ProviderScope.containerOf(context)` calls `dependOnInheritedWidget`, which is illegal in `initState`. It throws when reached via `pushAndRemoveUntil` because the widget's ancestors are deactivated before initState completes in that navigation flow.

`didChangeDependencies` is the legal hook for inherited-widget access. It runs after initState and any time inherited widgets change. The `??=` ensures the container is captured exactly once.

## Anti-patterns

| Pattern | Problem |
|---|---|
| `ref.read(...)` in `dispose()` | StateError: ConsumerState.ref used after dispose |
| `ProviderScope.containerOf(context)` in `initState()` | dependOnInheritedWidget called before binding completes |
| Caching `ref` itself in `initState()` | `ref` is the same field that fails in dispose — caching doesn't help |
| Using a global / static container | Defeats the entire `ProviderScope` mechanism; breaks tests |

## When to apply

Any `ConsumerStatefulWidget` that needs to:
- Cancel a subscription in dispose
- Persist final state (e.g. write a draft) before unmount
- Notify a provider that the widget is going away
- Read a provider value during teardown for any reason

## When NOT to apply

If your `ConsumerStatefulWidget` doesn't touch providers in dispose, you don't need this pattern. Most leaf widgets fall here.

## Verification

```bash
# Search for the anti-pattern after introducing this pattern in a new screen
grep -rn 'ref\.read\|ref\.watch' lib/ | xargs -I{} grep -l 'dispose' {}
```

If a `ConsumerStatefulWidget` references `ref.read` or `ref.watch` AND has a `dispose()` method, audit it for this pattern.
