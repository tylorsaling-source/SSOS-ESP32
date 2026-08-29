# `basic_surv` 48-field input contract

This document removes the guesswork between the `basic_surv` world and the
SSOS-ESP32 V2 model head. The adapter accepts either the exact ordered array
below or a JSON object using these field names. The named form is recommended:
it prevents a reordered value from silently becoming a different input.

## The complete data path

```text
named world state (48 values)
  -> fixed field order below
  -> latent8 = tanh(projection_weight @ observation48 + projection_bias)
  -> tensor9 = [latent8[0] ... latent8[7], 1.0]
  -> ESP32 V2 computes eight raw Q10-head scores
```

No additional normalization occurs in `host/basic_surv_9d.py`. The formulas in
this table are the normalization contract.

| # | Field | Value supplied to the projection |
| ---: | --- | --- |
| 1–8 | `health`, `hunger`, `thirst`, `temperature`, `battery`, `injury`, `rest_debt`, `daylight` | World state as a normalized float, normally 0 to 1 |
| 9–10 | `wood`, `stone` | Inventory count divided by 5 |
| 11 | `has_tool` | 0 or 1 |
| 12–14 | `raw_water`, `purified_water`, `food_units` | Inventory count divided by 3 |
| 15–16 | `shelter_progress`, `fire_level` | World state, 0 to 1 |
| 17–28 | `exit_dx`, `exit_dz`, `wood_dx`, `wood_dz`, `stone_dx`, `stone_dz`, `water_dx`, `water_dz`, `food_dx`, `food_dz`, `hazard_dx`, `hazard_dz` | `(target coordinate - creature coordinate) / 20.0` |
| 29 | `hazard_distance` | `min(1, nearest-hazard distance / 20.0)` |
| 30–31 | `shelter_dx`, `shelter_dz` | `(shelter coordinate - creature coordinate) / 20.0` |
| 32 | `coverage` | Fraction of the world visited, 0 to 1 |
| 33 | `steps_remaining` | `1 - step_count / 700` |
| 34–35 | `x`, `z` | Creature coordinate divided by 20.0 |
| 36–47 | `proposal_*` | One-hot proposal over the 12 actions below |
| 48 | `bias` | Always exactly 1.0 |

The proposal order is:

```text
north, south, west, east, gather, process_water, consume, craft_tool,
build_shelter, build_fire, first_aid, rest
```

The 48 fields, in exact array order, are:

```text
health, hunger, thirst, temperature, battery, injury, rest_debt, daylight,
wood, stone, has_tool, raw_water, purified_water, food_units,
shelter_progress, fire_level, exit_dx, exit_dz, wood_dx, wood_dz, stone_dx,
stone_dz, water_dx, water_dz, food_dx, food_dz, hazard_dx, hazard_dz,
hazard_distance, shelter_dx, shelter_dz, coverage, steps_remaining, x, z,
proposal_north, proposal_south, proposal_west, proposal_east, proposal_gather,
proposal_process_water, proposal_consume, proposal_craft_tool,
proposal_build_shelter, proposal_build_fire, proposal_first_aid, proposal_rest,
bias
```

## Recommended named input

Create a JSON object with every name above, then run:

```powershell
python .\host\basic_surv_9d.py .\my-observation.json
```

The adapter reports any missing or unknown names instead of silently changing
their meaning. An array remains supported for the original integration, but it
must use the exact order above.

## Output meaning

The eight raw output indices map to:

```text
0 tool_making
1 fire_making
2 water_security
3 food_security
4 shelter_construction
5 first_aid
6 rest_and_warmth
7 evacuate
```

These are scores, not probabilities. The ESP32 applies no softmax and does not
perform the 48-to-8 projection. The host owns that projection; V2 owns only the
replaceable 9-to-8 head.
