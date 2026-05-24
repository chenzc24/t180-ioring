---
name: t180-ioring
description: Master coordinator for complete T180 (180nm) IO Ring generation. Handles signal classification, device mapping, semantic intent generation, engine-based pin wiring, JSON generation, SKILL generation, and complete workflow through DRC/LVS verification. Use this skill for any T180 IO Ring generation task. Trigger when user mentions T180, 180nm, 180nm IO ring, or any IO ring task targeting the 180nm process node.
---

# IO Ring Orchestrator - T180

Master coordinator for T180 IO Ring generation. The T180 rules are different
from T28, but the execution architecture follows the T28 flow:

`draft intent -> semantic intent -> enrichment engine -> full intent graph -> validation -> confirmed config -> SKILL -> Virtuoso -> DRC/LVS`.

## Scripts Path Verification

Auto-detect `SCRIPTS_PATH` from this file's location. Do not hard-code:

```bash
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS_PATH="${SKILL_ROOT}/scripts"
ls "$SCRIPTS_PATH/enrich_intent.py" || echo "ERROR: SCRIPTS_PATH not found"
```

## Entry Points

- **Text requirements only** -> Step 0 -> Step 2 (Draft) -> [Step 2b if enabled] -> Step 3 (Semantic Intent + Engine)
- **Image input** -> Step 0 -> Step 1 (Image) -> Step 2 -> [Step 2b if enabled] -> Step 3
- **Draft intent graph file provided** -> Skip to Step 3
- **Final intent graph file provided** -> Skip to Step 4
- **User explicitly requests Draft Editor** -> Always open Step 2b regardless of `AMS_DRAFT_EDITOR`

Determine entry path automatically. Do not run any pre-step wizard opt-in flow.

## Output Path Contract

- Create one `output_dir` once and reuse it for Steps 2-11.
- Do not regenerate `timestamp` after Step 0.
- Export `AMS_OUTPUT_ROOT` once in Step 0.
- `AMS_OUTPUT_ROOT`: workspace-level output root
- `output_dir`: `${AMS_OUTPUT_ROOT}/generated/${timestamp}`
- DRC/LVS reports: `${AMS_OUTPUT_ROOT}/drc` and `${AMS_OUTPUT_ROOT}/lvs`

## Complete Workflow

### Step 0: Directory Setup & Parse Input

```bash
if [ -n "${AMS_IO_AGENT_PATH:-}" ]; then WORK_ROOT="${AMS_IO_AGENT_PATH}"; else WORK_ROOT="$(pwd)"; fi

export AMS_OUTPUT_ROOT="${AMS_OUTPUT_ROOT:-${WORK_ROOT}/output}"
mkdir -p "${AMS_OUTPUT_ROOT}/generated"

if [ -n "${output_dir:-}" ] && [ -d "${output_dir}" ]; then
  echo "Reusing existing output_dir: ${output_dir}"
else
  timestamp="${timestamp:-$(date +%Y%m%d_%H%M%S)}"
  output_dir="${AMS_OUTPUT_ROOT}/generated/${timestamp}"
fi
mkdir -p "$output_dir"
echo "AMS_OUTPUT_ROOT=${AMS_OUTPUT_ROOT}"; echo "output_dir=${output_dir}"

PROJECT_ROOT="$(cd "${WORK_ROOT}" && while [ ! -d .venv ] && [ "$(pwd)" != "/" ]; do cd ..; done; pwd)"
if   [ -f "${PROJECT_ROOT}/.venv/Scripts/python.exe" ]; then export AMS_PYTHON="${PROJECT_ROOT}/.venv/Scripts/python.exe"
elif [ -f "${PROJECT_ROOT}/.venv/bin/python" ];         then export AMS_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
elif [ -f "${SKILL_ROOT}/.venv/Scripts/python.exe" ];   then export AMS_PYTHON="${SKILL_ROOT}/.venv/Scripts/python.exe"
elif [ -f "${SKILL_ROOT}/.venv/bin/python" ];           then export AMS_PYTHON="${SKILL_ROOT}/.venv/bin/python"
elif command -v python3 &>/dev/null;                    then export AMS_PYTHON="python3"
elif command -v python  &>/dev/null;                    then export AMS_PYTHON="python"
else echo "ERROR: No Python 3.9+ found. Create .venv at project root."; return 1; fi
echo "AMS_PYTHON=${AMS_PYTHON}"

if [ -f "${SKILL_ROOT}/.env" ]; then set -a; . "${SKILL_ROOT}/.env"; set +a; fi
if [ -f "${PROJECT_ROOT}/.env" ]; then set -a; . "${PROJECT_ROOT}/.env"; set +a; fi

[ "${AMS_DRAFT_EDITOR:-}"  = "on" ] || export AMS_DRAFT_EDITOR="off"
[ "${AMS_LAYOUT_EDITOR:-}" = "on" ] || export AMS_LAYOUT_EDITOR="off"
echo "AMS_DRAFT_EDITOR=${AMS_DRAFT_EDITOR}  AMS_LAYOUT_EDITOR=${AMS_LAYOUT_EDITOR}"
```

All subsequent steps must use `$AMS_PYTHON`, not `python3`.

Parse user input: signal list, ring dimensions, placement order, and voltage-domain specs.
If the user explicitly requests the visual/draft editor, set `AMS_DRAFT_EDITOR=on` for this run.
If the prompt specifies a target Virtuoso library for the generated cell, keep it
as a load-time target (or `target_library`) rather than `ring_config.library_name`.
For T180, `ring_config.library_name` is the IO device master library and should
normally remain `tpd018bcdnv5` via `device_masters.default_library`.

### Step 1: Image Input Processing

Run only when images are provided.

1. Load `references/image_vision_instruction.md`.
2. Extract topology, counter-clockwise outer-ring signal order, and pad count description.
3. Treat extracted structure as Step 2 input.
4. If user text conflicts with image extraction, prefer explicit user text and report unresolved conflicts.

### Step 2: Build Draft JSON

Reference: `references/draft_builder_T180.md`

1. Parse structural inputs: signal list, width, height, `placement_order`.
2. Compute `ring_config`.
3. Generate `instances` for `pad` with only `name`, `position`, and `type`.
4. Save `{output_dir}/io_ring_intent_graph_draft.json`.

Do not add `device`, `pin_connection`, `direction`, `view_name`, or corner instances in Step 2.

### Step 2b: Draft Editor

Open when `AMS_DRAFT_EDITOR=on` or the user explicitly requested the editor.

```bash
$AMS_PYTHON $SCRIPTS_PATH/build_confirmed_config.py \
  {output_dir}/io_ring_intent_graph_draft.json \
  {output_dir}/io_ring_draft_confirmed.json \
  --mode draft
```

The draft editor lets users adjust pad placement and optionally set `device`,
`domain`, `voltage_domain`, and `direction`. Merge confirmed draft changes back
before Step 3. Treat editor values as hints unless the user explicitly set them.

Skip when `AMS_DRAFT_EDITOR=off` and the user did not request the editor.

### Step 3: Generate Semantic Intent + Run Enrichment Engine

Reference: `references/enrichment_rules_T180.md`

Mandatory inputs:
- Step 2 draft JSON as immutable structural source
- Step 2b draft editor output if opened
- Original user prompt constraints

Input precedence:
1. Explicit user prompt constraints
2. Draft Editor hints
3. Default inference from `enrichment_rules_T180.md`

Process:
1. Decide per instance: signal class, base `device`, concrete voltage-domain block id, broad domain, and `direction` for `PDDW0412SCDG`.
2. Write `{output_dir}/io_ring_semantic_intent.json` using the Semantic Intent Schema in `references/enrichment_rules_T180.md`.
3. Do not include `pin_connection`, `view_name`, or corners in semantic intent.
4. Run the engine:

```bash
$AMS_PYTHON $SCRIPTS_PATH/enrich_intent.py \
  {output_dir}/io_ring_semantic_intent.json \
  {output_dir}/io_ring_intent_graph.json \
  T180
```

Exit handling:
- Exit 0 -> proceed to Step 4.
- Exit 1 -> fix semantic intent input error and rerun Step 3.
- Exit 2 -> stop and report wiring table or engine bug.
- Exit 3 -> fix semantic classification/domain/provider mistake and rerun Step 3.

The engine owns mechanical wiring: `pin_connection`, `view_name`, `PCORNER`
insertion, and gate checks. Preserve draft `ring_config`, `name`, `position`,
and `type`.

### Step 4: Validate JSON

```bash
$AMS_PYTHON $SCRIPTS_PATH/validate_intent.py {output_dir}/io_ring_intent_graph.json
```

- Exit 0 -> proceed to Step 5.
- Exit 1 -> treat as engine output bug unless a targeted semantic fix is obvious.
- Exit 2 -> file not found.

### Step 5: Build Confirmed Config

Check `AMS_LAYOUT_EDITOR`:
- `on` -> ask whether to open the visual Layout Editor.
- `off` -> skip editor automatically.

Open editor:

```bash
$AMS_PYTHON $SCRIPTS_PATH/build_confirmed_config.py \
  {output_dir}/io_ring_intent_graph.json \
  {output_dir}/io_ring_confirmed.json
```

Skip editor:

```bash
$AMS_PYTHON $SCRIPTS_PATH/build_confirmed_config.py \
  {output_dir}/io_ring_intent_graph.json \
  {output_dir}/io_ring_confirmed.json \
  --skip-editor
```

### Step 6: Generate SKILL Scripts

```bash
$AMS_PYTHON $SCRIPTS_PATH/generate_schematic.py \
  {output_dir}/io_ring_confirmed.json \
  {output_dir}/io_ring_schematic.il

$AMS_PYTHON $SCRIPTS_PATH/generate_layout.py \
  {output_dir}/io_ring_confirmed.json \
  {output_dir}/io_ring_layout.il
```

The scripts add timestamps to output filenames. Use the actual printed paths in later steps.

### Step 7: Check Virtuoso Connection

```bash
$AMS_PYTHON $SCRIPTS_PATH/check_virtuoso_connection.py
```

- Exit 0 -> proceed.
- Exit 1 -> stop and report generated files so far. Do not proceed.

### Step 8: Execute SKILL Scripts in Virtuoso

Use timestamped `.il` filenames printed by Step 6:

```bash
$AMS_PYTHON $SCRIPTS_PATH/run_il_with_screenshot.py \
  {output_dir}/io_ring_schematic_<timestamp>.il \
  {lib} {cell} \
  {output_dir}/schematic_screenshot.png \
  schematic

$AMS_PYTHON $SCRIPTS_PATH/run_il_with_screenshot.py \
  {output_dir}/io_ring_layout_<timestamp>.il \
  {lib} {cell} \
  {output_dir}/layout_screenshot.png \
  layout
```

### Step 9: Run DRC

```bash
$AMS_PYTHON $SCRIPTS_PATH/run_drc.py {lib} {cell} layout T180
```

- T180 DRC defaults to the benchmark selected-rule deck
  `calibre/T180/_drc_rule_T180_cell_benchmark_`.
- The full/current selected deck is still available as
  `DRC_RULE_FILE_180_FULL` in `calibre/env_common.csh`.
- Exit 0 -> Step 10.
- Exit 1 -> parse report, fix semantic intent, rerun Steps 3-9. Maximum 2 attempts.

### Step 10: Run LVS

```bash
$AMS_PYTHON $SCRIPTS_PATH/run_lvs.py {lib} {cell} layout T180
```

- Exit 0 -> Step 11.
- Exit 1 -> identify mismatch, fix semantic intent, rerun Steps 3-10. Maximum 2 attempts.

### Step 11: Final Report

Report generated files, validation results, DRC/LVS results, ring statistics,
voltage-domain summary, and image analysis results if applicable.

## Semantic And Rule Boundaries

- T180 rules live in `references/enrichment_rules_T180.md`.
- The engine data file is `io_ring/schematic/devices/device_wiring_T180.json`.
- Semantic intent uses base T180 device names only: no T28 suffixes and no `_H_G` / `_V_G`.
- The only T180 corner device emitted by the engine is `PCORNER`.
- Broad `domain` in final intent graph is `analog`, `digital`, or `null`; concrete voltage-domain block id is stored as `voltage_domain`.

## Global Rules

- Preserve user signal order exactly.
- Preserve duplicate signal names as duplicate pads.
- Do not reorder, sort, or group signals unless the user explicitly changes placement.
- Insert `PCORNER` at side transitions; do not add semantic corner entries manually.
- Isolate analog and digital domains.
- Each voltage-domain block needs provider pair `PVDD2CDG` + `PVSS2CDG` and consumer pair `PVDD1CDG` + `PVSS1CDG`.
- Each voltage-domain block must have exactly one `PVDD2CDG`; multiple `PVSS2CDG` are allowed only with the same signal name.
- `PDDW0412SCDG` must carry `direction: input` or `direction: output`.
- Do not rely on mental arithmetic for geometry; use code.

## Checklist

- Step 2 draft JSON contains only `ring_config` plus `name`/`position`/`type`.
- Step 3 semantic intent contains device/domain/direction decisions but no pins or corners.
- Step 3 engine exits 0 and prints passing gates.
- Step 4 validation exits 0.
- Step 5 confirmed config is generated.
- Step 6 schematic and layout SKILL files are generated.
- Steps 7-10 complete when Virtuoso and Calibre are available.

## Directory Structure

```text
t180-ioring/
  SKILL.md
  .env
  requirements.txt
  scripts/
    enrich_intent.py
    validate_intent.py
    build_confirmed_config.py
    generate_schematic.py
    generate_layout.py
    check_virtuoso_connection.py
    run_il_with_screenshot.py
    run_drc.py
    run_lvs.py
  references/
    draft_builder_T180.md
    enrichment_rules_T180.md
    T180_Technology.md
    image_vision_instruction.md
  io_ring/
    config.py
    validation/json_validator.py
    layout/
      enrichment_engine.py
      confirmed_config.py
      generator.py
      layout_generator_factory.py
      process_config.py
      device_classifier.py
      position_calculator.py
      validator.py
      visualizer.py
      auto_filler.py
      filler_generator.py
      voltage_domain.py
      skill_generator.py
    schematic/
      generator.py
      device_parser.py
      devices/
        IO_device_info_T180.json
        device_wiring_T180.json
    editor/
      launcher.py
      confirm_merge.py
      utils.py
      draft_editor.html
      confirmation_editor.html
      vendor/
    bridge/
      __init__.py
  skill_code/
  calibre/
```

All runtime code and resources are under `io_ring/`, `skill_code/`, and `calibre/`.
