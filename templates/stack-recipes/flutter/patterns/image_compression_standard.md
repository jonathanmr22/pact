# Image Compression Standard (Flutter)

## The standard

**ALL** images stored in the app MUST go through a single compression helper that produces:

- **Format:** WebP
- **Quality:** 90
- **Max dimension:** 1080px (longest edge)
- **In-place rewrite:** the original file is replaced (no parallel `_compressed` files)

## Why a single helper

If each screen / each upload path implements its own compression, the format / quality / size diverge. Some users end up with 4MB JPEGs, others with 200KB WebPs. Storage costs balloon, sync is slow, the UI is inconsistent. A single helper enforces uniformity.

```dart
// Example helper API
class ImageCompressor {
  /// Replace [file] with a compressed WebP @ quality 90 @ 1080px max dim.
  /// Returns the same File reference for chaining.
  static Future<File> compressToWebPInPlace(File file) async {
    // ... uses flutter_image_compress, image, or similar package
  }
}
```

## Why WebP, quality 90, 1080px

| Choice | Reason |
|---|---|
| WebP | ~30% smaller than JPEG at the same perceptual quality. Native on Android since API 14, iOS 14+. |
| Quality 90 | Sweet spot — visually indistinguishable from 100, ~40% smaller files than 95. |
| 1080px max | Even premium phones rarely render images at >1080px in normal contexts. Going higher is wasted bytes. |

These are defaults for **user-facing photos** (avatars, post images, attachments). Specialized contexts (icons, full-resolution maps, document scans) may need different settings — handle those as explicit exceptions.

## Migration: legacy JPG/PNG → WebP

If your project predates this standard, you have legacy files in JPEG/PNG. Two strategies:

### Eager migration (recommended for small libraries)

A bootstrap-time helper walks the image directory, recompresses everything to WebP, deletes originals. Run on first launch after the standard ships, then never again.

```dart
class ImageMigration {
  static Future<void> retryPendingCompressions() async {
    final dir = await getApplicationDocumentsDirectory();
    final imagesDir = Directory('${dir.path}/images');
    await for (final entity in imagesDir.list(recursive: true)) {
      if (entity is File) {
        final ext = entity.path.split('.').last.toLowerCase();
        if (ext == 'jpg' || ext == 'jpeg' || ext == 'png') {
          await ImageCompressor.compressToWebPInPlace(entity);
        }
      }
    }
  }
}
```

### Lazy migration (recommended for large libraries)

Compress on-read: when an image file is loaded for display, check its extension. If JPG/PNG, kick off background compression and replace.

Trade-off: simpler bootstrap (no big migration step), but the savings appear gradually rather than at once.

## Anti-patterns

| Pattern | Why it breaks |
|---|---|
| Per-screen compression with different quality/dimension | File-size variance across the app; image cache thrashing |
| Saving the original alongside the compressed (`photo.jpg` + `photo_thumb.jpg`) | 2x storage for no benefit (the compressed version is the only one anyone needs) |
| Skipping compression for "small" uploads | Modern cameras produce 4MB photos even at 12MP; "small" is rarely small |
| Different format for thumbnails vs full | Thumbnail and full from the SAME source file at different render sizes is fine; keeping multiple stored copies is not |

## Hook enforcement

A `pre-edit-rules.sh` rule can flag direct calls to non-standard compression APIs:

```bash
# Block bare flutter_image_compress calls — must go through ImageCompressor
if echo "$NEW_STRING" | grep -qE 'FlutterImageCompress\.compress'; then
  if ! echo "$FILE_PATH" | grep -qE 'image_compressor\.dart'; then
    echo "BLOCKED: use ImageCompressor.compressToWebPInPlace, not raw FlutterImageCompress" >&2
    exit 1
  fi
fi
```

## Verification

After adopting:

- Image directory size before/after migration: expect 60-70% reduction
- Image cache hit rate: should improve (smaller files = more fit in memory cache)
- Sync time per image: roughly proportional to file size — measure delta
