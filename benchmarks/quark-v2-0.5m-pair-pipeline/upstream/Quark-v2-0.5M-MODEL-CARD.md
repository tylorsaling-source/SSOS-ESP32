---
license: apache-2.0
datasets:
- HuggingFaceFW/fineweb-edu
language:
- en
pipeline_tag: text-generation
library_name: transformers
tags:
- llama
- tiny-model
- sub-1M
- small
- tiny
- quark
- 1m
---

# 🔬 Quark-v2-0.5M

**Quark-v2-0.5M** is an ultra-lightweight Llama-based model with only **465,504 parameters** and it is the second version of the quark series.
It was trained from scratch to demonstrate the power of high-quality data (FineWeb-Edu) on extremely small architectures.

## Model Details
- **Architecture:** Llama-based
- **Parameters:** 465,504
- **Vocabulary Size:** 500 (Custom Byte-Level BPE)
- **Hidden Size:** 96
- **Intermediate Size:** 192
- **Layers:** 4
- **Heads:** 4
- **Context Length:** 256 tokens

## Training
- **Dataset:** 1 billion tokens of `HuggingFaceFW/fineweb-edu` (Sample-10BT)
- **Training Time:** ~1.4h on a single Kaggle T4 GPU
- **Final Loss:** 2.44
- **Optimizer:** AdamW with Cosine Learning Rate Decay

![image](https://cdn-uploads.huggingface.co/production/uploads/697f2832c2c5e4daa93cece7/A4AGDkkxew3pvQVv4YaNU.png)

## Intended Use
Quark is a research project to explore the limits of "Micro-LLMs". It is surprisingly capable of forming grammatically correct English sentences and structured lists, despite fitting into less than 2MB of disk space.

## Performance Example
**Prompt:** "Artificial intelligence is "<br>
**Output:** "Artificial intelligence is very possible. In the early 19th century, it has been done in the brain and acids, where they are taking some of the most common reality. This can also have to be lower than any other studies that would not be able to use this factor. If you’ve seen the same part of the world’s little glaucoma, we should need to be able to maintain their important"

**Prompt:** "The future of science is "<br>
**Output:**: "The future of science is very easily. In addition to the claims, including many other people who have been done by the greatest ways that they are listed with their respective and built understanding of these two-thirds of the statements. In this example, it was not asked about how these problems can be confused for the next year. There is no one thing that he should als"

**Prompt:** "Albert Einstein was "<br>
**Output:**: "Albert Einstein was very difficult to prevent them. - Ask the majority of these families, they were sometimes reported that a country had been developing and building unconsciously involved from their own landscape. Their statement is not considered as a good election for the valuable implantation of the programs and the temperature of the powers of the world"

## Benchmarks

![image](https://cdn-uploads.huggingface.co/production/uploads/697f2832c2c5e4daa93cece7/oEwLoCOB-ARiqnsOEeqgm.png)

![image](https://cdn-uploads.huggingface.co/production/uploads/697f2832c2c5e4daa93cece7/RiEGyYYMf_a5HX7b6xQux.png)

**Full research:** [https://lh-tech.de/ai/sub-5m-research.html](https://lh-tech.de/ai/sub-5m-research.html)

## How to use
```python
from transformers import LlamaForCausalLM, PreTrainedTokenizerFast

model = LlamaForCausalLM.from_pretrained("LH-Tech-AI/Quark-v2-0.5M")
tokenizer = PreTrainedTokenizerFast.from_pretrained("LH-Tech-AI/Quark-v2-0.5M")

prompt = "The scientific method is"
inputs = tokenizer(prompt, return_tensors="pt")
outputs = model.generate(**inputs, max_new_tokens=50, do_sample=True, temperature=0.4)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
```