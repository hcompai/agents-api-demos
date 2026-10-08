# design_and_print (Python)

A Holo agent on your Mac designs a part in FreeCAD, slices it in Bambu Studio and starts the print, clicking
through both apps like a person: no CAD scripts, no printer API.

```
print-cli ──Client.local()──► agent runtime on this Mac ──► Holo4 (Models API)
                                 ├─ desktop:     FreeCAD, Bambu Studio, file dialogs
                                 └─ workstation: shell for plumbing (folders, open -a)
```

The whole recipe (part limits, FreeCAD tips, slicing budget, print checklist) lives in
[`instructions.md`](instructions.md). Edit it to fit your printer.

## Setup

- macOS with [FreeCAD](https://www.freecad.org/downloads.php) and [Bambu Studio](https://bambulab.com/en/download/studio).
- A Bambu Lab printer bound in Bambu Studio, idle, filament loaded.
- Screen Recording and Accessibility permissions for your terminal.

## Run

```bash
uv run --extra local print-cli --printer "My X2D" --prompt "A chess rook, about 25 mm tall"
```

Job files land in `jobs/<timestamp>/` (`part.FCStd`, `part.stl`). A run takes about 15 minutes and 200 steps.
