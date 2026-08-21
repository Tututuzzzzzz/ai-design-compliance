"""Localisation for backend-generated report prose.

The UI chrome is translated in the frontend, but the body of a report — the
verdict reasoning, the policy notes, the findings the register raises — is
written here in Python, and the vision model writes the rest. A Vietnamese user
was therefore reading a Vietnamese shell wrapped around English content.

Every string the pipeline generates goes through this module. The language is
chosen once, when the job is submitted (`DesignMetadata.language`), and stored
with the report, so re-opening an old report shows it in the language it was
analysed in rather than silently mixing the two.
"""

from __future__ import annotations

from typing import Literal

Lang = Literal["en", "vi"]

DEFAULT_LANG: Lang = "en"
SUPPORTED: tuple[Lang, ...] = ("en", "vi")


def normalize(lang: str | None) -> Lang:
    value = (lang or "").strip().lower()[:2]
    return value if value in SUPPORTED else DEFAULT_LANG  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Vision prompt
# --------------------------------------------------------------------------

#: Appended to the system prompt. The model keeps reasoning in English (the
#: prompt and the category vocabulary are English) but writes every field a
#: human reads in the target language. Proper nouns stay untranslated: a rights
#: holder is a legal entity and "Metro-Goldwyn-Mayer" must not become a gloss.
OUTPUT_LANGUAGE_INSTRUCTION: dict[Lang, str] = {
    "en": "",
    "vi": (
        "\nOUTPUT LANGUAGE\n"
        "Write every human-readable field in Vietnamese: description, notes, and "
        "each finding's title, description, location_hint and remediation, plus "
        "niche.primary, niche.sub_niche, niche.audience, niche.style and "
        "niche.motifs.\n"
        "Do NOT translate: the category and severity enum values (they are fixed "
        "identifiers), text transcribed in ocr_lines and matched_text (transcribe "
        "verbatim as printed on the artwork), rights_holder, and brand, character, "
        "franchise or product names — keep those in their original form. You may "
        "add a short Vietnamese gloss in parentheses after a proper noun when it "
        "helps the reader.\n"
        "Use natural Vietnamese with correct diacritics, not a word-for-word "
        "translation."
    ),
}


# --------------------------------------------------------------------------
# Vocabulary shared by several generated sentences
# --------------------------------------------------------------------------

SEVERITY: dict[Lang, dict[str, str]] = {
    "en": {"low": "LOW", "medium": "MEDIUM", "high": "HIGH", "critical": "CRITICAL"},
    "vi": {
        "low": "THẤP",
        "medium": "TRUNG BÌNH",
        "high": "CAO",
        "critical": "NGHIÊM TRỌNG",
    },
}

#: Lower-case form, used mid-sentence ("severity raised medium → high").
SEVERITY_INLINE: dict[Lang, dict[str, str]] = {
    "en": {"low": "low", "medium": "medium", "high": "high", "critical": "critical"},
    "vi": {
        "low": "thấp",
        "medium": "trung bình",
        "high": "cao",
        "critical": "nghiêm trọng",
    },
}

CATEGORY: dict[Lang, dict[str, str]] = {
    "en": {
        "copyrighted_character": "copyrighted character",
        "brand_logo": "brand logo",
        "trademarked_phrase": "trademarked phrase",
        "public_figure": "public figure",
        "copyrighted_artwork": "copyrighted artwork",
        "licensed_font": "licensed font",
        "prohibited_content": "prohibited content",
    },
    "vi": {
        "copyrighted_character": "nhân vật có bản quyền",
        "brand_logo": "logo thương hiệu",
        "trademarked_phrase": "cụm từ đã đăng ký nhãn hiệu",
        "public_figure": "nhân vật công chúng",
        "copyrighted_artwork": "tác phẩm có bản quyền",
        "licensed_font": "phông chữ cần giấy phép",
        "prohibited_content": "nội dung bị cấm",
    },
}

VERDICT: dict[Lang, dict[str, str]] = {
    "en": {"SAFE": "SAFE", "RISKY": "RISKY", "BLOCKED": "BLOCKED"},
    "vi": {"SAFE": "AN TOÀN", "RISKY": "RỦI RO", "BLOCKED": "BỊ CHẶN"},
}


def severity(value: str, lang: Lang) -> str:
    return SEVERITY[lang].get(value, value.upper())


def severity_inline(value: str, lang: Lang) -> str:
    return SEVERITY_INLINE[lang].get(value, value)


def category(value: str, lang: Lang) -> str:
    return CATEGORY[lang].get(value, value.replace("_", " "))


def verdict(value: str, lang: Lang) -> str:
    return VERDICT[lang].get(value, value)


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------

#: Every entry takes the same keyword arguments in both languages, so a caller
#: never has to branch on language itself.
_T: dict[str, dict[Lang, str]] = {
    # --- verdict.decide -------------------------------------------------
    "reason.clean": {
        "en": (
            "No copyrighted characters, brand marks, registered phrases, "
            "recognisable public figures, protected artwork, or prohibited content were "
            "detected. The design reads as original work on a generic subject, so there "
            "is nothing to block a listing."
        ),
        "vi": (
            "Không phát hiện nhân vật có bản quyền, nhãn hiệu thương hiệu, cụm từ đã "
            "đăng ký, nhân vật công chúng dễ nhận ra, tác phẩm được bảo hộ hay nội dung "
            "bị cấm. Thiết kế được đánh giá là tác phẩm gốc trên một chủ đề phổ thông, "
            "không có yếu tố nào cản trở việc đăng bán."
        ),
    },
    "headline.blocked.critical": {
        "en": "a clearly protected element was reproduced: {title}",
        "vi": "một yếu tố được bảo hộ rõ ràng đã bị sao chép: {title}",
    },
    "headline.blocked.multiple": {
        "en": "multiple independent high-severity issues were found, led by: {title}",
        "vi": "phát hiện nhiều vấn đề mức độ cao độc lập, nổi bật nhất là: {title}",
    },
    "headline.blocked.single": {
        "en": "a high-severity issue was found: {title}",
        "vi": "phát hiện một vấn đề mức độ cao: {title}",
    },
    "headline.risky.low_confidence": {
        "en": (
            "a serious issue was detected but with low detection confidence "
            "({confidence}): {title}. A human should confirm before listing"
        ),
        "vi": (
            "phát hiện một vấn đề nghiêm trọng nhưng độ tin cậy nhận diện thấp "
            "({confidence}): {title}. Cần người kiểm tra lại trước khi đăng bán"
        ),
    },
    "headline.risky.reviewable": {
        "en": "a reviewable issue was found: {title}",
        "vi": "phát hiện một vấn đề cần xem xét: {title}",
    },
    "headline.safe.low_only": {
        "en": "only low-severity observations were recorded, none of which prevent listing",
        "vi": (
            "chỉ ghi nhận các quan sát ở mức độ thấp, không có điểm nào cản trở việc "
            "đăng bán"
        ),
    },
    # --- verdict._explain -----------------------------------------------
    "explain.header": {
        "en": "Verdict {verdict} because {headline}.",
        "vi": "Kết luận {verdict} vì {headline}.",
    },
    "explain.count": {
        "en": "{count} issue(s) recorded:",
        "vi": "Đã ghi nhận {count} vấn đề:",
    },
    "explain.item": {
        "en": (
            "  • [{severity}] {category}: {title} ({where}, detection confidence "
            "{confidence}).{holder}{cite} Fix: {remediation}"
        ),
        "vi": (
            "  • [{severity}] {category}: {title} ({where}, độ tin cậy nhận diện "
            "{confidence}).{holder}{cite} Khắc phục: {remediation}"
        ),
    },
    "explain.holder": {
        "en": " Rights holder: {holder}.",
        "vi": " Chủ sở hữu quyền: {holder}.",
    },
    "explain.cite": {
        "en": " Evidence: {cites}.",
        "vi": " Bằng chứng: {cites}.",
    },
    "explain.box_at": {
        "en": "box at ({x}, {y})",
        "vi": "khung tại ({x}, {y})",
    },
    "explain.no_location": {
        "en": "location not localised",
        "vi": "chưa xác định được vị trí",
    },
    # --- verdict.summarize ----------------------------------------------
    "summary.clean": {
        "en": "No IP or policy risk detected — clear to upload.",
        "vi": "Không phát hiện rủi ro sở hữu trí tuệ hay chính sách — có thể đăng bán.",
    },
    "summary.issues": {
        "en": "{verdict}: {count} issue(s) across {categories}. Most serious — {title}.",
        "vi": "{verdict}: {count} vấn đề thuộc {categories}. Nghiêm trọng nhất — {title}.",
    },
    # --- verdict.merge_trademark_hits -----------------------------------
    "tm.title": {
        "en": 'Text "{query}" matches registered mark "{mark}"',
        "vi": 'Văn bản "{query}" trùng khớp nhãn hiệu đã đăng ký "{mark}"',
    },
    "tm.description": {
        "en": (
            'The design carries the text "{query}", which matches the registered mark '
            '"{mark}" at {similarity}% similarity{owner}{status}. Registered wordmarks '
            "apply to the goods in their class, so printing the phrase on apparel can "
            "infringe even without a logo."
        ),
        "vi": (
            'Thiết kế chứa văn bản "{query}", trùng khớp với nhãn hiệu đã đăng ký '
            '"{mark}" ở mức tương đồng {similarity}%{owner}{status}. Nhãn hiệu chữ đã '
            "đăng ký có hiệu lực với nhóm hàng hóa của nó, nên việc in cụm từ này lên "
            "quần áo vẫn có thể vi phạm dù không kèm logo."
        ),
    },
    "tm.owner_suffix": {
        "en": " (owner: {owner})",
        "vi": " (chủ sở hữu: {owner})",
    },
    "tm.status_suffix": {
        "en": ", status {status}",
        "vi": ", trạng thái {status}",
    },
    "tm.location_hint": {
        "en": "see OCR text region",
        "vi": "xem vùng văn bản OCR",
    },
    "tm.remediation": {
        "en": (
            'Remove or reword "{query}". Rephrasing to a descriptive, non-identical '
            "wording that does not function as a brand is usually enough; verify against "
            "the register before listing."
        ),
        "vi": (
            'Bỏ hoặc viết lại "{query}". Thông thường chỉ cần đổi sang cách diễn đạt mô '
            "tả, không trùng khớp và không mang chức năng thương hiệu; hãy đối chiếu lại "
            "với cơ sở dữ liệu nhãn hiệu trước khi đăng bán."
        ),
    },
    # --- verdict._hit_evidence ------------------------------------------
    "hit.match": {
        "en": 'register match "{mark}" @ {similarity}%',
        "vi": 'khớp đăng bạ "{mark}" @ {similarity}%',
    },
    "hit.status": {"en": "status {status}", "vi": "trạng thái {status}"},
    "hit.owner": {"en": "owner {owner}", "vi": "chủ sở hữu {owner}"},
    "hit.classes": {"en": "class {classes}", "vi": "nhóm {classes}"},
    # --- verdict.cap_unverified_phrases ---------------------------------
    "cap.note": {
        "en": (
            " — NOTE: no trademark register confirmed this phrase and no rights holder "
            "could be named, so it is reported as needing review rather than as a "
            "confirmed registration. Common descriptive shirt text is frequently not "
            "registered at all."
        ),
        "vi": (
            " — LƯU Ý: không có cơ sở dữ liệu nhãn hiệu nào xác nhận cụm từ này và cũng "
            "không xác định được chủ sở hữu quyền, nên đây được báo cáo là cần xem xét "
            "chứ không phải một đăng ký đã được xác nhận. Văn bản áo mang tính mô tả "
            "thông thường phần lớn không hề được đăng ký."
        ),
    },
    "cap.evidence": {
        "en": (
            "No register match and no named rights holder — severity capped at medium "
            "so an unattributed phrase cannot block a listing on its own."
        ),
        "vi": (
            "Không khớp đăng bạ và không nêu được chủ sở hữu quyền — mức độ được giới "
            "hạn ở trung bình để một cụm từ không rõ chủ sở hữu không thể tự nó chặn "
            "một listing."
        ),
    },
    # --- run.analyze_design ---------------------------------------------
    "evidence.vision": {
        "en": "Identified by {provider} from the artwork itself.",
        "vi": "Được {provider} nhận diện trực tiếp từ chính hình thiết kế.",
    },
    "note.no_local_index": {
        "en": (
            "Local USPTO index not built — text was checked against the live USPTO "
            "search only. Run `python -m data.build_uspto_index` for offline coverage."
        ),
        "vi": (
            "Chưa xây dựng chỉ mục USPTO cục bộ — văn bản chỉ được đối chiếu với tra "
            "cứu USPTO trực tuyến. Chạy `python -m data.build_uspto_index` để có phạm "
            "vi đối chiếu ngoại tuyến."
        ),
    },
    # --- run.failed_report ----------------------------------------------
    "failed.reasoning": {
        "en": (
            "This design could not be analysed automatically: {error}. It is reported as "
            "RISKY rather than SAFE so it is never listed on the strength of a failed "
            "check — review it manually."
        ),
        "vi": (
            "Không thể phân tích tự động thiết kế này: {error}. Kết quả được báo là RỦI "
            "RO thay vì AN TOÀN để thiết kế không bao giờ được đăng bán dựa trên một "
            "lượt kiểm tra thất bại — hãy xem xét thủ công."
        ),
    },
    "failed.summary": {
        "en": "Analysis failed: {error}",
        "vi": "Phân tích thất bại: {error}",
    },
    "failed.niche": {"en": "unknown", "vi": "không xác định"},
    # --- rules.apply ------------------------------------------------------
    "rule.strict_platform": {
        "en": (
            "{names} treat {category} as a zero-tolerance category — severity raised "
            "{old} → {new}. Policy: {source}"
        ),
        "vi": (
            "{names} xếp {category} vào nhóm không khoan nhượng — mức độ được nâng từ "
            "{old} → {new}. Chính sách: {source}"
        ),
    },
    "rule.banned_goods": {
        "en": "Prohibited-goods policy hit — {summary}. Severity raised {old} → {new}.",
        "vi": (
            "Vi phạm chính sách hàng hóa bị cấm — {summary}. Mức độ được nâng từ {old} "
            "→ {new}."
        ),
    },
    "rule.strict_market": {
        "en": "{names}: {note} Severity raised {old} → {new}.",
        "vi": "{names}: {note} Mức độ được nâng từ {old} → {new}.",
    },
}


def t(key: str, lang: Lang, **kwargs: object) -> str:
    """Look up a template and format it.

    Falls back to English rather than to the raw key: a missing Vietnamese string
    should degrade to readable English, never to `rule.strict_market`.
    """
    entry = _T.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry["en"]).format(**kwargs)


# --------------------------------------------------------------------------
# Spreadsheet / CSV export
# --------------------------------------------------------------------------

EXPORT: dict[Lang, dict[str, str]] = {
    "en": {
        "filename": "Filename",
        "scanned": "Scanned",
        "verdict": "Verdict",
        "confidence": "Confidence %",
        "niche": "Niche",
        "sub_niche": "Sub-niche",
        "style": "Style",
        "motifs": "Motifs",
        "risk_categories": "Risk categories",
        "finding_count": "Findings",
        "top_severity": "Top severity",
        "rights_holders": "Rights holders",
        "trademark_matches": "Trademark matches",
        "regions": "Violation regions",
        "remediation": "Suggested fixes",
        "markets": "Markets",
        "platforms": "Platforms",
        "ocr_text": "OCR text",
        "source": "Input method",
        "source_ref": "Source ref",
        "reasoning": "Reasoning",
        "error": "Error",
        "sheet.summary": "Summary",
        "sheet.designs": "Designs",
        "sheet.findings": "Findings",
        "sheet.review": "Review sheet",
        "noPreview": "(no preview)",
        "metric": "Metric",
        "count": "Count",
        "total": "TOTAL",
        "failed": "FAILED",
        "category": "Category",
        "severity": "Severity",
        "title": "Title",
        "rights_holder": "Rights holder",
        "matched_text": "Matched text",
        "location": "Location",
        "evidence": "Evidence",
    },
    "vi": {
        "filename": "Tên tệp",
        "scanned": "Thời điểm quét",
        "verdict": "Kết luận",
        "confidence": "Độ tin cậy %",
        "niche": "Niche",
        "sub_niche": "Niche phụ",
        "style": "Phong cách",
        "motifs": "Motif",
        "risk_categories": "Nhóm rủi ro",
        "finding_count": "Số phát hiện",
        "top_severity": "Mức độ cao nhất",
        "rights_holders": "Chủ sở hữu quyền",
        "trademark_matches": "Kết quả khớp nhãn hiệu",
        "regions": "Vùng vi phạm",
        "remediation": "Đề xuất khắc phục",
        "markets": "Thị trường",
        "platforms": "Nền tảng",
        "ocr_text": "Văn bản OCR",
        "source": "Phương thức đầu vào",
        "source_ref": "Nguồn tham chiếu",
        "reasoning": "Giải thích",
        "error": "Lỗi",
        "sheet.summary": "Tổng quan",
        "sheet.designs": "Thiết kế",
        "sheet.findings": "Phát hiện",
        "sheet.review": "Bảng rà soát",
        "noPreview": "(không có ảnh)",
        "metric": "Chỉ số",
        "count": "Số lượng",
        "total": "TỔNG",
        "failed": "THẤT BẠI",
        "category": "Nhóm",
        "severity": "Mức độ",
        "title": "Tiêu đề",
        "rights_holder": "Chủ sở hữu quyền",
        "matched_text": "Văn bản khớp",
        "location": "Vị trí",
        "evidence": "Bằng chứng",
    },
}


def export(key: str, lang: Lang) -> str:
    table = EXPORT[lang]
    return table.get(key) or EXPORT[DEFAULT_LANG].get(key, key)
