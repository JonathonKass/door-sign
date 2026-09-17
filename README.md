# Office door sign

Renders an 800x480 black-and-white image of the week for a Seeed reTerminal
E1001 ePaper display. You edit one file, a GitHub Action redraws the image,
and the display picks it up.

## Everyday use

Edit `schedule.json` in GitHub's web editor (the pencil icon), commit, and wait
a minute or two. That's the whole workflow, and it works fine from a phone.

- **`default_week`** is your normal week. It rolls forward on its own, so in an
  ordinary week you change nothing.
- **`overrides`** are dated exceptions, and they win over the default week. Set
  just `am` or just `pm` to change half a day. `note_am` / `note_pm` print in
  small type under the status.
- **`notice`** is the banner across the bottom. Set it to `""` to hide the bar,
  in which case a small "updated" timestamp appears instead.

Valid statuses are `office`, `remote` and `leave`, which print as IN OFFICE,
REMOTE and OUT.

Old overrides are ignored once the date has passed. You can delete them or
leave them; they cost nothing either way.

## Checking it

`https://<your-username>.github.io/<repo>/` shows the current image at true
size. `https://<your-username>.github.io/<repo>/sign.png` is the raw image,
and that is the URL the display fetches.

## One-time setup

1. Create a GitHub repository and upload these files.
2. **Settings → Pages**: set Source to "Deploy from a branch", branch `main`,
   folder `/ (root)`.
3. **Settings → Actions → General → Workflow permissions**: choose
   "Read and write permissions". Without this the Action cannot commit the
   rendered image, which is the most common way this setup fails.
4. **Actions** tab → "Render door sign" → "Run workflow" to build it once by
   hand and confirm it works.

## Running it locally

```
pip install Pillow
python3 render.py schedule.json sign.png
python3 render.py schedule.json test.png --date 2026-12-24   # preview a date
```

## Notes

- The schedule rebuilds every morning at 11:00 UTC so the "today" highlight
  advances. GitHub sometimes runs scheduled jobs late by a few minutes.
- On Saturday and Sunday the sign shows the week ahead, not the one that ended.
- `timezone` in `schedule.json` matters: the build server runs on UTC, and
  without it the sign would roll over to tomorrow in the late afternoon.
- The image is pure 1-bit black and white. OUT is drawn as a diagonal hatch
  rather than gray, so it survives on a display with no true grayscale.
