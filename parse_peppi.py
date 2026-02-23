import sys
import re
import html

def clean_html_text(raw_html):
    # Remove all HTML tags
    clean = re.sub(r'<[^>]+>', '', raw_html)
    # Unescape HTML entities
    return html.unescape(clean)

def parse_peppi(html_path):
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return f"<error>Failed to read file: {e}</error>"

    # 1. Extract the main prompt block (usually before the first triple quote or before chat history)
    # The main prompt is wrapped in <pre class=sf-dump ...> ... """
    main_prompt_match = re.search(r'<pre class=sf-dump.*?>\s*"""(.*?)"""', content, re.DOTALL)
    if main_prompt_match:
        main_prompt_raw = main_prompt_match.group(1)
        main_prompt_text = clean_html_text(main_prompt_raw)
    else:
        # Fallback: just use the whole thing if the triple-quote match fails
        main_prompt_text = clean_html_text(content)

    # Extract standard tags from the cleaned text
    tags = ['rules', 'identity', 'user_context', 'backstory', 'memory_note']
    extracted = {}
    for tag in tags:
        pattern = f'<{tag}>(.*?)</{tag}>'
        match = re.search(pattern, main_prompt_text, re.DOTALL)
        if match:
            extracted[tag] = match.group(1).strip()
        else:
            extracted[tag] = ""

    # 2. Extract Chat History from the second sf-dump block (the array)
    messages = []
    # Chat history is typically in <samp data-depth=2 ...> blocks
    blocks = re.findall(r'<samp data-depth=2 class=sf-dump-compact>(.*?)</samp>', content, re.DOTALL)
    for block in blocks:
        # Each block has "role" and "content"
        # We need to strip tags from each part
        role_match = re.search(r'"<span class=sf-dump-key>role</span>"\s*=>\s*"<span class=sf-dump-str.*?>(.*?)</span>"', block)
        content_match = re.search(r'"<span class=sf-dump-key>content</span>"\s*=>\s*"<span class=sf-dump-str.*?>(.*?)</span>"', block)
        
        if role_match and content_match:
            role = clean_html_text(role_match.group(1))
            msg_content = clean_html_text(content_match.group(1))
            messages.append({
                'role': role,
                'content': msg_content
            })

    # Build XML
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<peppi_response>')
    for tag in tags:
        val = extracted.get(tag, "")
        # Minimal XML escaping for the values
        escaped_val = val.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        xml.append(f'  <{tag}>{escaped_val}</{tag}>')
    
    xml.append('  <chat_history>')
    for m in messages:
        esc_role = m['role'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        esc_content = m['content'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        xml.append(f'    <message role="{esc_role}">{esc_content}</message>')
    xml.append('  </chat_history>')
    xml.append('</peppi_response>')
    
    return "\n".join(xml)

if __name__ == "__main__":
    import os
    target_html = "e:\\Peppi\\moltbot-render\\response-peppi.html"
    target_xml = "e:\\Peppi\\moltbot-render\\peppi_response.xml"
    
    if os.path.exists(target_html):
        result = parse_peppi(target_html)
        with open(target_xml, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Successfully generated {target_xml}")
    else:
        print(f"Error: {target_html} not found")
