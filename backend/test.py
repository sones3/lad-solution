#!/usr/bin/env python3
"""
POC: patch a PDF by reusing an already-observed glyph byte from the same PDF,
without needing the original font file.

This version is intentionally conservative:
- it only patches text-showing operators (Tj/TJ)
- it only handles operands that pypdf decoded to TextStringObject
- it only patches strings whose decoded text and raw bytes have the same length
  (simple 1-byte encodings such as WinAnsi / MacRoman / PDFDocEncoding)

That makes it a good fit for PDFs like the provided sample, where the target text
is in literal Tj strings and the font is Times-Roman / WinAnsi.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, ByteStringObject, ContentStream, TextStringObject


@dataclass
class FontState:
    page_index: int
    font_name: str
    font_obj_id: Optional[int]

    @property
    def key(self) -> Tuple[int, str, Optional[int]]:
        return (self.page_index, self.font_name, self.font_obj_id)


def resolve_font_state(page, page_index: int, font_name_obj) -> FontState:
    font_name = str(font_name_obj)
    font_ref = page["/Resources"]["/Font"][font_name_obj]
    font_obj_id = getattr(font_ref, "idnum", None)
    return FontState(page_index=page_index, font_name=font_name, font_obj_id=font_obj_id)


def get_decoded_and_raw(text_obj) -> Tuple[Optional[str], Optional[bytes]]:
    """Return (decoded_text, raw_bytes) for text operands we can safely patch."""
    if isinstance(text_obj, TextStringObject):
        raw = getattr(text_obj, "original_bytes", None)
        if raw is None:
            return None, None
        return str(text_obj), raw
    return None, None


def learn_observed_glyph_bytes(writer: PdfWriter) -> Dict[Tuple[int, str, Optional[int]], Dict[str, bytes]]:
    observed: Dict[Tuple[int, str, Optional[int]], Dict[str, bytes]] = {}

    for page_index, page in enumerate(writer.pages):
        cs = ContentStream(page.get_contents(), writer)
        current_font: Optional[FontState] = None

        for operands, operator in cs.operations:
            if operator == b"Tf":
                current_font = resolve_font_state(page, page_index, operands[0])
                observed.setdefault(current_font.key, {})
                continue

            if current_font is None:
                continue

            text_operands = []
            if operator == b"Tj":
                text_operands = [operands[0]]
            elif operator == b"TJ":
                text_operands = [item for item in operands[0] if isinstance(item, (TextStringObject, ByteStringObject))]

            for text_obj in text_operands:
                decoded, raw = get_decoded_and_raw(text_obj)
                if decoded is None or raw is None:
                    continue
                if len(decoded) != len(raw):
                    # Skip multibyte or otherwise ambiguous encodings in this POC.
                    continue
                cmap = observed[current_font.key]
                for ch, byte in zip(decoded, raw):
                    cmap.setdefault(ch, bytes([byte]))

    return observed


def patch_text_operand(
    text_obj,
    target_text: str,
    old_char: str,
    new_char: str,
    replacement_bytes: bytes,
) -> Tuple[object, int]:
    """
    Patch all occurrences of target_text inside a single text operand, but only swap
    the first character of each target_text occurrence from old_char -> new_char.
    Returns (possibly_new_operand, number_of_swaps).
    """
    decoded, raw = get_decoded_and_raw(text_obj)
    if decoded is None or raw is None:
        return text_obj, 0

    if len(decoded) != len(raw):
        return text_obj, 0

    hit_count = 0
    raw_buf = bytearray(raw)
    start = 0
    while True:
        idx = decoded.find(target_text, start)
        if idx < 0:
            break
        if decoded[idx] != old_char:
            start = idx + len(target_text)
            continue
        # 1-byte encoding assumption: character index == byte index.
        raw_buf[idx : idx + 1] = replacement_bytes
        hit_count += 1
        start = idx + len(target_text)

    if hit_count == 0:
        return text_obj, 0

    # Keep raw bytes explicit in the content stream. This is the important part:
    # we are not re-laying out text; we are swapping the underlying shown byte.
    return ByteStringObject(bytes(raw_buf)), hit_count


def patch_pdf(
    input_pdf: str,
    output_pdf: str,
    target_text: str,
    old_char: str,
    new_char: str,
) -> dict:
    reader = PdfReader(input_pdf)
    writer = PdfWriter(clone_from=reader)

    observed = learn_observed_glyph_bytes(writer)

    total_swaps = 0
    fonts_used = set()

    for page_index, page in enumerate(writer.pages):
        cs = ContentStream(page.get_contents(), writer)
        current_font: Optional[FontState] = None
        page_changed = False

        for operands, operator in cs.operations:
            if operator == b"Tf":
                current_font = resolve_font_state(page, page_index, operands[0])
                continue

            if current_font is None:
                continue

            font_map = observed.get(current_font.key, {})
            replacement_bytes = font_map.get(new_char)
            if replacement_bytes is None:
                continue

            if operator == b"Tj":
                new_operand, count = patch_text_operand(
                    operands[0], target_text, old_char, new_char, replacement_bytes
                )
                if count:
                    operands[0] = new_operand
                    total_swaps += count
                    fonts_used.add(current_font.key)
                    page_changed = True

            elif operator == b"TJ":
                arr = operands[0]
                for i, item in enumerate(arr):
                    if not isinstance(item, (TextStringObject, ByteStringObject)):
                        continue
                    new_item, count = patch_text_operand(
                        item, target_text, old_char, new_char, replacement_bytes
                    )
                    if count:
                        arr[i] = new_item
                        total_swaps += count
                        fonts_used.add(current_font.key)
                        page_changed = True

        if page_changed:
            page.replace_contents(cs)

    if total_swaps == 0:
        raise RuntimeError(
            f"No swap performed. Either target_text was not found, or no observed '{new_char}' byte existed in the same font."
        )

    with open(output_pdf, "wb") as fh:
        writer.write(fh)

    return {
        "total_swaps": total_swaps,
        "fonts_used": sorted(list(fonts_used)),
        "target_text": target_text,
        "old_char": old_char,
        "new_char": new_char,
        "output_pdf": output_pdf,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Reuse an observed glyph byte from the same PDF to patch text.")
    ap.add_argument("input_pdf")
    ap.add_argument("output_pdf")
    ap.add_argument("--target-text", required=True, help="Exact text span to search inside text-showing operands")
    ap.add_argument("--old-char", required=True, help="Character expected at the start of each matched span")
    ap.add_argument("--new-char", required=True, help="Replacement character to reuse from the same font in the same PDF")
    args = ap.parse_args()

    if len(args.old_char) != 1 or len(args.new_char) != 1:
        raise SystemExit("--old-char and --new-char must be exactly one character each")

    result = patch_pdf(
        input_pdf=args.input_pdf,
        output_pdf=args.output_pdf,
        target_text=args.target_text,
        old_char=args.old_char,
        new_char=args.new_char,
    )

    print("[OK] glyph-swap complete")
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()