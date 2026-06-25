from app.schemas.assist import ReadView

_VISIBLE_TEXT_BUDGET = 8000
_CONTENT_BLOCKS_LIMIT = 50
_HEADINGS_LIMIT = 10
_METADATA_LIMIT = 12
_BLOCK_TEXT_LIMIT = 500


def format_read_view(read_view: ReadView, selection_scope: str = "page") -> str:
    lines: list[str] = [
        f"URL: {read_view.url}",
        f"Title: {read_view.title}",
    ]

    if read_view.metadata:
        lines.append("Metadata:")
        for key, value in list(read_view.metadata.items())[:_METADATA_LIMIT]:
            if value:
                lines.append(f"  {key}: {value[:200]}")

    if read_view.headings:
        lines.append(f"Headings: {' | '.join(read_view.headings[:_HEADINGS_LIMIT])}")

    if selection_scope == "selection" and read_view.selected_text:
        lines.append(f"\nSELECTED TEXT:\n{read_view.selected_text}")
        return "\n".join(lines)

    if read_view.content_blocks:
        lines.append("\nCONTENT BLOCKS:")
        for i, block in enumerate(read_view.content_blocks[:_CONTENT_BLOCKS_LIMIT], 1):
            text = str(block.get("text", ""))[:_BLOCK_TEXT_LIMIT]
            if text:
                lines.append(f"{i}. {text}")

    if read_view.visible_text:
        raw_text = read_view.visible_text
        truncated = len(raw_text) > _VISIBLE_TEXT_BUDGET
        snippet = raw_text[:_VISIBLE_TEXT_BUDGET].strip()
        if snippet:
            lines.append(f"\nPAGE TEXT:\n{snippet}")
            if truncated:
                lines.append("[Content truncated — summary covers the beginning of the page only]")

    return "\n".join(lines)
