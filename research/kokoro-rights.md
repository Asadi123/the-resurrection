# Kokoro English narration rights and quality check

Checked primary publisher sources on 2026-10-27. Hugging Face revision: `f3ff3571791e39611d31c381e3a41a3af07b4987`. Full source text and tensor hashes are preserved in [kokoro-license-evidence.json](kokoro-license-evidence.json).

## Rights finding

The official [model card](https://huggingface.co/hexgrad/Kokoro-82M/blob/f3ff3571791e39611d31c381e3a41a3af07b4987/README.md) declares `license: apache-2.0`, calls the weights Apache-licensed, permits production and personal deployment, and explicitly welcomes commercial APIs and real use cases. The official [inference library LICENSE](https://github.com/hexgrad/kokoro/blob/main/LICENSE) contains Apache License 2.0.

All four requested voice tensors are published inside that same Apache-2.0-labelled model repository. The complete repository tree contains **no separate per-voice LICENSE or NOTICE files**. The official [VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/f3ff3571791e39611d31c381e3a41a3af07b4987/VOICES.md) states no different license or attribution condition for any of these four English voices. Its Japanese and French entries explicitly identify applicable CC BY training sources; those exceptions are not attached to these English entries.

| Voice tensor | Official language / sex | Published quality grade | License evidence |
| --- | --- | --- | --- |
| `bm_george.pt` | British English male | C | Repository Apache-2.0; no separate voice terms found |
| `am_michael.pt` | American English male | C+ | Repository Apache-2.0; no separate voice terms found |
| `bm_lewis.pt` | British English male | D+ | Repository Apache-2.0; no separate voice terms found |
| `am_adam.pt` | American English male | F+ | Repository Apache-2.0; no separate voice terms found |

Practical conclusion: local use of these publisher-supplied voices for the film narration is permitted under the published repository license without API fees. No extra license restriction on generated English audio is stated in these sources. This finding is based on the repository-level grant, rather than a distinct individually signed license for each voice. The model card states that training uses permissive/public-domain audio plus synthetic speech and excludes custom voice clones; it does not disclose a complete per-English-voice provenance chain.

If redistributing the library, model, or voice tensors, retain the Apache license and applicable notices and mark modifications as required by Apache section 4. A final narrated film does not redistribute those tensor/code files.

## Recommended auditions and prosody

Start with **Michael** and **George**. Michael has the best published grade among the four; George offers a British male option. The grades estimate training data quality/quantity, not an objective guarantee that either will sound better to this listener. Adam is a poor first choice given the publisher's F+ grade.

The publisher recommends a roughly **100–200-token** utterance range, warns about weakness below **10–20 tokens**, and warns about rushing over **400 tokens**. Bundle very short lines into natural sentences and split long passages at sentence boundaries. The official pipeline supports a `speed` argument, paragraph splitting, and explicit pronunciation markup. For a restrained narrative audition, test normal speed and a modest slower setting (e.g. 0.95; this value is an editorial suggestion, not a publisher preset). Use `lang_code='a'` for Michael/Adam and `'b'` for George/Lewis.

## Optional local expressive alternative

[Resemble AI Chatterbox](https://huggingface.co/ResembleAI/chatterbox) is published with an **MIT** model card and [MIT code license](https://github.com/resemble-ai/chatterbox/blob/master/LICENSE). The original English model offers `exaggeration` and `cfg_weight` controls; publisher tips recommend approximately `exaggeration=0.7, cfg_weight=0.3` for dramatic speech, noting that stronger exaggeration can increase speaking speed. It can generate without a user audio prompt, or use an authorized voice reference. It is substantially larger than Kokoro (500M versus 82M parameters), so local cost is compute/time, not a mandatory paid API. Its published CPU support does not guarantee acceptable generation speed in this workspace. No audio from Chatterbox was generated or evaluated during this check.
