"""TEMPLATE — copy this file to add YOUR model to the gauntlet.

Three ways to plug in, by where your model runs:

1. LOCAL open-weights via vLLM  -> subclass VLLMModelAdapter (easiest for HF VLMs)
2. LOCAL via raw transformers   -> subclass TransformersModelAdapter
3. Any HTTP API                 -> subclass APIModelAdapter (or VisionChatAdapter
                                   if it's a chat-vision API you prompt for markdown)

Then add ONE entry to configs/models.yaml pointing at your class (see below) and run:
    gauntlet validate-adapter my_model
    gauntlet run -m my_model -b olmocr_bench --max-samples 5

Full walkthrough: ADD_A_MODEL.md
"""
from __future__ import annotations

from tbdoc.models.local._vllm_base import VLLMModelAdapter

# --- Option 1: local vLLM model ------------------------------------------------
# configs/models.yaml:
#   my_model:
#     kind: local
#     adapter: "tbdoc.models.template.my_model:MyModelAdapter"
#     repo_id: your-org/your-model        # verify on the live HF card
#     revision: <pin a commit hash>       # reproducibility is a deliverable
#     backend: vllm
#     license: <from the model card>
#     commercial_use: true|false


class MyModelAdapter(VLLMModelAdapter):
    # The prompt is part of the measured system — keep it stable across runs.
    prompt = "Convert this document page to clean GitHub-flavored Markdown."
    longest_side = 1540          # resize cap; check your model card's recommendation
    # trust_remote_code = True   # only if the card requires it
    # skip_special_tokens = False  # if your model emits meaningful special tokens

    # Override parse_output() if your model emits structure beyond plain markdown:
    # def parse_output(self, text: str) -> dict:
    #     return {"markdown": ..., "layout_boxes": [{"bbox": [x0,y0,x1,y1],
    #             "type": "table", "text": ...}], "tables_html": [...]}


# --- Option 2: API-backed model -------------------------------------------------
# See src/tbdoc/models/api/anthropic_vision.py (chat-vision) or mistral_ocr.py
# (dedicated OCR endpoint) for complete working examples. You implement:
#   _client() -> SDK client        _call_api(image) -> raw response
#   _parse_response(raw) -> dict   (+ optional _token_usage/_api_version/_request_id)
# The base class handles rate limiting, retries, cost + telemetry stamping, secrets.

# --- Option 3: native document segmentation (Tier C) ----------------------------
# If your model/service can split multi-doc streams itself, override segment():
#   def segment(self, pages, boundary_judge=None) -> Segmentation:
#       return Segmentation(boundaries=[...], method="native")
# and add "segmentation" to `capabilities`. Otherwise the frozen boundary_judge
# composes segmentation from your per-page parses automatically.
