# Brand assets

Drop the official MockMateAI artwork here. The app reads it through
`src/components/brand/Brand.tsx` — nothing else references these paths, so this
folder is the only place a logo file ever needs to be updated.

## Required

| File | Used for |
| --- | --- |
| `mockmateai-mark.png` | The mark, everywhere: navbar, sidebar, auth, loader, intro, favicon |

**Filename must be lowercase.** Windows doesn't care, Linux does — an uppercase
`.PNG` works locally and 404s the moment it's deployed.

Transparent background. The mark is sized by **height** with width left to
follow, so it doesn't need to be square — the current asset is 1362×1155 and
sits correctly against the wordmark's cap height.

Until this file exists the app renders a neutral geometric placeholder instead —
no broken images, and the official mark appears everywhere the moment the file is
added. No code change needed.

### Worth doing at some point

The current export is **1.1 MB**, and it's displayed at 20–32px in the header and
sidebar. That's roughly a thousand times more pixels than are ever shown, and it
downloads on first load of every page. Re-exporting at **256px on the long edge**
would bring it under ~30 KB with no visible difference anywhere it's used. The
intro and loader render it largest, at 96px, so 256px still leaves headroom for
retina.

## Optional

| File | Used for |
| --- | --- |
| `mockmateai-mark-light.png` | A brighter cut for dark backgrounds |
| `mockmateai-mark-dark.png` | A darker cut for light backgrounds |

Only add these if the single mark genuinely loses contrast in one theme. The
supplied artwork is a metallic gradient that holds up on both, so one file is
normally enough.

## What the code does *not* do

It never recolours, redraws, reproportions or crops the artwork. The only
treatment is an optional soft glow rendered *behind* the image (`glow` prop),
used on the loader and the intro.

## Favicon

`public/favicon.svg` is separate and still hand-drawn. To use the official mark
there too, export a 64×64 PNG as `public/favicon.png` and change the `<link
rel="icon">` in `index.html` to point at it.
