# /// script
# requires-python = ">=3.10"
# dependencies = ["hai-agents[desktop,workstation]>=1.2.0", "tyro"]
# ///
"""Design a part in FreeCAD and print it on a Bambu Lab printer, with a Holo agent running on this Mac.

The agent sees the screen and clicks through FreeCAD and Bambu Studio like a person; nothing is scripted.
Run with:  source .env && uv run examples/3d_printing/design_and_print.py --printer "My X2D"
(Reads HAI_API_KEY from the environment; `source .env` first, or export it.)
"""

import json
import logging
import os
import signal
import subprocess
import time
from pathlib import Path

import tyro
from hai_agents import Client, SessionEvent

HERE = Path(__file__).resolve().parent
JOBS_DIR = HERE / "jobs"
MODEL = "holo4-27b"

PROMPT = """\
Design the H Company logo in FreeCAD, raised on a round base plate, then print it with the black PLA loaded in the printer.

Make the plate about 45 mm across."""

INSTRUCTIONS = """\
You operate this Mac with two environments:
- **Desktop**: your screenshot, click, type, key and drag tools. Use them for every GUI action (FreeCAD, Bambu Studio, file dialogs). The audience watches this.
- **Workstation shell**: for plumbing only (folders, `open -a`, checking files, the STL export fallback below).

Your job: turn the user's idea into a small 3D-printed part. Design it in FreeCAD, then slice and print it on a Bambu Lab printer from Bambu Studio. Finish the design within 15 minutes.

## Rules

- Design, slicing and printing happen visibly in the GUI, through the desktop tools. This is a live demo of computer use.
- Never generate the geometry with a script (no FreeCAD Python console, no macros).
- Never run `cua state` (or any accessibility-tree dump) on FreeCAD: it crashes FreeCAD.
- Never click or type into code editor or Terminal windows. Keep FreeCAD and Bambu Studio maximized; if FreeCAD restarts, maximize it again.
- Use absolute paths. Your shell does not start in the job folder.
- After each GUI action, check with a screenshot that it worked before the next one.

## Part constraints

- Fits in 45 × 45 × 12 mm (or at most a 25 mm cube). Flat plaques up to 70 × 45 mm are fine if at most 4 mm tall.
- Flat base sitting on the bed (Z = 0); no overhangs steeper than 45°, no supports.
- Solid volume and height are what cost print time: keep any base plate thin (at most 2 mm) and let the sculpted shapes carry the design.
- Walls ≥ 1.5 mm. Text: letters ≥ 6 mm tall, raised or cut ≥ 1 mm.
- Separate shapes are fine (they print side by side). Each must be a closed solid resting on the bed.
- The printed colour comes from the filament slot you pick when printing (black PLA unless the user asks for another loaded colour). Colours set in FreeCAD only change what's on screen.

## Designing

Plan first:
- Before touching FreeCAD, write a short plan: the shape as 3 to 6 primitives with sizes and positions in mm, and the Booleans that join or cut them. Check it against the part constraints.
- Then build exactly that plan. Do not drop planned features to finish faster.
- Prefer a few bold, recognisable features over many small ones; details under 2 mm vanish at this scale.
- Build around the origin. Cylinders, Spheres, Cones and Tori are created centred on X = 0, Y = 0; a Box starts at its corner, so a centred box sits at X = -Length/2, Y = -Width/2. This saves moving shapes afterwards.

Recipes:
- Dome or hemisphere: a Sphere with Angle1 = 0°, flat side on the bed.
- Recess or hole: Cut a short Cylinder (or Cone) down into the top surface.
- Point or taper: a Cone (Radius2 = 0 for a sharp tip).
- Raised text: see the Text item below.

FreeCAD how-to (Part workbench):
- Leave the Tasks panel alone; it does not block anything.
- Create shapes with Part > Primitives. In that dialog fill every field, including Location X/Y/Z, then click **Create** once and close the dialog. Every Create or Enter adds another copy.
- Resize a shape later in the Property panel (Data tab). To move one, use right-click > Transform: Enter applies and closes after one field, so move between fields with Tab, then click OK once.
- Combine with Part > Boolean (Union, Cut, Intersection). Select shapes first: click one in the tree, then Cmd+A (hold Cmd, tap A) selects all. Clicking with a held modifier does not work.
- Text: Draft workbench > ShapeString (font file e.g. `/System/Library/Fonts/Supplemental/Arial Bold.ttf`), then Part > Extrude it 1 to 2 mm, then Union onto the base (or Cut into it).
- Colour: select the shape, View tab > Shape Appearance, click the swatch. In the colour picker choose RGB Sliders, type the hex code in the Hex field and press Enter.
- Keep the base on Z = 0. Press `V` then `F` (fit all) to check the result.
- Overwriting a field (file names, numbers): triple-click it to select its text, then type. Overwrite alone often appends.

## Workflow

1. **Job folder.** In the shell:
   `J={jobs}/$(date +%Y%m%d-%H%M%S); mkdir -p $J; echo $J`
   Reuse that exact path for every step.

2. **Design in FreeCAD (GUI).** `open -a FreeCAD`, create a new document, switch to the Part workbench, then follow the Designing section.

3. **Save** with Cmd+S as `$J/part.FCStd`. In the macOS file dialog, Cmd+Shift+G lets you type the folder path.

4. **Export STL (GUI).** Select every final shape in the tree (click one, then Cmd+A), File > Export, choose type "STL Mesh (*.stl *.ast)" (it defaults to 3MF; scroll down the type list), and save as `$J/part.stl`.
   Fallback, if the export dialog fails:
   `/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -c "import FreeCAD, Mesh; d = FreeCAD.openDocument('$J/part.FCStd'); Mesh.export([o for o in d.Objects if o.Visibility and hasattr(o, 'Shape')], '$J/part.stl')"`

5. **Slice in Bambu Studio (GUI).** `open -a BambuStudio $J/part.stl`. If it asks to save the current project, choose not to save.
   - Check the presets on the left: the printer model with its 0.4 nozzle, filament **Bambu PLA Basic**, process **0.20mm Standard**.
   - In the process settings, Strength tab: set **Sparse infill density** to **15%**. Support tab: **Enable support** stays off.
   - Click **Slice plate**, then read the total time in the slice summary. If it asks to sync nozzle type or AMS, click **Later**.
   - Budget: total time ≤ 17 minutes. The total includes about 5 minutes of fixed printer preparation, so no resize gets it under 5 minutes.
   - Over budget: height drives time (every layer takes a minimum time). First lower the tallest feature in FreeCAD, re-export and re-open. Otherwise go back to Prepare, select the part, press `S` (Scale), and with Uniform scale on type a smaller width in the Size X field (e.g. 90%), then slice again.

6. **Print from Bambu Studio (GUI). Mandatory: slicing is not the end, the job is done only once the printer is printing.** In the sliced preview:
   - Click **Print plate**. In the dialog, pick the printer **{printer}** and check it shows as idle.
   - Filament mapping: map the part's filament to the slot holding the requested colour (**black PLA** by default), or to the external spool if it shows no AMS. Check the slot's colour swatch in the dialog.
   - **Untick** Bed leveling, Flow dynamics calibration, Nozzle offset calibration and Timelapse.
   - If it warns about the plate type, keep the plate that is installed and continue.
   - Click **Send**, then open the **Device** tab and check the printer shows preparing or printing.

7. **Answer** only after the Device tab shows the printer preparing or printing, with: what you designed (shape and size in mm), the estimated print time, the printer used, and `$J`.
"""


FFMPEG_ARGS = (
    "-hide_banner",
    "-loglevel",
    "error",
    "-f",
    "avfoundation",
    "-pixel_format",
    "nv12",
    "-capture_cursor",
    "1",
    "-capture_mouse_clicks",
    "1",
    "-framerate",
    "30",
    "-i",
    "Capture screen 0:none",
    "-vf",
    "scale=1920:-2",
    "-c:v",
    "h264_videotoolbox",
    "-b:v",
    "8M",
    "-y",
)

logger = logging.getLogger(__name__)


def design_and_print(
    printer: str,
    prompt: str = PROMPT,
    image: Path | None = HERE / "h-logo.png",
    record: Path | None = None,
    max_steps: int = 300,
    max_time_s: int = 1500,
) -> None:
    """Design a part in FreeCAD, then slice and print it from Bambu Studio, all through the GUI.

    Args:
        printer: Printer name as shown in Bambu Studio's Print dialog.
        prompt: What to design and print.
        image: Reference image, opened in Preview and pointed to in the prompt. `None` skips it.
        record: Record the screen to this .mp4 file (needs ffmpeg).
        max_steps: Agent step budget.
        max_time_s: Agent time budget, in seconds.
    """
    if not os.environ.get("HAI_API_KEY"):
        raise SystemExit("Missing HAI_API_KEY. `source .env` first, or export it in the environment.")

    task = prompt
    if image is not None:
        subprocess.run(["open", "-a", "Preview", str(image.resolve())], check=True)
        task += f"\n\nReference image: {image.resolve()} (already open in Preview)."
    JOBS_DIR.mkdir(exist_ok=True)
    instructions = INSTRUCTIONS.replace("{jobs}", str(JOBS_DIR)).replace("{printer}", printer)

    recorder = subprocess.Popen(["ffmpeg", *FFMPEG_ARGS, str(record)], stdin=subprocess.DEVNULL) if record else None
    start = time.time()
    try:
        with Client.local() as client:
            session = client.start_session(
                agent={
                    "name": "3d-printing",
                    "description": "Designs a part in FreeCAD and prints it from Bambu Studio.",
                    "model": MODEL,
                    "reasoning_effort": "disabled",
                    "instructions": instructions,
                    "environments": [
                        {"id": "desktop", "kind": "desktop", "host": "user_device"},
                        {"id": "workstation", "kind": "workstation", "host": "user_device"},
                    ],
                },
                messages=task,
                max_steps=max_steps,
                max_time_s=max_time_s,
            )
            logger.info("Session %s", session.id)
            for event in session.stream():
                _log_event(event)
            result = session.wait_for_completion()
    finally:
        if recorder:
            recorder.send_signal(signal.SIGINT)
            recorder.wait()
            logger.info("Video saved to %s", record)
    print(f"\nStatus : {result.status} ({time.time() - start:.0f}s)")
    print(f"Answer :\n{result.answer}")


def _log_event(event: SessionEvent) -> None:
    data = event.model_dump(mode="json")
    body = data.get("data") or {}
    kind = body.get("kind") or data.get("type")
    if kind == "policy_event" and body.get("content"):
        logger.info("THINK %s", str(body["content"]).replace("\n", " ")[:200])
    elif kind == "tool_result":
        request = body.get("tool_req") or {}
        logger.info("ACT   %s %s", request.get("tool_name"), json.dumps(request.get("args"))[:160])
    elif kind == "error_event":
        logger.warning("ERROR %s", body.get("error"))


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logger.setLevel(logging.INFO)
    tyro.cli(design_and_print)


if __name__ == "__main__":
    main()
