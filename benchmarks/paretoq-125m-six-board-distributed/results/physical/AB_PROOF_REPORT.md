# MobileLLM ParetoQ 125M six-board distributed A/B benchmark

## Aggregate comparison

| Metric | FAST | REGULAR | FAST / REGULAR comparison |
|---|---:|---:|---:|
| Prompts | 5 | 5 | identical |
| Generated tokens | 120 | 120 | identical |
| Exact tokens | 120/120 | 120/120 | identical |
| Mean TTFT (ms) | 56425.810 | 87587.629 | 1.552x |
| Prompt-to-finish total (ms) | 1195151.128 | 1787937.172 | 1.496x |
| Aggregate decode (tok/s) | 0.125955 | 0.085185 | 1.479x |
| SPI errors | 0 | 0 | identical |

Timing note: `spi_ms` in the raw capture is ring-cycle wall time. It overlaps worker computation and must not be interpreted as isolated wire-transfer time.

## Per-prompt timing comparison

| Prompt | FAST TTFT ms | REGULAR TTFT ms | FAST finish ms | REGULAR finish ms | FAST decode tok/s | REGULAR decode tok/s | Exact tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| p01 | 41490.423 | 64299.573 | 223653.470 | 333845.583 | 0.126261 | 0.085329 | 24/24 both |
| p02 | 55060.384 | 85458.350 | 237627.384 | 355429.363 | 0.125981 | 0.085194 | 24/24 both |
| p03 | 48283.432 | 74874.389 | 230638.428 | 344622.408 | 0.126128 | 0.085265 | 24/24 both |
| p04 | 68642.398 | 106647.414 | 251606.416 | 377006.412 | 0.125708 | 0.085072 | 24/24 both |
| p05 | 68652.414 | 106658.419 | 251625.430 | 377033.406 | 0.125702 | 0.085067 | 24/24 both |

## Exact input/output comparison

| ID | Input | Host oracle output | FAST output | REGULAR output |
|---|---|---|---|---|
| p01 | The old workshop was | a place where the old workers would meet to discuss their work.<br>The old workshop was a place where the old | a place where the old workers would meet to discuss their work.<br>The old workshop was a place where the old | a place where the old workers would meet to discuss their work.<br>The old workshop was a place where the old |
| p02 | At sunrise, the river | is still flowing.<br>The river is a tributary of the Ganges, which flows through the city of | is still flowing.<br>The river is a tributary of the Ganges, which flows through the city of | is still flowing.<br>The river is a tributary of the Ganges, which flows through the city of |
| p03 | The engineer opened the cabinet and | the engineers were able to get the engineers to the top of the building.<br>The engineers were able to | the engineers were able to get the engineers to the top of the building.<br>The engineers were able to | the engineers were able to get the engineers to the top of the building.<br>The engineers were able to |
| p04 | Beyond the last house, a narrow road | leads to the village of Kulan, where the village is located.<br>The village is located in the Kul | leads to the village of Kulan, where the village is located.<br>The village is located in the Kul | leads to the village of Kulan, where the village is located.<br>The village is located in the Kul |
| p05 | A careful technician checked the wiring before | installing the cable.<br>The AAC cable.<br>The cable was installed in the correct position.<br>The cable was | installing the cable.<br>The AAC cable.<br>The cable was installed in the correct position.<br>The cable was | installing the cable.<br>The AAC cable.<br>The cable was installed in the correct position.<br>The cable was |

## Artifact identity

| Artifact | SHA-256 |
|---|---|
| Official checkpoint | `4e20ca9dc92366b58293ef010cd7019f241925aa7bf0ad9d50ba909db33de99a` |
| Compute-node app | `115a4ece2764f1b50fb92b45f39622153439504ed09dd09dab75734222cac85b` |
| Physical A/B capture | `dcaad598ae2fefbbc5e696be495b40ea299ab73c740e1173a3a0f3daf9f2410e` |
