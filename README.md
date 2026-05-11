# io-ring-orchestrator-T180

> **AI Agent:** Skip to [Agent Setup Guide](#-agent-setup-guide) below for
> executable installation steps with concrete commands and ask/write tables.

A Claude Code skill for automated IO Ring generation on TSMC 180nm (T180) process
nodes — from natural-language requirements to verified layout, including JSON
construction, Cadence SKILL generation, Virtuoso execution, and DRC/LVS.

---

<!--=======================================================================-->
<!-- PART 1 — HUMAN GUIDE                                                   -->
<!-- Quick orientation, prerequisites, config reference, usage              -->
<!--=======================================================================-->

## Overview

`io-ring-orchestrator-T180` depends on **virtuoso-bridge-lite** for all Virtuoso
communication (TCP + SSH). The project layout after setup:

```
<project-root>/
├── .venv/                          ← one shared Python env (bridge + all skills)
├── virtuoso-bridge-lite/           ← bridge source
└── .claude/skills/
    └── io-ring-orchestrator-T180/
        ├── .env                    ← T180 skill config (CDS_LIB_PATH_180, VB_FS_MODE)
        └── calibre/
            └── site_local.csh      ← Calibre/PDK paths on the EDA server (you fill this in)
```

### How the system works

```
Claude Code (your machine)
       │
       │  1. Generates JSON + SKILL scripts locally
       │
       ▼
virtuoso-bridge-lite
       │
       ├─ TCP socket ──────────────► Virtuoso daemon (EDA server)
       │                              loads .il, returns results
       │
       └─ SSH tunnel ──────────────► EDA server
              │
              ├─ uploads .il file → Virtuoso load()
              ├─ uploads calibre/ scripts → runs csh
              └─ downloads reports / screenshots
```

**Filesystem mode** controls how Calibre scripts and output files are exchanged:

| Mode | When | Behavior |
|---|---|---|
| `remote` | Windows PC, or no NFS | Scripts uploaded to `/tmp/vb_t180_calibre_${USER}/` via SSH; results downloaded back |
| `shared` | Linux on same NFS as EDA server | Both machines see the same paths; Calibre reads/writes directly |

Auto-detected: Windows path (`C:\...`) → `remote`; NFS probe → `shared`. Set `VB_FS_MODE` in `.env` to override.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.9+ | Local machine |
| Git | For cloning repos |
| Cadence Virtuoso | On the EDA server — required for SKILL execution and screenshots |
| Calibre (Mentor/Siemens) | On the EDA server — required for DRC and LVS |
| TSMC 180nm PDK | On the EDA server — layer map, LVS include files, `cds.lib`, IO library `tpd018bcdnv5` |
| `csh` | On the EDA server — Calibre wrapper scripts are written in csh |

---

## Quick Setup (Human)

**1. Clone and install:**
```bash
# At your project root:
git clone https://github.com/chenzc24/virtuoso-bridge-lite.git
mkdir -p .claude/skills
git clone https://github.com/chenzc24/io-ring-orchestrator-T180.git .claude/skills/io-ring-orchestrator-T180
```
```bash
# Create venv and install (Linux/Mac/Git Bash):
python -m venv .venv && source .venv/bin/activate
# Windows PowerShell:  python -m venv .venv; .venv\Scripts\Activate.ps1

pip install -e virtuoso-bridge-lite
pip install -r .claude/skills/io-ring-orchestrator-T180/requirements.txt
```

**2. Configure bridge connection:**

The bridge `.env` is created by `virtuoso-bridge init`. See
[`virtuoso-bridge-lite/README.md`](https://github.com/chenzc24/virtuoso-bridge-lite#quick-start)
for full details (jump hosts, multi-profile, local mode).

> Make sure the `.venv` is activated before running any `virtuoso-bridge` commands.

```bash
virtuoso-bridge init <username>@<eda-server>    # creates ~/.virtuoso-bridge/.env
# With jump host:
# virtuoso-bridge init <username>@<eda-server> -J <username>@<jump-host>
```

**3. Configure T180 skill `.env`:**

Edit `.claude/skills/io-ring-orchestrator-T180/.env` — the fields marked `# <-- CHANGE`:

| Variable | Required | What to set |
|---|---|---|
| `CDS_LIB_PATH_180` | Yes | Remote Linux path to your T180 `cds.lib` |
| `VB_FS_MODE` | Optional | `remote` (Windows) or `shared` (NFS Linux). Auto-detected if blank. |
| `AMS_DRAFT_EDITOR` | Optional | `on` or `off` — open Draft Editor after Step 2 (default: `on`) |
| `AMS_LAYOUT_EDITOR` | Optional | `on` or `off` — open Confirmation Editor at Step 6 (default: `on`) |

**4. Configure `site_local.csh`** (Calibre/PDK paths on the EDA server):
```bash
cd .claude/skills/io-ring-orchestrator-T180/calibre
cp site_local.csh.example site_local.csh   # then edit with your site paths
```

Set `MGC_HOME`, `PDK_LAYERMAP_180`, `incFILE_180`, and source your site's Cadence/Mentor
cshrc files. Do **not** edit `env_common.csh` — `site_local.csh` overrides it.

**5. Start bridge and verify:**
```bash
virtuoso-bridge start
virtuoso-bridge status                  # tunnel ✓  daemon ✓
```
In Virtuoso CIW, load the daemon SKILL file once per session (path printed by `start`):
```skill
load("/tmp/virtuoso_bridge_<user>/virtuoso_bridge/virtuoso_setup.il")
```
```bash
# Run from project root:
.venv/bin/python .claude/skills/io-ring-orchestrator-T180/scripts/check_virtuoso_connection.py
# Windows: .venv\Scripts\python.exe .claude\skills\io-ring-orchestrator-T180\scripts\check_virtuoso_connection.py
```

**Auto-activate `.venv`:** Set VS Code to use `.venv` as the interpreter, or add
`echo 'source .venv/bin/activate' > .envrc && direnv allow` (Linux/Mac).
Claude Code finds `.venv` automatically — no manual activation needed for skill runs.

---

## Workflow

The skill runs a 12-step pipeline automatically:

```
 1.  Parse input → create timestamped output directory
 2.  Build draft intent graph JSON (structure only)
 2b. [Optional] Draft Editor — visual pad placement (skip if AMS_DRAFT_EDITOR=off)
 3.  Enrich draft → final intent graph (devices, pins, corners, voltage domains)
 4.  Reference-guided gate check (continuity, provider count, pin families)
 5.  Validate JSON (validate_intent.py)
 6.  Build confirmed config — optionally open Layout Editor (see below)
 7.  Generate schematic SKILL (.il)
 8.  Generate layout SKILL (.il)
 9.  Check Virtuoso connection
10.  Execute SKILL in Virtuoso + capture screenshots
11.  Run Calibre DRC
12.  Run Calibre LVS   [optional: PEX after LVS]
```

Output files land in `${AMS_OUTPUT_ROOT}/generated/<YYYYMMDD_HHMMSS>/`:
`io_ring_intent_graph.json`, `io_ring_confirmed.json`, `io_ring_schematic.il`,
`io_ring_layout.il`, `schematic_screenshot.png`, `layout_screenshot.png`,
`drc_report.txt`, `lvs_report.txt`.

---

## Draft Editor (Step 2b)

When `AMS_DRAFT_EDITOR=on` (default), a browser editor opens after Step 2 for
visual pad placement. Users can drag pads between sides, add/remove pads,
set `device` type, set `domain` (digital/analog), and confirm structural layout
before enrichment (Step 3).

**Skip when:** `AMS_DRAFT_EDITOR=off` AND user did not request the editor.
Users can still request the editor by saying *"I want to use the editor"* —
the `.env` setting is a default, not a hard gate.

---

## Layout Editor / Confirmation Editor (Step 6)

When `AMS_LAYOUT_EDITOR=on` (default), the skill asks at Step 6:
> *"The layout is ready for confirmation. Open the visual Layout Editor?"*
> (no response within ~15 s → skip automatically)

**If opened:** a browser launches on `localhost` showing the IO ring as an
interactive SVG. Every pad, corner, and filler is draggable and editable.
Click **"Confirm & Continue"** when done — edits are merged back into the
confirmed config and the pipeline resumes.

**Component colors:**

| Category | Color | Examples |
|---|---|---|
| Analog IO | Blue | `PVDD1ANA`, `PVSS1ANA` |
| Digital devices (all) | Green | `PDDW0412SCDG`, `PVDD1CDG`, `PVSS1CDG`, `PVDD2CDG`, `PVSS2CDG` |
| Corners | Red | `PCORNER` |
| Fillers / Blank | Gray / Red | `PFILLER10`, `PFILLER20`, `blank` |

**Key operations:** drag to move · click Inspector to edit properties · Ctrl+Z undo ·
toolbar Add/Delete · Import/Export JSON · Confirm & Continue to proceed.

---

## T180 Device Reference

T180 uses the `tpd018bcdnv5` IO library with a unified pad architecture (same
power pins for analog and digital, distinguished by voltage-domain label routing).

| Signal type | Device | Notes |
|---|---|---|
| Analog IO (V-type) | `PVDD1ANA` | Analog signal pad with AVDD pin; "V" in name → V-type |
| Analog IO (G-type) | `PVSS1ANA` | Analog signal pad with AVSS pin; "G" in name → G-type |
| Voltage-domain power provider | `PVDD2CDG` | VDDPST provider; exactly ONE per voltage domain |
| Voltage-domain ground provider | `PVSS2CDG` | VSSPST provider; multiple with same name allowed per domain |
| Power consumer | `PVDD1CDG` | Regular VDD pad; VDD → Self Name |
| Ground consumer | `PVSS1CDG` | Regular VSS pad; VSS → Self Name |
| Digital IO | `PDDW0412SCDG` | Bidirectional digital pad; requires `direction` field |
| Corner | `PCORNER` | Single corner type for all pad adjacencies |
| Filler | `PFILLER10` / `PFILLER20` | Inserted between different voltage domains |

### Pad Dimensions (defaults)

| Parameter | Value |
|---|---|
| `pad_width` | 80 µm |
| `pad_height` | 120 µm |
| `pad_spacing` | 90 µm |
| `corner_size` | 130 µm |

### Pin Architecture

All power pads share a common pin set: `VDD`, `VSS`, `VDDPST`, `VSSPST`.
Analog IO adds `AVDD`/`AVSS` as signal pins. Digital IO adds `PAD`, `I`, `OEN`,
`DS`, `IE`, `PE`, `C` pins.

Pin connections are **voltage-domain-based**: `VDDPST`/`VSSPST` connect to the
provider's signal name within the same voltage domain block; `VDD`/`VSS` connect
to the consumer pair in the same block.

---

## Multi-Voltage Domain Support

T180 supports multiple voltage domains within both analog and digital sections.
Each voltage domain block MUST have:

- Exactly **ONE** `PVDD2CDG` (VDDPST provider)
- One or more `PVSS2CDG` (VSSPST provider, same signal name)
- A consumer pair: `PVDD1CDG` + `PVSS1CDG`

Different `VDDPST`/`VSSPST` label pairs define different voltage domains.
Filler pads (`PFILLER10`) are automatically inserted between adjacent pads
belonging to different voltage domains.

---

## Usage

**Via Claude Code (natural language):**
```
Generate T180 IO ring with signals: MCLK, VIOLA, GIOLA, VIOHA, GIOHA, FGCAL, DITM.
4 pads per side, clockwise placement.
Library: LLM_Layout_Design, Cell: IO_RING_test.
```
Or explicitly: `Use io-ring-orchestrator-T180 to generate an IO ring with...`

### Writing Effective Prompts

The skill classifies signals by **name pattern** and **voltage domain assignment**.
For non-standard names, always specify explicitly — it overrides all inference.

**Required in every prompt:**
- Signal list (in placement order)
- Pads per side (e.g. `4 pads per side` or `top=4, bottom=4, left=2, right=2`)
- Placement order: `clockwise` or `counterclockwise`
- Library and cell name

**Signal classification (how the skill decides device type):**

| Signal type | Auto-detected when | Device |
|---|---|---|
| Analog IO | Name matches analog patterns (MCLK, VDCK, AVSC…) or user-specified | `PVDD1ANA` / `PVSS1ANA` |
| Voltage-domain provider | Name matches `VIOH*`/`GIOH*`/`VPST`/`GPST` or user-specified | `PVDD2CDG` / `PVSS2CDG` |
| Power/ground consumer | Other VDD/VSS signals in the domain | `PVDD1CDG` / `PVSS1CDG` |
| Digital IO | Name matches digital patterns (FGCAL, DA*, CKTM…) or user-specified | `PDDW0412SCDG` |
| Corner | Inferred at side transitions | `PCORNER` |

**Full recommended prompt:**
```
Task: Generate IO ring schematic and layout for Cadence Virtuoso.
4 pads per side. Clockwise placement.

Signals: MCLK VDCK GDCK VPID VNID IPPI IPNI VNSC AVSF AGSF CKAZ CKTM CONV RSTM DOFG CLKO DOTM GIOHD DA14 DA13

Signal classification:
- Analog IO: MCLK, VDCK, GDCK, VPID, VNID, IPPI, IPNI, VNSC, AVSF, AGSF
- Digital IO: CKAZ, CKTM, CONV, RSTM, DOFG, CLKO, DOTM, DA14, DA13

Voltage domains:
- Analog: VIOHA/GIOHA → consumers VIOLA/GIOLA
- Digital: VIOHD/GIOHD → consumers VIOLD/GIOLD

Technology: 180nm  |  Library: LLM_Layout_Design  |  Cell: IO_RING_mixed
```

---

## Configuration Reference

### Bridge `.env` variables

Bridge connection is configured via `virtuoso-bridge init`. See
[`virtuoso-bridge-lite/README.md`](https://github.com/chenzc24/virtuoso-bridge-lite#quick-start)
for the full reference (`VB_REMOTE_HOST`, `VB_REMOTE_USER`, jump hosts, multi-profile, etc.).

### T180 skill `.env` variables

| Variable | Description | Required |
|---|---|---|
| `CDS_LIB_PATH_180` | Remote path to T180 `cds.lib` | Yes |
| `VB_FS_MODE` | `shared` or `remote` (auto-detect if blank) | No |
| `AMS_DRAFT_EDITOR` | `on` or `off` — Draft Editor at Step 2b (default: `on`) | No |
| `AMS_LAYOUT_EDITOR` | `on` or `off` — Confirmation Editor at Step 6 (default: `on`) | No |
| `AMS_OUTPUT_ROOT` | Output root (default: `./output`) | No |

These live in `.claude/skills/io-ring-orchestrator-T180/.env`.

### `site_local.csh` variables

| Variable | Description |
|---|---|
| `MGC_HOME` | Calibre installation root on EDA server |
| `PDK_LAYERMAP_180` | T180 PDK layer map file |
| `incFILE_180` | T180 LVS include file (`source.added`) |

`env_common.csh` defaults are applied only if the variable is **not** set by
`site_local.csh` or the shell — all `setenv` calls are guarded by `if ( ! $?VAR )`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Virtuoso connection fails | `virtuoso-bridge status` → `restart`; confirm daemon `.il` loaded in CIW |
| DRC/LVS path errors | Check `CDS_LIB_PATH_180` in `.env`; check `MGC_HOME` / `PDK_LAYERMAP_180` / `incFILE_180` in `site_local.csh` |
| Wrong output location | Set `AMS_OUTPUT_ROOT` in `.env` |
| Skill not triggering | Say `Use io-ring-orchestrator-T180 to...`; verify `SKILL.md` exists in `.claude/skills/` |
| `import virtuoso_bridge` fails | Run `pip install -e virtuoso-bridge-lite` inside the project `.venv` |
| Draft Editor not opening | Check `AMS_DRAFT_EDITOR` in `.env`; ensure port is not blocked |
| Voltage domain continuity fails | Check VDDPST/VSSPST labels — different labels mean different domains |

---

## Related Documentation

| Document | Description |
|---|---|
| `SKILL.md` | Full workflow contract — Steps 0–12, repair loops, troubleshooting |
| `references/draft_builder_T180.md` | Structural draft JSON generation rules |
| `references/enrichment_rules_T180.md` | Signal classification, device selection, pin connection rules |
| `references/T180_Technology.md` | DRC rules and process details |
| `virtuoso-bridge-lite/README.md` | Bridge CLI, SSH tunnel, daemon, multi-profile setup |

---

<!--=======================================================================-->
<!-- PART 2 — AI AGENT SETUP GUIDE                                          -->
<!-- Executable steps. No placeholders. 🤖 = run directly, ❓ = ask user.  -->
<!--=======================================================================-->

## 🤖 Agent Setup Guide

> **Human readers:** This section is written for AI agents performing automated
> setup. You can read it as a detailed reference, but the [Human Guide](#quick-setup-human)
> above covers everything you need more concisely.

Steps marked **🤖** can be executed with the exact commands shown.
Steps marked **❓ → 🤖** require collecting values from the user first, then
writing them into the specified file. Every repo URL and command is concrete.

---

### Step 0 — Clone repositories 🤖

```bash
# Run from the project root directory:
git clone https://github.com/chenzc24/virtuoso-bridge-lite.git
mkdir -p .claude/skills
git clone https://github.com/chenzc24/io-ring-orchestrator-T180.git .claude/skills/io-ring-orchestrator-T180
```

The skill lands in `.claude/skills/io-ring-orchestrator-T180/` — Claude Code
discovers skills in `.claude/skills/` automatically. Bridge repo stays at project root.

---

### Step 1 — Create project `.venv` and install packages 🤖

```bash
python -m venv .venv

# Activate (choose by OS):
source .venv/bin/activate          # Linux / Mac / Git Bash
# .venv\Scripts\Activate.ps1       # Windows PowerShell
# .venv\Scripts\activate.bat       # Windows CMD

pip install -e virtuoso-bridge-lite
pip install -r .claude/skills/io-ring-orchestrator-T180/requirements.txt

# Verify:
python -c "import virtuoso_bridge; print('ok:', virtuoso_bridge.__version__)"
virtuoso-bridge --version          # expect: 0.6.x
```

One `.venv` serves all skills. To add a second skill later: `pip install -r .claude/skills/<other-skill>/requirements.txt`.

---

### Step 2 — Initialize bridge config ❓ → 🤖

> All subsequent steps require the `.venv` to be active. If in a new terminal, run:
> `source .venv/bin/activate` (Linux/Mac) or `.venv\Scripts\Activate.ps1` (Windows).

**Ask user — required:**

| Question to ask user |
|---|
| "Hostname or IP of your EDA server?" |
| "SSH username on that server?" |

Then run `virtuoso-bridge init` to create the bridge `.env` with correct format and defaults:

```bash
virtuoso-bridge init <username>@<eda-server>
# With jump host:
# virtuoso-bridge init <username>@<eda-server> -J <username>@<jump-host>
```

This writes `~/.virtuoso-bridge/.env` with all bridge variables
(`VB_REMOTE_HOST`, `VB_REMOTE_USER`, ports, jump host, etc.) in the correct format.
**Do not** write the bridge `.env` manually — always use `virtuoso-bridge init`.

For advanced options (multi-profile, local mode, custom ports), see
[`virtuoso-bridge-lite/README.md`](https://github.com/chenzc24/virtuoso-bridge-lite#quick-start).

---

### Step 3 — Configure T180 skill `.env` ❓ → 🤖

**Ask user — required:**

| Variable | Question to ask user |
|---|---|
| `CDS_LIB_PATH_180` | "Remote Linux path to your T180 `cds.lib`? (e.g. `/home/youruser/TSMC180/cds.lib`)" |

Write the value into `.claude/skills/io-ring-orchestrator-T180/.env`. The file ships
pre-filled with defaults — use the Edit tool to update only the `CDS_LIB_PATH_180` line
(the one marked `# <-- CHANGE path`), replacing the example path with the user's actual path.

**Optional — ask user if they want to customize:**

| Variable | Question | Default |
|---|---|---|
| `AMS_DRAFT_EDITOR` | "Enable Draft Editor (visual pad placement before enrichment)?" | `on` |
| `AMS_LAYOUT_EDITOR` | "Enable Confirmation Editor (visual layout review at Step 6)?" | `on` |

---

### Step 4 — Write `site_local.csh` ❓ → 🤖

```bash
cp .claude/skills/io-ring-orchestrator-T180/calibre/site_local.csh.example \
   .claude/skills/io-ring-orchestrator-T180/calibre/site_local.csh
```

> **Note:** If `site_local.csh.example` does not exist, create `site_local.csh` from
> scratch (see template below).

**Ask user — required:**

| What | Question to ask user |
|---|---|
| Cadence cshrc path | "Path to site's Cadence setup script on EDA server? (e.g. `/home/cshrc/.cshrc.cadence.IC618SP201`)" |
| Mentor cshrc path | "Path to site's Mentor setup script? (e.g. `/home/cshrc/.cshrc.mentor`)" |
| `MGC_HOME` | "Calibre install root on EDA server? (e.g. `/home/mentor/calibre/calibre2022/aoj_cal_2022.1_36.16`)" |
| `PDK_LAYERMAP_180` | "T180 PDK layer map path on EDA server? (e.g. `/home/process/tsmc180bcd_gen2_2022/PDK/TSMC180BCD/tsmc18/tsmc18.layermap`)" |
| `incFILE_180` | "T180 LVS `source.added` path on EDA server?" |

Write values directly into `site_local.csh`. Example of a complete filled-in file:

```csh
source /home/cshrc/.cshrc.cadence.IC618SP201
source /home/cshrc/.cshrc.mentor
setenv MGC_HOME /home/mentor/calibre/calibre2022/aoj_cal_2022.1_36.16
setenv PDK_LAYERMAP_180 /home/process/tsmc180bcd_gen2_2022/PDK/TSMC180BCD/tsmc18/tsmc18.layermap
setenv incFILE_180 /home/dmanager/shared_lib/TSMC180MS/calibre_rule/lvs/source.added
```

---

### Step 5 — Start bridge and verify 🤖

```bash
virtuoso-bridge start         # opens SSH tunnel + deploys daemon on EDA server
virtuoso-bridge status        # expect: tunnel ✓  daemon ✓
```

Instruct user to load the daemon SKILL file in Virtuoso CIW once per Virtuoso session.
`virtuoso-bridge start` prints the exact path to load:
```skill
load("/tmp/virtuoso_bridge_<user>/virtuoso_bridge/virtuoso_setup.il")
```

Verify end-to-end:
```bash
# Linux/Mac/Git Bash:
.venv/bin/python .claude/skills/io-ring-orchestrator-T180/scripts/check_virtuoso_connection.py
# Windows PowerShell:
# .venv\Scripts\python.exe .claude\skills\io-ring-orchestrator-T180\scripts\check_virtuoso_connection.py
# Success: ✅ Virtuoso Connection: OK
# Failure: follow printed instructions; run `virtuoso-bridge restart` if tunnel is down
```

---

### Setup complete ✅

```
<project-root>/
├── .venv/                                         ← shared env (bridge + all skills)
├── virtuoso-bridge-lite/                          ← bridge source (editable install)
└── .claude/skills/io-ring-orchestrator-T180/
    ├── .env                                       ← T180 skill config (CDS_LIB_PATH_180, VB_FS_MODE, editors)
    └── calibre/
        └── site_local.csh                         ← written in Step 4
```

Bridge config lives in `~/.virtuoso-bridge/.env` (created by `virtuoso-bridge init` in Step 2).
`AMS_PYTHON` in `SKILL.md` Step 0 finds `.venv` at project root automatically —
no manual activation needed when Claude Code runs scripts.
