# vLLM Issue Tracker

Generated at: 2026-05-01T08:22:38+00:00

## Action Queue

| topic | issue | title | labels | updated_at | my_status | learning_value | fixability | next_action | url |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| compilation_runtime | [#39479](https://github.com/vllm-project/vllm/issues/39479) | [torch.compile] config hashing refactor follow-ups | help wanted, good first issue, feature request | 2026-05-01T04:49:13Z | fixable | high | high | Read compilation config hash TODOs; pick one small refactor | https://github.com/vllm-project/vllm/issues/39479 |
| model_family_gemma4 | [#41452](https://github.com/vllm-project/vllm/issues/41452) | [Bug]: Gemma4-31B-it deployed on vLLM cannot process images in tool message | bug | 2026-05-01T07:55:19Z | triage | high | medium | Reproduce tool-message image path and trace prompt replacement failure | https://github.com/vllm-project/vllm/issues/41452 |
| model_family_deepseek_v4 | [#40955](https://github.com/vllm-project/vllm/issues/40955) | [Bug]: DeepSeek V4 pro can not run with TP16 | bug, DSv4 | 2026-05-01T06:04:12Z | triage | high | medium | Inspect DeepSeek V4 FP8 tensor-parallel shape constraints | https://github.com/vllm-project/vllm/issues/40955 |
| model_family_deepseek_v4 | [#41027](https://github.com/vllm-project/vllm/issues/41027) | [Bug]: can't run deepseek v4 flash | bug, DSv4 | 2026-04-30T22:02:12Z | triage | high | medium | Reproduce unsupported architecture path and backend fallback | https://github.com/vllm-project/vllm/issues/41027 |
| pooling_embeddings | [#41390](https://github.com/vllm-project/vllm/issues/41390) | [Performance]: Llama-Nemotron embedding is slower than Transformers for offline batch-32 pooling after compile-cache warmup |  | 2026-04-30T16:42:43Z | triage | high | medium | Run MRE and profile pooling runner vs HF baseline | https://github.com/vllm-project/vllm/issues/41390 |
| model_family_deepseek_v4 | [#41331](https://github.com/vllm-project/vllm/issues/41331) | [Bug]: Garbled Output in DeepSeek-V4 with CUDA Graph Enabled Under Concurrent Identical Input Requests | bug | 2026-04-30T03:53:06Z | triage | high | medium | Compare cudagraph modes and sparse MLA metadata replay | https://github.com/vllm-project/vllm/issues/41331 |
| model_family_gpt_oss | [#27653](https://github.com/vllm-project/vllm/issues/27653) | [RFC]: include past-reasoning for harmony(gpt-oss) formatting in chat completions API | RFC, stale | 2026-04-30T02:20:03Z | triage | high | medium | Map harmony_utils handling of past reasoning across turns | https://github.com/vllm-project/vllm/issues/27653 |
| model_family_gpt_oss | [#28262](https://github.com/vllm-project/vllm/issues/28262) | [Bug]: [gpt-oss] Responses API incorrect input/output handling | bug, stale | 2026-04-22T02:17:13Z | triage | high | medium | Add tests around Responses API Harmony channel metadata | https://github.com/vllm-project/vllm/issues/28262 |
| model_family_gemma4 | [#39392](https://github.com/vllm-project/vllm/issues/39392) | [Bug]: Gemma4 tool-call-parser produces <pad> tokens under concurrent requests | bug | 2026-04-13T22:36:49Z | triage | high | medium | Read Gemma4ToolParser state handling and reproduce concurrent tool calls | https://github.com/vllm-project/vllm/issues/39392 |
| model_family_gemma4 | [#39681](https://github.com/vllm-project/vllm/issues/39681) | [Bug]: Gemma4 multimodal crashes with "pixel_values contains inconsistent shapes" when concurrent image requests have different resolutions | bug | 2026-04-13T07:59:35Z | triage | high | medium | Read gemma4_mm TensorSchema path; reproduce with concurrent image sizes | https://github.com/vllm-project/vllm/issues/39681 |
| sampling_logits_output | [#29280](https://github.com/vllm-project/vllm/issues/29280) | [Feature]: Selective Token Logprobs Tracking | feature request | 2026-02-13T07:59:32Z | triage | high | medium | Map sampler/logprobs output path and check current API shape | https://github.com/vllm-project/vllm/issues/29280 |
| observability_metrics | [#41368](https://github.com/vllm-project/vllm/issues/41368) | [Bug]: vllm-0.20.0 metrics not accurate | bug | 2026-04-30T19:28:54Z | triage | medium | medium | Compare /metrics output with log stats for Qwen3.5 bench | https://github.com/vllm-project/vllm/issues/41368 |
| model_loading_hf | [#32911](https://github.com/vllm-project/vllm/issues/32911) | [Bug]: "ValueError: No tokenizer file found in directory" when serving Qwen3-Omni | bug, stale | 2026-04-28T02:17:00Z | triage | medium | medium | Check Qwen3-Omni tokenizer mode/model loading path and vLLM-Omni delta | https://github.com/vllm-project/vllm/issues/32911 |
| model_family_gpt_oss | [#40838](https://github.com/vllm-project/vllm/issues/40838) | [Bug]: Performance regression from v0.16.0 to v0.17.0+ on openai/gpt-oss-120b | bug | 2026-04-27T23:26:37Z | triage | medium | medium | Review v0.16 to v0.17 serving/runtime changes before attempting a perf bisect | https://github.com/vllm-project/vllm/issues/40838 |
| tokenization_chat_templates | [#29849](https://github.com/vllm-project/vllm/issues/29849) | [Bug]: DeepSeek-V3.2 As of transformers v4.44, default chat template is no longer allowed, so you must provide a chat template if the tokenizer does not define one | bug, stale | 2026-04-18T02:16:55Z | triage | medium | medium | Check DeepSeek V3.2 tokenizer template handling and duplicates | https://github.com/vllm-project/vllm/issues/29849 |

## Topics

### model_family_gemma4

Gemma 4 / Gemma4 model-family issues, especially multimodal, tool calling, quantization, MoE, and HF integration.

| issue | title | labels | updated_at | my_status | learning_value | fixability | next_action | url |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [#41452](https://github.com/vllm-project/vllm/issues/41452) | [Bug]: Gemma4-31B-it deployed on vLLM cannot process images in tool message | bug | 2026-05-01T07:55:19Z | triage | high | medium | Reproduce tool-message image path and trace prompt replacement failure | https://github.com/vllm-project/vllm/issues/41452 |
| [#39392](https://github.com/vllm-project/vllm/issues/39392) | [Bug]: Gemma4 tool-call-parser produces <pad> tokens under concurrent requests | bug | 2026-04-13T22:36:49Z | triage | high | medium | Read Gemma4ToolParser state handling and reproduce concurrent tool calls | https://github.com/vllm-project/vllm/issues/39392 |
| [#39681](https://github.com/vllm-project/vllm/issues/39681) | [Bug]: Gemma4 multimodal crashes with "pixel_values contains inconsistent shapes" when concurrent image requests have different resolutions | bug | 2026-04-13T07:59:35Z | triage | high | medium | Read gemma4_mm TensorSchema path; reproduce with concurrent image sizes | https://github.com/vllm-project/vllm/issues/39681 |

### model_family_deepseek_v4

DeepSeek V4 model-family issues, including DeepSeek-V4 Flash/Pro, MoE routing, distributed serving, kernels, and tokenizer/template behavior.

| issue | title | labels | updated_at | my_status | learning_value | fixability | next_action | url |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [#40955](https://github.com/vllm-project/vllm/issues/40955) | [Bug]: DeepSeek V4 pro can not run with TP16 | bug, DSv4 | 2026-05-01T06:04:12Z | triage | high | medium | Inspect DeepSeek V4 FP8 tensor-parallel shape constraints | https://github.com/vllm-project/vllm/issues/40955 |
| [#41027](https://github.com/vllm-project/vllm/issues/41027) | [Bug]: can't run deepseek v4 flash | bug, DSv4 | 2026-04-30T22:02:12Z | triage | high | medium | Reproduce unsupported architecture path and backend fallback | https://github.com/vllm-project/vllm/issues/41027 |
| [#41331](https://github.com/vllm-project/vllm/issues/41331) | [Bug]: Garbled Output in DeepSeek-V4 with CUDA Graph Enabled Under Concurrent Identical Input Requests | bug | 2026-04-30T03:53:06Z | triage | high | medium | Compare cudagraph modes and sparse MLA metadata replay | https://github.com/vllm-project/vllm/issues/41331 |

### model_family_gpt_oss

gpt-oss model-family issues, including Harmony formatting, Responses API behavior, streaming/tools, MXFP4 MoE, ROCm, and performance.

| issue | title | labels | updated_at | my_status | learning_value | fixability | next_action | url |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [#27653](https://github.com/vllm-project/vllm/issues/27653) | [RFC]: include past-reasoning for harmony(gpt-oss) formatting in chat completions API | RFC, stale | 2026-04-30T02:20:03Z | triage | high | medium | Map harmony_utils handling of past reasoning across turns | https://github.com/vllm-project/vllm/issues/27653 |
| [#40838](https://github.com/vllm-project/vllm/issues/40838) | [Bug]: Performance regression from v0.16.0 to v0.17.0+ on openai/gpt-oss-120b | bug | 2026-04-27T23:26:37Z | triage | medium | medium | Review v0.16 to v0.17 serving/runtime changes before attempting a perf bisect | https://github.com/vllm-project/vllm/issues/40838 |
| [#28262](https://github.com/vllm-project/vllm/issues/28262) | [Bug]: [gpt-oss] Responses API incorrect input/output handling | bug, stale | 2026-04-22T02:17:13Z | triage | high | medium | Add tests around Responses API Harmony channel metadata | https://github.com/vllm-project/vllm/issues/28262 |

### kv_cache

KV cache allocation, block management, eviction, offload, prefix reuse, KV dtype/layout.

_No active issues._

### scheduler_batching

V1 scheduler, continuous batching, preemption, chunked prefill, partial prefill, fairness.

_No active issues._

### attention_kernels

PagedAttention, FlashAttention, FlashInfer, MLA, CUDA graphs, CPU attention kernels.

_No active issues._

### speculative_decoding

Speculative decoding, draft models, EAGLE, MTP, ngram, tree attention.

_No active issues._

### quantization

FP8, AWQ, GPTQ, Marlin, TurboQuant, KV cache quantization.

_No active issues._

### moe

Mixture of Experts, routing, expert parallelism, DeepEP, EPLB, MoE kernels.

_No active issues._

### lora_adapters

LoRA loading, dynamic adapters, multimodal LoRA, adapter serving.

_No active issues._

### structured_output_tooling

Structured outputs, guided decoding, xgrammar, tool calling, reasoning parsers.

_No active issues._

### openai_server

OpenAI-compatible API server, streaming, chat completions, tools, metrics.

_No active issues._

### distributed_pd

Distributed execution, tensor/data/pipeline parallelism, disaggregated prefill, KV transfer.

_No active issues._

### multimodal_input_processing

Multimodal inputs, prompt embeddings, HF processors, image/video/audio preprocessing, encoder budgeting.

_No active issues._

### sampling_logits_output

Sampling, logits processors, logprobs, output processing, parallel sampling, max token accounting.

| issue | title | labels | updated_at | my_status | learning_value | fixability | next_action | url |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [#29280](https://github.com/vllm-project/vllm/issues/29280) | [Feature]: Selective Token Logprobs Tracking | feature request | 2026-02-13T07:59:32Z | triage | high | medium | Map sampler/logprobs output path and check current API shape | https://github.com/vllm-project/vllm/issues/29280 |

### pooling_embeddings

Embedding, pooling, reranking, scoring, classification, reward and token embedding models.

| issue | title | labels | updated_at | my_status | learning_value | fixability | next_action | url |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [#41390](https://github.com/vllm-project/vllm/issues/41390) | [Performance]: Llama-Nemotron embedding is slower than Transformers for offline batch-32 pooling after compile-cache warmup |  | 2026-04-30T16:42:43Z | triage | high | medium | Run MRE and profile pooling runner vs HF baseline | https://github.com/vllm-project/vllm/issues/41390 |

### compilation_runtime

torch.compile, CUDA graphs, compile cache, custom ops, Triton/TileLang JIT, fusion passes.

| issue | title | labels | updated_at | my_status | learning_value | fixability | next_action | url |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [#39479](https://github.com/vllm-project/vllm/issues/39479) | [torch.compile] config hashing refactor follow-ups | help wanted, good first issue, feature request | 2026-05-01T04:49:13Z | fixable | high | high | Read compilation config hash TODOs; pick one small refactor | https://github.com/vllm-project/vllm/issues/39479 |

### observability_metrics

Metrics, Prometheus, OpenTelemetry, traces, request timing, logging and production observability.

| issue | title | labels | updated_at | my_status | learning_value | fixability | next_action | url |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [#41368](https://github.com/vllm-project/vllm/issues/41368) | [Bug]: vllm-0.20.0 metrics not accurate | bug | 2026-04-30T19:28:54Z | triage | medium | medium | Compare /metrics output with log stats for Qwen3.5 bench | https://github.com/vllm-project/vllm/issues/41368 |

### tokenization_chat_templates

Tokenizers, tokenizer modes, chat templates, prompt formatting, HF processor/tokenizer compatibility.

| issue | title | labels | updated_at | my_status | learning_value | fixability | next_action | url |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [#29849](https://github.com/vllm-project/vllm/issues/29849) | [Bug]: DeepSeek-V3.2 As of transformers v4.44, default chat template is no longer allowed, so you must provide a chat template if the tokenizer does not define one | bug, stale | 2026-04-18T02:16:55Z | triage | medium | medium | Check DeepSeek V3.2 tokenizer template handling and duplicates | https://github.com/vllm-project/vllm/issues/29849 |

### model_loading_hf

Model loading, Hugging Face config integration, weight formats, model registry and architecture support.

| issue | title | labels | updated_at | my_status | learning_value | fixability | next_action | url |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [#32911](https://github.com/vllm-project/vllm/issues/32911) | [Bug]: "ValueError: No tokenizer file found in directory" when serving Qwen3-Omni | bug, stale | 2026-04-28T02:17:00Z | triage | medium | medium | Check Qwen3-Omni tokenizer mode/model loading path and vLLM-Omni delta | https://github.com/vllm-project/vllm/issues/32911 |
