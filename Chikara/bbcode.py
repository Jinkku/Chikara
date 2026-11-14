"""osu!-style BBCode for profile bios -> safe HTML (and plain text for search descriptions).

Everything is HTML-escaped first; only the tags below turn into markup, with their arguments checked.
Unknown or unbalanced tags stay as literal text, like osu!.

  [b] [i] [u] [s]/[strike]   [color=#hex|name]   [size=50|85|100|150]   [centre]/[center]
  [url]https://..[/url]  [url=https://..]text[/url]   [img]https://..[/img]
  [quote]..[/quote]  [quote="name"]..[/quote]   [spoiler]..[/spoiler]   [box=title]..[/box]
  [heading]..[/heading]   [notice]..[/notice]   [code]..[/code]   [c]..[/c]
  [list][*]a[*]b[/list]   [list=1] numbers the items
"""
import re
from html import escape

TOKEN = re.compile(r"(\[/?(?:[a-z]+|\*)(?:=[^\]\n]{0,300})?\])", re.IGNORECASE)
COLOUR = re.compile(r"^(#[0-9a-f]{3}|#[0-9a-f]{6}|[a-z]{3,20})$", re.IGNORECASE)
SIZES = {"50": 50, "85": 85, "100": 100, "150": 150}
RAW = {"img", "code", "c"}            # content is taken as-is (no tags inside)
BLOCK = {"centre", "center", "quote", "box", "heading", "notice", "code", "list", "*"}  # eat one newline after these


def _url(value):
    value = (value or "").strip().strip('"')
    if re.match(r"^https?://[^\s<>\"']+$", value, re.IGNORECASE):
        return value
    return None


def _open(name, arg):
    """(open html, close html) for a tag, or None when it isn't allowed / its argument is bad."""
    if name == "b": return "<strong>", "</strong>"
    if name == "i": return "<em>", "</em>"
    if name == "u": return "<u>", "</u>"
    if name in ("s", "strike"): return "<del>", "</del>"
    if name == "color":
        if arg and COLOUR.match(arg.strip()):
            return f'<span style="color:{arg.strip()}">', "</span>"
        return None
    if name == "size":
        if arg and arg.strip() in SIZES:
            return f'<span style="font-size:{SIZES[arg.strip()]}%">', "</span>"
        return None
    if name in ("centre", "center"): return '<div class="bb-center">', "</div>"
    if name == "url":
        link = _url(arg)
        if link is None:
            return None
        return f'<a href="{escape(link)}" rel="nofollow ugc noopener" target="_blank">', "</a>"
    if name == "quote":
        by = (arg or "").strip().strip('"')
        head = f'<p class="bb-quote-by">{escape(by)} wrote:</p>' if by else ""
        return f'<blockquote class="bb-quote">{head}', "</blockquote>"
    if name == "spoiler": return '<span class="bb-spoiler" tabindex="0">', "</span>"
    if name == "box":
        title = (arg or "").strip() or "spoiler"
        return f'<details class="bb-box"><summary>{escape(title)}</summary><div>', "</div></details>"
    if name == "heading": return '<h3 class="bb-heading">', "</h3>"
    if name == "notice": return '<div class="bb-notice">', "</div>"
    if name == "list":
        return ("<ol>", "</ol>") if (arg or "").strip() == "1" else ("<ul>", "</ul>")
    if name == "*": return "<li>", "</li>"
    return None


def _tokens(text):
    out = []
    for part in TOKEN.split(text):
        if not part:
            continue
        m = re.match(r"^\[(/?)([a-z]+|\*)(?:=(.*))?\]$", part, re.IGNORECASE)
        if m:
            out.append(("close" if m.group(1) else "open", m.group(2).lower(), m.group(3), part))
        else:
            out.append(("text", None, None, part))
    return out


def to_html(text):
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    tokens = _tokens(text)
    html, stack = [], []   # stack of (name, close html)
    eat_newline = False
    i = 0
    while i < len(tokens):
        kind, name, arg, raw = tokens[i]
        i += 1
        if kind == "text":
            if eat_newline and raw.startswith("\n"):
                raw = raw[1:]
            eat_newline = False
            nxt = tokens[i] if i < len(tokens) else None
            if nxt and nxt[0] != "text" and nxt[1] in BLOCK and raw.endswith("\n"):
                raw = raw[:-1]  # the newline before a block tag / list item is just layout
            html.append(escape(raw).replace("\n", "<br>"))
            continue
        eat_newline = False

        if kind == "open" and name in RAW | {"url"} and not (name == "url" and arg):
            # [img]src[/img], [url]link[/url], [code]..[/code], [c]..[/c]: the content up to the matching close tag
            j = next((k for k in range(i, len(tokens)) if tokens[k][0] == "close" and tokens[k][1] == name), None)
            if j is not None:
                content = "".join(t[3] for t in tokens[i:j])
                done = None
                if name == "img":
                    src = _url(content)
                    if src:
                        done = f'<img class="bb-img" src="{escape(src)}" alt="" loading="lazy" referrerpolicy="no-referrer">'
                elif name == "url":
                    link = _url(content)
                    if link:
                        done = f'<a href="{escape(link)}" rel="nofollow ugc noopener" target="_blank">{escape(link)}</a>'
                elif name == "code":
                    done = f'<pre class="bb-code">{escape(content.strip(chr(10)))}</pre>'
                    eat_newline = True
                else:
                    done = f'<code class="bb-c">{escape(content)}</code>'
                if done is not None:
                    html.append(done)
                    i = j + 1
                    continue
            html.append(escape(raw))
            continue

        if kind == "open":
            if name == "*":
                if not any(n == "list" for n, _ in stack):
                    html.append(escape(raw)); continue
                while stack and stack[-1][0] not in ("list", "*"):
                    html.append(stack.pop()[1])   # tags left open inside the last item
                if stack and stack[-1][0] == "*":
                    html.append(stack.pop()[1])
            tag = _open(name, arg)
            if tag is None:
                html.append(escape(raw)); continue
            html.append(tag[0])
            stack.append((name, tag[1]))
            eat_newline = name in BLOCK
            continue

        # close tag: close everything opened after it; an unmatched one stays as text
        alias = {"center": ("center", "centre"), "centre": ("center", "centre"),
                 "strike": ("strike", "s"), "s": ("strike", "s")}.get(name, (name,))
        if not any(n in alias for n, _ in stack):
            html.append(escape(raw)); continue
        while stack:
            n, close = stack.pop()
            html.append(close)
            if n in alias:
                break
        eat_newline = name in BLOCK
    while stack:
        html.append(stack.pop()[1])
    return "".join(html)


def to_plain(text):
    """The words only: tags removed, images dropped (search descriptions)."""
    text = re.sub(r"\[img\].*?\[/img\]", " ", str(text or ""), flags=re.IGNORECASE | re.DOTALL)
    def tag(m):
        name = re.match(r"^\[/?([a-z]+|\*)", m.group(0), re.IGNORECASE).group(1).lower()
        return " " if name in BLOCK else ""
    text = TOKEN.sub(tag, text)
    return " ".join(text.split())
