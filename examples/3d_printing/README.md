# 3d_printing (Python)

A Holo agent running on your Mac designs a part in FreeCAD, slices it in Bambu Studio, and starts the print on a
Bambu Lab printer. It sees the screen and clicks through both apps like a person: no CAD scripts, no printer API.

Single file: [`design_and_print.py`](design_and_print.py). The default prompt prints the H Company logo
([`h-logo.png`](h-logo.png)) raised on a 45 mm round plate.

```
design_and_print.py ──Client.local()──► agent runtime on this Mac ──► Holo4 (H Models API)
                                         │
                                         ├─ desktop:     clicks and types in FreeCAD, Bambu Studio, file dialogs
                                         └─ workstation: shell for plumbing (folders, open -a, STL export fallback)

FreeCAD: plan → primitives → Boolean → save → export STL
Bambu Studio: slice → check time → Print plate → printer, filament slot, calibrations off → Send → Device tab
```

## Setup

- macOS, with [FreeCAD](https://www.freecad.org/downloads.php) and [Bambu Studio](https://bambulab.com/en/download/studio) in `/Applications`.
- A Bambu Lab printer already bound in Bambu Studio (cloud or LAN mode), idle, with filament loaded.
- Screen Recording and Accessibility permissions for the terminal that runs the script (the agent takes screenshots and
  sends clicks).
- `HAI_API_KEY` in your environment.

## Run

```bash
# from the repo root, with HAI_API_KEY in your environment (or .env)
source .env && uv run examples/3d_printing/design_and_print.py --printer "My X2D"
```

`--printer` is the printer name shown in Bambu Studio's Print dialog. Other options:

| Option | Default | What it does |
| --- | --- | --- |
| `--prompt` | the H logo | what to design and print |
| `--image` | `h-logo.png` | reference image, opened in Preview and pointed to in the prompt; `None` skips it |
| `--record` | off | records the screen to an `.mp4` (needs `ffmpeg`) |
| `--max-steps` / `--max-time-s` | 300 / 1500 | agent budget |

```bash
uv run examples/3d_printing/design_and_print.py --printer "My X2D" --image None \
  --prompt "Design a chess rook in FreeCAD and print it with the black PLA loaded in the printer."
```

The script logs each thought and action, then prints the final answer: the design and its size, the estimated print
time, and the job folder (`examples/3d_printing/jobs/<timestamp>/` with `part.FCStd` and `part.stl`).

## What a run looks like

H logo, Holo4 27B with reasoning disabled: about 13 minutes and 198 steps from an empty FreeCAD to the printer
printing. In that run the slicer showed the part at 16 mm, over the 12 mm limit; the agent went back to FreeCAD,
cut the H down to 12 mm, re-exported, and then printed.

## Notes

- The agent instructions in the script carry the whole recipe: part limits (45 × 45 × 12 mm, no supports), a
  plan-first design method, FreeCAD GUI tips, the slicing time budget, and the print dialog checklist. Edit them to
  change the printer setup or the budget.
- The first start of the local runtime can take longer than its 45 s startup timeout. If it times out, run again.
- Simple shapes work best: domes, cylinders, cones and boxes combined with Booleans (a logo, an eye, a chess rook,
  a rocket). Avoid shapes that need supports.
