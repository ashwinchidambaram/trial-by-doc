"""granite-docling-258M adapter (transformers, Idefics3). Emits DocTags -> markdown via docling-core.

Verified recipe 2026-06-11: AutoModelForImageTextToText, "Convert this page to docling.",
decode with skip_special_tokens=False (DocTags ARE special tokens), then docling-core conversion.
"""
from __future__ import annotations

import html
import logging
import re

from tbdoc.core.registry import register_model
from tbdoc.models.local._transformers_base import TransformersModelAdapter


@register_model("granite_docling")
class GraniteDoclingAdapter(TransformersModelAdapter):
    max_new_tokens = 8192

    def build_inputs(self, image):
        messages = [{"role": "user", "content": [
            {"type": "image"},
            {"type": "text", "text": "Convert this page to docling."},
        ]}]
        prompt = self.processor.apply_chat_template(messages, add_generation_prompt=True)
        return self.processor(text=prompt, images=[image], return_tensors="pt").to("cuda")

    # Markdown that still carries DocTag location artifacts (raw <loc_..> OR docling's escaped &gt;loc /
    # loc12&gt; form) — granite-258M emits malformed tags that either crash docling or survive its export.
    _DOCTAG_ARTIFACT = re.compile(r"<loc_|<otsl>|<doctag|<nl>|</?fcel|&gt;\s*loc|&lt;\s*loc|loc\d+\s*&gt;")

    def decode(self, gen_ids, image) -> dict:
        # DocTags are special tokens -> must NOT skip them
        doctags = self.processor.decode(gen_ids, skip_special_tokens=False).lstrip()
        markdown = None
        tables_html = None
        try:
            from docling_core.types.doc import DoclingDocument
            from docling_core.types.doc.document import DocTagsDocument
            dt = DocTagsDocument.from_doctags_and_image_pairs([doctags], [image])
            doc = DoclingDocument.load_from_doctags(dt, document_name="Document")
            markdown = doc.export_to_markdown()
            try:
                tables_html = [doc.export_to_html()] if doc.tables else None
            except Exception:
                tables_html = None
        except Exception as e:
            logging.getLogger("tbdoc.granite").warning(
                "doctags->markdown conversion threw (%s: %s); recovering plain text", type(e).__name__, e)
        # S11 #6: never emit DocTag noise to the text scorer/extractor (it corrupted ~46% of granite's
        # outputs). Recover plain text when conversion threw OR "succeeded" but left location artifacts —
        # strip tags + unescape entities. Clean docling markdown (no artifacts) is kept as-is.
        if markdown is None or self._DOCTAG_ARTIFACT.search(markdown):
            if markdown is not None:
                logging.getLogger("tbdoc.granite").warning("docling markdown carried DocTag artifacts; recovering plain text")
            markdown = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", doctags)).split())
        return {"markdown": markdown, "tables_html": tables_html, "raw": {"doctags": doctags[:3000]}}
