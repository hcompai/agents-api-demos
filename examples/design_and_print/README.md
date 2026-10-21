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

- macOS on Apple silicon with [FreeCAD](https://www.freecad.org/downloads.php) and [Bambu Studio](https://bambulab.com/en/download/studio).
- A Bambu Lab printer bound in Bambu Studio, idle, filament loaded.
- Screen Recording and Accessibility permissions for your terminal.
- Follow the repository [quickstart](../../README.md#quickstart) and set `HAI_API_KEY` in `.env`.

The command controls this Mac and sends the job to the named printer. Save open work first and check that the bed is clear and the plate, nozzle and loaded filament match Bambu Studio's settings. Hosted Holo receives screenshots and tool output; see [local mode](https://hub.hcompany.ai/agents-api/local-mode).

## Run

```bash
uv run --extra local print-cli --printer "My X2D" --prompt "A chess rook, about 25 mm tall"
```

Job files land in `examples/design_and_print/jobs/<timestamp>-<suffix>/` (`part.FCStd`, `part.stl`). The first run downloads the local runtime. The agent budget defaults to 25 minutes and 300 steps; the print runs separately after the agent exits. Stay nearby while it operates the desktop and printer.
