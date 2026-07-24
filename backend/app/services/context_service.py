from app.schemas.request import PageContext, PriorStep


def format_page_context(ctx: PageContext) -> str:
    """
    Converts a PageContext into a clean, readable text block for the AI prompt.
    Structured text produces better AI results than raw JSON.
    """
    lines: list[str] = [
        f"URL: {ctx.url}",
        f"Title: {ctx.title}",
    ]

    if ctx.metadata:
        lines.append("Metadata:")
        for key, value in list(ctx.metadata.items())[:12]:
            if value:
                lines.append(f"- {key}: {value[:300]}")

    if ctx.headings:
        lines.append(f"Headings: {' | '.join(ctx.headings[:5])}")

    if ctx.selected_text:
        lines.append(f"Selected text: \"{ctx.selected_text}\"")

    if ctx.interactive_elements:
        lines.append("\nINTERACTIVE ELEMENTS (use the SELECTOR value exactly as shown):")
        for i, el in enumerate(ctx.interactive_elements[:80], 1):
            tag = el.type
            if el.input_type:
                tag += f"[{el.input_type}]"

            meta: list[str] = [tag]
            if el.text:
                meta.append(f'label="{el.text}"')
            if el.placeholder:
                meta.append(f'placeholder="{el.placeholder}"')
            if el.role:
                meta.append(f'role="{el.role}"')
            if el.aria_label:
                meta.append(f'aria-label="{el.aria_label}"')
            if el.accessibility_name:
                meta.append(f'accessibility-name="{el.accessibility_name}"')
            if el.href:
                meta.append(f'href="{el.href[:240]}"')
            if el.selector_id:
                meta.append(f'selector-id="{el.selector_id}"')
            if el.state:
                meta.append(f"state={el.state}")

            # Selector is shown FIRST and clearly separated so the AI copies it directly.
            lines.append(f'{i}. SELECTOR: {el.selector}  ({", ".join(meta)})')

    if ctx.content_blocks:
        lines.append("\nVISIBLE CONTENT BLOCKS (use these for reading/comparison; selectors may identify cards/rows):")
        for i, block in enumerate(ctx.content_blocks[:20], 1):
            lines.append(f"{i}. SELECTOR: {block.selector}")
            if block.href:
                lines.append(f"   URL: {block.href[:300]}")
            lines.append(f"   TEXT: {block.text[:500]}")

    if ctx.visible_text:
        snippet = ctx.visible_text[:500].strip()
        if snippet:
            lines.append(f"\nPAGE TEXT SNIPPET:\n{snippet}")

    if ctx.images:
        lines.append("\nIMAGES:")
        for i, img_url in enumerate(ctx.images[:15], 1):
            lines.append(f"- Image {i}: {img_url}")

    return "\n".join(lines)


def format_prior_steps(steps: list[PriorStep]) -> str:
    """
    Formats already-executed steps into a section the AI uses to avoid
    repeating work and to understand where in the workflow we are.
    """
    if not steps:
        return ""

    lines = [
        "\nRECENT EXECUTED STEPS:",
        "These steps already ran. Successful steps should not be repeated. Failed steps identify what did not work; recover using the current page state and exact current selectors.",
    ]
    for i, step in enumerate(steps, 1):
        status = "SUCCESS" if step.execution_result.lower().startswith(("success", "clicked", "filled", "navigating", "waited", "scrolled")) else "FAILED"
        line = f"{i}. {status} {step.action_type.upper()}: {step.description}"
        if step.value:
            line += f' (value: "{step.value}")'
        line += f" → {step.execution_result}"
        lines.append(line)
        if step.page_url:
            lines.append(f"   Page URL: {step.page_url[:300]}")
        if step.page_title:
            lines.append(f"   Page title: {step.page_title[:200]}")
        if step.page_metadata:
            lines.append("   Page metadata:")
            for key, value in list(step.page_metadata.items())[:12]:
                if value:
                    lines.append(f"   - {key}: {value[:300]}")
        if step.page_analysis:
            lines.append(f"   Page analysis before this step: {step.page_analysis}")

    return "\n".join(lines)
