"""
Preserves Telegram's rich-text styling (bold, italic, monospace, links, etc.)
when an admin types a styled ad message, by converting the message's `entities`
into MarkdownV2 syntax. This lets us store ad text as a single MarkdownV2 string
in the Gist, and re-send it later with parse_mode="MarkdownV2" so it looks
exactly like what the admin typed.

Why this is needed: Telegram delivers styled text to bots as PLAIN text plus a
separate `entities` list describing which character ranges are bold/italic/etc.
If we only save `message.text`, all styling is silently lost.
"""

# Characters that MarkdownV2 requires to be escaped when they appear as literal text
# (i.e. NOT part of the markup itself).
_MDV2_SPECIAL = r"_*[]()~`>#+-=|{}.!"


def _escape(text):
    return "".join(f"\\{ch}" if ch in _MDV2_SPECIAL else ch for ch in text)


def entities_to_markdownv2(text, entities):
    """
    text: the plain message text (update.message.text or .caption)
    entities: update.message.entities or .caption_entities (list of MessageEntity)
    Returns a MarkdownV2-formatted string equivalent to the styled original.
    """
    if not entities:
        return _escape(text)

    code_units = text.encode("utf-16-le")
    num_units = len(code_units) // 2

    def unit_slice(start, end):
        raw = code_units[start * 2:end * 2]
        return raw.decode("utf-16-le")

    pieces = []
    cursor = 0
    for ent in sorted(entities, key=lambda e: e.offset):
        start = ent.offset
        end = ent.offset + ent.length
        if start > cursor:
            pieces.append(_escape(unit_slice(cursor, start)))

        inner = unit_slice(start, end)
        etype = ent.type

        if etype == "bold":
            pieces.append(f"*{_escape(inner)}*")
        elif etype == "italic":
            pieces.append(f"_{_escape(inner)}_")
        elif etype == "underline":
            pieces.append(f"__{_escape(inner)}__")
        elif etype == "strikethrough":
            pieces.append(f"~{_escape(inner)}~")
        elif etype == "code":
            pieces.append(f"`{inner}`")  # no escaping inside code spans
        elif etype == "pre":
            lang = getattr(ent, "language", "") or ""
            pieces.append(f"```{lang}\n{inner}\n```")
        elif etype == "text_link":
            url = ent.url or ""
            pieces.append(f"[{_escape(inner)}]({url})")
        elif etype == "spoiler":
            pieces.append(f"||{_escape(inner)}||")
        else:
            # url, mention, hashtag, etc. — leave as plain escaped text, Telegram
            # will still auto-link @mentions/URLs on its own when rendering
            pieces.append(_escape(inner))

        cursor = max(cursor, end)

    if cursor < num_units:
        pieces.append(_escape(unit_slice(cursor, num_units)))

    return "".join(pieces)
