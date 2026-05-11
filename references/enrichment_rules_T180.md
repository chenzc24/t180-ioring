# Enrichment Rules - T180 (Phase 2)

## Purpose

Enrich the Phase 1 draft JSON with device types, pin connections, direction, domain, and corners.

## Semantic Intent Schema (Engine Input)

T180 now uses the same execution architecture as T28: the AI writes a compact
semantic intent file, then `scripts/enrich_intent.py` mechanically generates the
full intent graph.

Write semantic intent to `{output_dir}/io_ring_semantic_intent.json`:

```json
{
  "ring_config": {
    "process_node": "T180",
    "chip_width": 630,
    "chip_height": 630,
    "top_count": 4,
    "bottom_count": 4,
    "left_count": 4,
    "right_count": 4,
    "width": 12,
    "height": 12,
    "placement_order": "clockwise"
  },
  "domains": {
    "analog_1": {
      "kind": "analog",
      "vdd_consumer": "VIOLA",
      "vss_consumer": "GIOLA",
      "vdd_provider": "VIOHA",
      "vss_provider": "GIOHA"
    },
    "digital_1": {
      "kind": "digital",
      "vdd_consumer": "VIOLD",
      "vss_consumer": "GIOLD",
      "vdd_provider": "VIOHD",
      "vss_provider": "GIOHD"
    }
  },
  "instances": [
    {
      "name": "VIOLA",
      "position": "top_0",
      "type": "pad",
      "device": "PVDD1CDG",
      "domain": "analog_1"
    },
    {
      "name": "CKAZ",
      "position": "right_0",
      "type": "pad",
      "device": "PDDW0412SCDG",
      "domain": "digital_1",
      "direction": "input"
    }
  ]
}
```

Schema rules:

- T180 dimensional fields from the draft must be preserved: `chip_width`, `chip_height`, `top_count`, `bottom_count`, `left_count`, `right_count`, `pad_width`, `pad_height`, `pad_spacing`, and `corner_size` when present.
- `ring_config.width` and `ring_config.height` are compatibility count fields. If omitted, the engine derives them from the side counts.
- `ring_config.placement_order` must be copied from the draft.
- `domains` keys are concrete voltage-domain block ids. Use `kind: "analog"` or `kind: "digital"`.
- Every domain must define `vdd_consumer`, `vss_consumer`, `vdd_provider`, and `vss_provider`.
- Every instance must preserve draft `name`, `position`, and `type`.
- Every instance must provide a base T180 `device` name: `PVDD1ANA`, `PVSS1ANA`, `PVDD1CDG`, `PVSS1CDG`, `PVDD2CDG`, `PVSS2CDG`, or `PDDW0412SCDG`.
- Every instance must set `domain` to one of the concrete domain ids in `domains`.
- `PDDW0412SCDG` instances must set `direction` to `input` or `output`.
- Do not include `pin_connection`, `view_name`, fillers, or corners in semantic intent.
- Do not add T28 orientation suffixes such as `_H_G` or `_V_G`; T180 devices use base names.

The engine writes `{output_dir}/io_ring_intent_graph.json` and adds:

- `pin_connection` using `io_ring/schematic/devices/device_wiring_T180.json`
- `view_name: "layout"`
- broad final `domain`: `analog`, `digital`, or `null`
- concrete `voltage_domain` id for pads
- four `PCORNER` instances at side transitions

Engine exit codes:

- `0`: success
- `1`: semantic input error; fix `io_ring_semantic_intent.json`
- `2`: wiring table or engine bug; stop and report
- `3`: gate failure; fix semantic classification/domain/provider assignment

## Scope

This phase adds the following fields to each instance:
- `device`
- `pin_connection`
- `direction` (Digital IO only)
- `domain`
- `view_name`

And inserts corner instances.

Mandatory inputs for Phase 2:
- Phase 1 draft JSON (primary source for structural fields)
- Original user prompt (source for explicit intent: voltage-domain assignment, provider naming, direction overrides)

Input precedence:
- Keep structural fields from Phase 1 draft immutable (`ring_config`, `name`, `position`, `type`) unless a hard inconsistency is reported.
- Apply constraints in this order when they do not conflict with immutable draft structure:
  1. Explicit user prompt constraints
  2. Default enrichment inference (rules below)

---

### Universal Ring Structure Principle

- **CRITICAL - Ring Structure Continuity**: IO RING is a **ring structure** (circular), so signals at the beginning and end of the list are adjacent. This applies to both analog and digital signals.
  - **General rule**: In a ring structure, if signals appear in two segments (one at the beginning of the list and one at the end of the list), they are considered contiguous because the list wraps around.
  - This principle applies to:
    - **Analog signals**: Voltage domain continuity
    - **Digital signals**: Digital domain continuity

### User Intent Priority

- **Absolute priority**: Strictly follow user-specified signal order, placement order, and all requirements.
- **Signal preservation**: Preserve all signals with identical names.
- **Placement sequence**: Process one side at a time, place signals and pads simultaneously.
- **Voltage domain configuration**:
  - **If user explicitly specifies**: MUST strictly follow user's specification exactly, do not modify or ask for confirmation.
  - **If user does NOT specify**: AI must analyze and create voltage domains automatically — every signal must belong to a voltage domain, and every voltage domain must have its own provider pair.

### T180 Multi-Voltage Domain Concepts

T180 supports multiple voltage domains within both analog and digital domains. Key concepts:

1. **Domain and voltage domain**: An IO Ring has two broad domains (analog and digital). Within each broad domain, there can be multiple voltage domains defined by different VDDPST/VSSPST label pairs (provider pairs).
2. **Voltage Domain Identification**: Each unique VDDPST/VSSPST label pair defines a specific voltage domain. Different VDDPST/VSSPST labels mean different voltage domains, even within the same broad domain (analog or digital).
3. **Voltage Domain Continuity**: Signals in the same voltage domain should form contiguous blocks. Ring structure continuity applies.
4. **Provider & Consumer Pairs Per Voltage Domain**: Each voltage domain block MUST have:
   - A **provider pair**: `PVDD2CDG` (VDDPST provider) + `PVSS2CDG` (VSSPST provider) — these provide the VDDPST/VSSPST signals for the domain.
   - A **consumer pair**: `PVDD1CDG` (VDD consumer) + `PVSS1CDG` (VSS consumer) — these are the regular VDD/VSS connections in the domain.
   - **Multiple `PVSS2CDG` instances allowed**: A voltage domain can have multiple `PVSS2CDG` pads with the **same signal name** (multiple VSSPST providers sharing one ground net).
   - **Only ONE `PVDD2CDG`**: A voltage domain MUST have exactly one `PVDD2CDG` (only one VDDPST provider). Multiple `PVDD2CDG` with different signal names in the same domain is **FORBIDDEN**.
   - Cannot share providers across voltage domains.
5. **Pin Configuration is Voltage-Domain-Based for VDDPST/VSSPST**:
   - **VDDPST/VSSPST pins** (voltage-domain-based): MUST connect to the corresponding provider signal names (`PVDD2CDG`'s name for VDDPST, `PVSS2CDG`'s name for VSSPST) in the **same** voltage domain. This is the core voltage-domain routing rule.
   - **VDD/VSS pins** (per voltage domain block): Connect to the consumer pair in the same voltage domain block. For power/ground consumer pads (PVDD1CDG/PVSS1CDG), VDD/VSS connects to **Self Name**. For other pads (providers, IO), VDD/VSS connects to the consumer pair signal names (ANA_CSM_PWR/ANA_CSM_GND or DIG_CSM_PWR/DIG_CSM_GND) in the same voltage domain block.
   - **AVDD/AVSS pins** (signal pins, NOT voltage-domain-based): Connect to **Self Name** (the pad's own signal name).
   - **Summary**: Only VDDPST/VSSPST are resolved from the voltage domain provider. All other pins use self-referencing or regular power/ground connections.

---

## Step 1: Signal Classification & Domain Assignment

### 1.1 Classification Priority (CRITICAL)

The priority for determining device type is:
1. **User Explicit Instruction** (e.g., "Signal X is Analog IO", "Domain is Analog"). **This overrides EVERYTHING.**
2. **Mandatory Dictionary** (Section 1.2 below).
3. **Naming Heuristics** (General Rule: if a device belongs to the analog domain, "V" in name implies `PVDD1ANA` and "G" in name implies `PVSS1ANA`.).

### 1.2 Mandatory Signal Classification Dictionary

This dictionary serves as a **reference default** only. **User-specified classification always takes priority.** If the user explicitly classifies a signal as a certain type (e.g., calls it analog IO), it MUST be classified as that type — even if the signal name appears in a different category below. Only use this dictionary when the user does NOT specify the type.

**Analog IO (Force Type: `PVDD1ANA` or `PVSS1ANA`):**

`MCLK`, `CDCKB`, `VDCKB`, `VDCK`, `GDCK`, `VDBS`, `GDBS`, `VNID`, `VPID`, `IPNI`, `IPPI`, `VINP`, `AVSC`, `AGSC`, `IINP`, `IINN`, `DVSC`, `DGSC`, `VCMSC`, `VNSC`, `VPSC`, `VPID`, `VNID`, `INPI`, `INNI`, `VDO`, `GDO`, `AVSF`, `AGSF`, `DGSF`, `DVSF`

**Digital IO (Force Type: `PDDW0412SCDG`):**

`FGCAL`, `DITM`, `CKTM`, `RSTM`, `DOTM`, `CKAZ`, `DOFG`, `CLKO`, `CONV`, `DA*` (e.g., DA0-DA14)

**Example:**
- `FGCAL` is listed under Digital IO above. However, if the user explicitly says "FGCAL is analog IO", then `FGCAL` MUST be classified as analog IO (`PVDD1ANA` or `PVSS1ANA`) — the user's specification overrides the dictionary.
- Conversely, `MCLK` is listed under Analog IO above. If the user explicitly says "MCLK is digital IO", then `MCLK` MUST be classified as digital IO (`PDDW0412SCDG`).
- Only when the user does NOT specify the type (e.g., just says "place FGCAL") should the dictionary default be used.

### 1.3 Basic Domain(Analog/Digital) Assignment Rules

**Critical - If user explicitly specifies domain → use user specification**
Else, determine domain based on these rules:
- Signals in the Analog IO list → `domain: "analog"`
- Signals in the Digital IO list → `domain: "digital"`
- Signals with names matching power/ground patterns (e.g., `V*`, `G*`, `VIOLA`, `GIOLA`, `VIOLD`, `GIOLD`) → determine domain from context:
  - If surrounded by analog signals → `domain: "analog"`
  - If surrounded by digital signals → `domain: "digital"`

**Domain Isolation**: Analog and Digital domains never share pin configurations or connections.

### 1.4 Voltage Domain Continuity & Multi-Domain Assignment

**CRITICAL - Voltage Domain Continuity in Signal Recognition**:
- **Analog signals**: Analog voltage domains should form contiguous blocks, which means that they are all connected with provider signals' VDDPST/VSSPST within that voltage domain.
- **Ring structure continuity applies** (see "Universal Ring Structure Principle" above).

**Provider & Consumer Pairs Per Voltage Domain**: Each voltage domain block MUST have:
- A **provider pair**: `PVDD2CDG` (VDDPST provider) + `PVSS2CDG` (VSSPST provider) — these provide the VDDPST/VSSPST signals for the domain.
- A **consumer pair**: `PVDD1CDG` (VDD consumer) + `PVSS1CDG` (VSS consumer) — these are the regular VDD/VSS connections in the domain.
- **Multiple `PVSS2CDG` instances allowed**: A voltage domain can have multiple `PVSS2CDG` pads with the **same signal name** (multiple VSSPST providers sharing one ground net).
- **Only ONE `PVDD2CDG`**: A voltage domain MUST have exactly one `PVDD2CDG` (only one VDDPST provider). Multiple `PVDD2CDG` with different signal names in the same domain is **FORBIDDEN**.
- Cannot share providers across voltage domains.

**IO voltage Domain Assignment**:
- All IO signals (analog and digital) must belong to a voltage domain. Each voltage domain is defined by its unique VDDPST/VSSPST provider pair.

**User Specification Priority**:
- **If user explicitly specifies voltage domains**: MUST strictly follow user's specification. User defines which signals belong to which voltage domain and which signals are providers.
- **If user does NOT specify**: Analyze signal names and create voltage domains automatically. Every signal must belong to a voltage domain. Each voltage domain must have at least one provider pair.

**Cross-Domain Provider Independence**:
- Each voltage domain identifies its provider signals independently within its own range.
- Same signal name in different voltage domains: each domain selects its own first occurrence as provider.

**What you should prepare for step 2**:
- voltage domain assignment for each signal (which voltage domain block it belongs to)
- Example:
`User Prompt:` 
Signal list:
12 pads per side. Single ring layout. Order: clockwise through right side, bottom side, left side, top side.
MCLK  VDCK GDCK VPID VNID IPPI IPNI VNSC AVSF AGSF CKAZ CKTM CONV RSTM DOFG CLKO DOTM GIOHD DA14 DA13 DA12 DA11 DA10 DA9 DA8 DA7 DA6 DA5 DA4 DA3 DA2 DA1 DA0 VIOHD VIOLD GIOLD GIOHD VDDIB VDID VSIS VSSIB DGSC VDCKB CDCKB VIOHA GIOHA GIOLA VIOLA 
Voltage domain requirements:
  - Digital signals use digital domain voltage domain (VIOLD/GIOLD/VIOHD/GIOHD)
  - from VDDIB to CDCKB use VDID and VSIS as voltage domain（VDDIB/VSSIB consumer）
  - from VIOHA to AGSF use VIOHA and GIOHA as voltage domain
`Voltage Domain Assignment Result:`
- Domain 1 (Analog): VDDIB, VDID, VSIS, VSSIB, DGSC, VDCKB, CDCKB (Voltage Domain: VDDPST provider `VDID`, VSSPST provider `VSIS`. Consumers: `VDDIB`/`VSSIB`)
- Domain 2 (Analog): VIOHA, GIOHA, GIOLA, VIOLA,MCLK, VDCK, GDCK, VPID, VNID, IPPI, IPNI, VNSC, AVSF, AGSF (Voltage Domain: VDDPST provider `VIOHA`, VSSPST provider `GIOHA`.consumers: `VIOLA`/`GIOLA`)
- Domain 3 (Digital): CKAZ, CKTM, CONV, RSTM, DOFG, CLKO, DOTM, DA14-DA0, VIOHD, VIOLD, GIOLD, GIOHD (Voltage Domain: VDDPST provider `VIOHD`, VSSPST provider `GIOHD`. Consumers: `VIOLD`/`GIOLD`)
---

### 1.5 Voltage Domain Provider Selection

**Provider & Consumer Selection Per Voltage Domain Block**:
- Each contiguous block of a voltage domain MUST have its own provider pair and consumer pair.

- **Voltage Domain Providers**:
  - `PVDD2CDG` (VDDPST provider): Connects VDDPST to its own signal name (self-referencing). **Exactly ONE per voltage domain block**.
  - `PVSS2CDG` (VSSPST provider): Connects VSSPST to its own signal name (self-referencing). **Multiple instances with the SAME signal name are allowed** per voltage domain block.

- **Voltage Domain Consumers**:
  - `PVDD1CDG` (VDD consumer): Connects VDD to its own signal name, VDDPST to the provider's label.
  - `PVSS1CDG` (VSS consumer): Connects VSS to its own signal name, VSSPST to the provider's label.

## Step 2: Device Selection

### 2.1 Voltage Domain Logic

**Priority for determining Voltage Domain (VD) vs Regular devices:**

1. **Priority 1 (User Explicit)**: If user explicitly specifies a signal as a voltage domain provider, use Voltage Domain devices (`PVDD2CDG`/`PVSS2CDG`).
2. **Priority 2 (Naming)**: If signal name matches conventions (e.g., `VIOH*`, `GIOH*`, `VPST`, `GPST`), use Voltage Domain devices (`PVDD2CDG`/`PVSS2CDG`).
3. **Priority 3 (First in Domain)**: If no naming match and user doesn't specify, select the first power signal and first ground signal in each voltage domain block as providers (`PVDD2CDG`/`PVSS2CDG`).
4. **Default**: All other power/ground signals use Regular devices (`PVDD1CDG`/`PVSS1CDG`).

**CRITICAL - Provider & Consumer Pairs Per Voltage Domain Block**:
- Each contiguous voltage domain block MUST have:
  - Exactly ONE `PVDD2CDG` (VDDPST provider) — the VDDPST pin connects to its own signal name.
  - One or more `PVSS2CDG` (VSSPST provider, same signal name) — the VSSPST pin connects to its own signal name. Multiple `PVSS2CDG` with the same signal name are allowed.
  - `PVDD1CDG` (VDD consumer) — for VDD-type signals that are not the VDDPST provider.
  - `PVSS1CDG` (VSS consumer) — for VSS-type signals with different names from the VSSPST provider.
- **FORBIDDEN**: Multiple `PVDD2CDG` with different signal names in the same voltage domain block.
- **FORBIDDEN**: `PVSS2CDG` instances with different signal names in the same voltage domain block (all `PVSS2CDG` in one domain must share the same signal name).
- If a voltage domain is split into multiple non-contiguous blocks (with ring wrap), each block needs its own provider pair and consumer pair.
- All consumer pads in that domain connect their VDDPST/VSSPST to the provider's labels.

### 2.2 Analog Domain Devices

| Signal Category | Condition | Device | Naming Convention Examples |
|:---|:---|:---|:---|
| **Analog IO** | Priority 1: User explicitly says "Analog IO". Priority 2: Name in Mandatory Dictionary. | Priority 1: User specifies. Priority 2:`PVDD1ANA` (if "V" in name) / `PVSS1ANA` (if "G" in name) | MCLK, CDCKB, VDCKB, VDCK, AVSC, AGSC, etc. |
| **Analog VD Power** | Priority 1: User says "Voltage Domain". Priority 2: Name matches `VIOHA`/`VDID`. | `PVDD2CDG` | VIOHA, VDID etc. |
| **Analog VD Ground** | Priority 1: User says "Voltage Domain". Priority 2: Name matches `GIOHA`/`GDID`. | `PVSS2CDG` | GIOHA, GDID etc. |
| **Analog Power** | Analog Domain Consumer (Regular) | `PVDD1CDG` | VIOLA, VDIB etc. |
| **Analog Ground** | Analog Domain Consumer (Regular) | `PVSS1CDG` | GIOLA, GDIB etc. |

### 2.3 Digital Domain Devices

| Signal Category | Condition | Device | Naming Convention Examples |
|:---|:---|:---|:---|
| **Digital IO** | Priority 1: User explicitly says "Digital IO". Priority 2: Name in Mandatory Dictionary. | `PDDW0412SCDG` | FGCAL, DITM, CKTM, RSTM, DOTM, DA0-DA14 etc. |
| **Digital VD Power** | Priority 1: User says "Voltage Domain". Priority 2: Name matches `VIOHD`/`VPST`. | `PVDD2CDG` | VIOHD, VPST etc. |
| **Digital VD Ground** | Priority 1: User says "Voltage Domain". Priority 2: Name matches `GIOHD`/`GPST`. | `PVSS2CDG` | GIOHD, GPST etc. |
| **Digital Power** | Digital Domain Consumer (Regular) | `PVDD1CDG` | VIOLD, VDIO etc. |
| **Digital Ground** | Digital Domain Consumer (Regular) | `PVSS1CDG` | GIOLD, GDIO etc. |

### 2.4 Corner Devices

| Signal Category | Condition | Device |
|:---|:---|:---|
| **Corner** | Corner Pad | `PCORNER` |

---

## Step 3: Pin Configuration (Voltage-Domain-Based)

**CRITICAL**: Configure `pin_connection` exactly according to these matrices. **Strictly isolate domains.**

### Global Pin Connection Rules (T180)

**Voltage-domain-based pin connections**:
- **VDDPST/VSSPST**: MUST connect to the voltage domain provider signal names in the **same** voltage domain. This is the ONLY voltage-domain-routed pin pair.
  - Consumer pads: VDDPST → provider's signal name (PVDD2CDG's name); VSSPST → provider's signal name (PVSS2CDG's name).
  - Provider pads: VDDPST/VSSPST → **Self Name** (self-referencing, providing the signal to the domain).
- **VDD/VSS**: Connect to the consumer pair (PVDD1CDG/PVSS1CDG) signal names in the **same** voltage domain block. This is also resolved per voltage domain — each voltage domain block has its own consumer pair.
  - Power/ground consumer pads (PVDD1CDG/PVSS1CDG): VDD/VSS → **Self Name**.
  - Provider pads (PVDD2CDG/PVSS2CDG): VDD → the PVDD1CDG consumer's name in this voltage domain block; VSS → the PVSS1CDG consumer's name in this voltage domain block.
  - IO pads (PDDW0412SCDG, PVDD1ANA/PVSS1ANA): VDD → the PVDD1CDG consumer's name in this voltage domain block; VSS → the PVSS1CDG consumer's name in this voltage domain block.
- **AVDD/AVSS** (analog IO only): Connect to **Self Name** (the pad's own analog signal).

**VDD/VSS Consistency per voltage domain block**: All pads within the **same** voltage domain block MUST connect VDD to the same consumer power signal and VSS to the same consumer ground signal. Different voltage domain blocks can have different VDD/VSS connections.

### 3.1 Analog Domain Pin Configuration

**Scope**: Devices with `domain: "analog"`.

**Label Sources (Analog Only — resolved per voltage domain block)**:
- **ANA_CSM_PWR**: Name of the `PVDD1CDG` consumer (VDD pad) in the **same** voltage domain block (e.g., `VDDIB` in Domain 2, `VIOLA` in Domain 3). Each voltage domain block has its own consumer pair.
- **ANA_CSM_GND**: Name of the `PVSS1CDG` consumer (VSS pad) in the **same** voltage domain block (e.g., `VSSIB` in Domain 2, `GIOLA` in Domain 3). Each voltage domain block has its own consumer pair.
- **ANA_VD_PWR**: Name of Analog Voltage Domain Power provider (`PVDD2CDG`) in the **same** voltage domain block (e.g., `VDID` in Domain 2, `VIOHA` in Domain 3). Each voltage domain has its own provider.
- **ANA_VD_GND**: Name of Analog Voltage Domain Ground provider (`PVSS2CDG`) in the **same** voltage domain block (e.g., `VSIS` in Domain 2, `GIOHA` in Domain 3). Each voltage domain has its own provider.

**Multi-Voltage Domain Pin Rules (T180-specific)**:
- T180 pins are the same for analog and digital (VDD, VSS, VDDPST, VSSPST), but the **label sources** differ based on domain.
- VDDPST/VSSPST labels determine which voltage domain a pad belongs to — connect to the provider (PVDD2CDG/PVSS2CDG) in the same voltage domain block.
- VDD/VSS labels connect to the consumer pair (PVDD1CDG/PVSS1CDG) in the **same** voltage domain block — NOT to consumers from other voltage domains.
- Pads in different voltage domains connect VDDPST/VSSPST to **different** provider labels AND VDD/VSS to **different** consumer labels.

| Device | VDD Pin Label | VSS Pin Label | VDDPST Pin Label | VSSPST Pin Label | Special Pins |
|:---|:---|:---|:---|:---|:---|
| **PVDD1ANA** | ANA_CSM_PWR | ANA_CSM_GND | ANA_VD_PWR | ANA_VD_GND | AVDD = **Self Name** |
| **PVSS1ANA** | ANA_CSM_PWR | ANA_CSM_GND | ANA_VD_PWR | ANA_VD_GND | AVSS = **Self Name** |
| **PVDD1CDG** | **Self Name** | ANA_CSM_GND | ANA_VD_PWR | ANA_VD_GND | - |
| **PVSS1CDG** | ANA_CSM_PWR | **Self Name** | ANA_VD_PWR | ANA_VD_GND | - |
| **PVDD2CDG** | ANA_CSM_PWR | ANA_CSM_GND | **Self Name** | ANA_VD_GND | - |
| **PVSS2CDG** | ANA_CSM_PWR | ANA_CSM_GND | ANA_VD_PWR | **Self Name** | - |

**Analog VDD/VSS Rule**: All pads' VDD/VSS pins connect to the consumer pair (PVDD1CDG/PVSS1CDG) in the **same** voltage domain block. VDD/VSS is resolved per voltage domain block, NOT globally.

### 3.2 Digital Domain Pin Configuration

**Scope**: Devices with `domain: "digital"`.

**Label Sources (Digital Only — resolved per voltage domain block)**:
- **DIG_CSM_PWR**: Name of the `PVDD1CDG` consumer (VDD pad) in the **same** voltage domain block (e.g., `VIOLD`). Each voltage domain block has its own consumer pair.
- **DIG_CSM_GND**: Name of the `PVSS1CDG` consumer (VSS pad) in the **same** voltage domain block (e.g., `GIOLD`). Each voltage domain block has its own consumer pair.
- **DIG_VD_PWR**: Name of Digital Voltage Domain Power provider (`PVDD2CDG`) in the **same** voltage domain block (e.g., `VIOHD`).
- **DIG_VD_GND**: Name of Digital Voltage Domain Ground provider (`PVSS2CDG`) in the **same** voltage domain block (e.g., `GIOHD`).

| Device | VDD Pin Label | VSS Pin Label | VDDPST Pin Label | VSSPST Pin Label | Special Pins |
|:---|:---|:---|:---|:---|:---|
| **PDDW0412SCDG** | DIG_CSM_PWR | DIG_CSM_GND | DIG_VD_PWR | DIG_VD_GND | - |
| **PVDD1CDG** | **Self Name** | DIG_CSM_GND | DIG_VD_PWR | DIG_VD_GND | - |
| **PVSS1CDG** | DIG_CSM_PWR | **Self Name** | DIG_VD_PWR | DIG_VD_GND | - |
| **PVDD2CDG** | DIG_CSM_PWR | DIG_CSM_GND | **Self Name** | DIG_VD_GND | - |
| **PVSS2CDG** | DIG_CSM_PWR | DIG_CSM_GND | DIG_VD_PWR | **Self Name** | - |

### 3.3 Corner Pin Configuration

| Device | Configuration |
|:---|:---|
| **PCORNER** | No `pin_connection` required. |

### 3.4 Label Source Resolution

**ANA_VD_PWR / ANA_VD_GND** (voltage-domain-based — resolves per voltage domain block):
- These labels resolve to the voltage domain provider signal names in the **same** voltage domain block.
- `ANA_VD_PWR` = Name of the `PVDD2CDG` instance in this voltage domain block (the VDDPST provider).
- `ANA_VD_GND` = Name of the `PVSS2CDG` instance in this voltage domain block (the VSSPST provider).
- In multi-domain scenarios, pads in different voltage domains connect VDDPST/VSSPST to **different** provider labels.
- Example: Domain 2 has provider `VDID`/`VSIS` → all pads in Domain 2 use VDDPST=`VDID`, VSSPST=`VSIS`. Domain 3 has provider `VIOHA`/`GIOHA` → all pads in Domain 3 use VDDPST=`VIOHA`, VSSPST=`GIOHA`.

**ANA_CSM_PWR / ANA_CSM_GND** (per voltage domain block — resolves to consumer pair):
- These labels resolve to the consumer pair (PVDD1CDG/PVSS1CDG) signal names in the **same** voltage domain block.
- `ANA_CSM_PWR` = Name of the `PVDD1CDG` consumer (VDD pad) in this voltage domain block.
- `ANA_CSM_GND` = Name of the `PVSS1CDG` consumer (VSS pad) in this voltage domain block.
- **CRITICAL**: Each voltage domain block has its OWN consumer pair. Do NOT use consumer names from a different voltage domain block.
- Example: Domain 2 has consumers `VDDIB`/`VSSIB` → all pads in Domain 2 use VDD=`VDDIB`, VSS=`VSSIB`. Domain 3 has consumers `VIOLA`/`GIOLA` → all pads in Domain 3 use VDD=`VIOLA`, VSS=`GIOLA`.
- **Consistency**: All pads within the **same** voltage domain block connect VDD to the same consumer power signal and VSS to the same consumer ground signal.

**DIG_VD_PWR / DIG_VD_GND** (voltage-domain-based — resolves per voltage domain block):
- Same logic as ANA_VD_PWR/ANA_VD_GND but within the digital domain section.
- `DIG_VD_PWR` = Name of the `PVDD2CDG` instance in this digital voltage domain block.
- `DIG_VD_GND` = Name of the `PVSS2CDG` instance in this digital voltage domain block.

**DIG_CSM_PWR / DIG_CSM_GND** (per voltage domain block — resolves to consumer pair):
- Same logic as ANA_CSM_PWR/ANA_CSM_GND but within the digital domain section.
- `DIG_CSM_PWR` = Name of the `PVDD1CDG` consumer in this digital voltage domain block (e.g., `VIOLD`).
- `DIG_CSM_GND` = Name of the `PVSS1CDG` consumer in this digital voltage domain block (e.g., `GIOLD`).
- **Consistency**: All pads within the **same** digital voltage domain block connect VDD/VSS to the same consumer pair.

---

## Step 4: Direction Determination (Digital IO Only)

### 4.1 Direction Rules

**Pre-Rule**: `direction` only has two valid values: `input` and `output`.

**Priority for determining `direction`:**

1. **User Explicit Instruction** (e.g., "`CKAZ` is Input", "`DA0-DA7` are Output"). **This overrides everything.**
2. **Signal-Direction Dictionary / Bus Annotation** (if provided by the user in text/image extraction result).
3. **Example** (only if no user instruction or dictionary info):
   - Input: `CKAZ`, `CONV`, `FGCAL`, `DITM`, `CKTM`, `RSTM`
   - Output: `DOTM`, `DOFG`, `CLKO`, `DA0-DA14`
4. **No Fallback**: If still unknown, keep `direction` unspecified and require explicit user confirmation.

### 4.2 Scope Constraints

- `direction` is required for Digital IO signal pads (e.g., `PDDW0412SCDG`).
- `direction` must NOT be added to analog-only pads, power/ground pads, or corner pads.

### 4.3 Conflict Handling

- If a user explicit instruction conflicts with any heuristic/example, follow the user explicit instruction.
- The template value `"direction": "input"` is an example only; do NOT treat it as a global fixed value.

---

## Step 5: Corner Insertion

### 5.1 Corner Rules

- Only one corner type in T180: `PCORNER`.
- Insert `PCORNER` instances at the exact transition points between sides during placement.
- Do not append corners at the end of the instances list.

### 5.2 Corner Identification

Corner positions are fixed regardless of placement order:
- `top_left`: Between Left-Last and Top-First.
- `top_right`: Between Top-Last and Right-First.
- `bottom_right`: Between Right-Last and Bottom-First.
- `bottom_left`: Between Bottom-Last and Left-First.

### 5.3 Corner Instance Template

```json
{
  "name": "CORNER_TL",
  "device": "PCORNER",
  "view_name": "layout",
  "domain": "null",
  "position": "top_left",
  "type": "corner"
}
```

---

## Step 6: Per-Instance Fields

Each enriched instance must include these additional fields:

| Field | Value |
|-------|-------|
| `view_name` | `"layout"` |
| `domain` | `"analog"` or `"digital"` or `"null"` (for corners) |

---

## Pre-Save Rule Gates

Before saving the final JSON, verify these gates pass:

### Continuity Gate
- Signals assigned to the same domain must form contiguous blocks.
- Ring structure continuity applies (start and end of list are adjacent).

### Voltage Domain Continuity Gate
- Signals in the same voltage domain (same VDDPST/VSSPST labels) must form contiguous blocks.
- If a voltage domain is split into multiple blocks, each block MUST have its own provider pair.

### Position-Identity Gate
- Every instance has a unique position.
- Position format matches the expected pattern (`side_index` or corner positions).

### VSS-Consistency Gate
- All pads within the **same voltage domain block** must connect VSS to the same consumer ground signal (ANA_CSM_GND for analog, DIG_CSM_GND for digital).
- VDD/VSS are resolved **per voltage domain block**, NOT globally. Different voltage domain blocks can have different VDD/VSS connections.

### Provider-Count Gate
- Each voltage domain block MUST have exactly ONE `PVDD2CDG` (VDDPST provider) and at least one `PVSS2CDG` (VSSPST provider).
- Multiple `PVSS2CDG` instances with the **same signal name** are allowed in a single voltage domain block.
- **FORBIDDEN**: More than one `PVDD2CDG` in the same voltage domain block.
- **FORBIDDEN**: `PVSS2CDG` instances with different signal names in the same voltage domain block (all `PVSS2CDG` in one domain must share the same signal name).
- Each voltage domain block MUST also have at least one consumer pair (`PVDD1CDG` + `PVSS1CDG`).
- Voltage domain providers must be identified correctly based on naming or explicit user specification.
- Multiple provider pairs are allowed for different voltage domains, but each voltage domain block follows the rules above.

---

## Final JSON Templates

### Analog Instance — IO in Domain 3 (No `direction`)

```json
{
  "name": "ANA_SIG_NAME",
  "device": "PVDD1ANA",
  "view_name": "layout",
  "domain": "analog",
  "position": "top_0",
  "type": "pad",
  "pin_connection": {
    "VDD": {"label": "VIOLA"},
    "VSS": {"label": "GIOLA"},
    "VDDPST": {"label": "VIOHA"},
    "VSSPST": {"label": "GIOHA"},
    "AVDD": {"label": "ANA_SIG_NAME"}
  }
}
```
**Note**: VDD=`VIOLA` and VSS=`GIOLA` are the consumer pair (PVDD1CDG/PVSS1CDG) in Domain 3. VDDPST/VSSPST connect to the Domain 3 providers.

### Analog Instance — Consumer in Domain 2 (PVDD1CDG)

```json
{
  "name": "VDDIB",
  "device": "PVDD1CDG",
  "view_name": "layout",
  "domain": "analog",
  "position": "top_1",
  "type": "pad",
  "pin_connection": {
    "VDD": {"label": "VDDIB"},
    "VSS": {"label": "VSSIB"},
    "VDDPST": {"label": "VDID"},
    "VSSPST": {"label": "VSIS"}
  }
}
```
**Note**: VDD=`VDDIB` (Self Name), VSS=`VSSIB` (consumer pair in Domain 2), VDDPST=`VDID`/VSSPST=`VSIS` (providers in Domain 2).

### Analog Instance — Provider in Domain 2 (PVSS2CDG)

```json
{
  "name": "VSIS",
  "device": "PVSS2CDG",
  "view_name": "layout",
  "domain": "analog",
  "position": "top_3",
  "type": "pad",
  "pin_connection": {
    "VDD": {"label": "VDDIB"},
    "VSS": {"label": "VSSIB"},
    "VDDPST": {"label": "VDID"},
    "VSSPST": {"label": "VSIS"}
  }
}
```
**Note**: VDD=`VDDIB`, VSS=`VSSIB` — connects to the **consumer pair in the SAME voltage domain (Domain 2)**, NOT to consumers from other domains.

### Digital Instance (Requires `direction`)

```json
{
  "name": "DIG_SIG_NAME",
  "device": "PDDW0412SCDG",
  "view_name": "layout",
  "domain": "digital",
  "position": "top_1",
  "type": "pad",
  "direction": "input",
  "pin_connection": {
    "VDD": {"label": "VIOLD"},
    "VSS": {"label": "GIOLD"},
    "VDDPST": {"label": "VIOHD"},
    "VSSPST": {"label": "GIOHD"}
  }
}
```

### Corner Instance

```json
{
  "name": "CORNER_TL",
  "device": "PCORNER",
  "view_name": "layout",
  "domain": "null",
  "position": "top_left",
  "type": "corner"
}
```
