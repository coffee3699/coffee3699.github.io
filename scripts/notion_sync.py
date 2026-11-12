"""Export only explicitly approved Notion posts. No third-party dependencies."""
import datetime as dt
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
API = 'https://api.notion.com/v1/'


def network_open(opener, target):
    for attempt in range(4):
        try:
            return opener(target, timeout=60)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(API + path, data=data, headers={
        'Authorization': 'Bearer ' + os.environ['NOTION_TOKEN'],
        'Notion-Version': '2025-09-03', 'Content-Type': 'application/json'})
    for attempt in range(5):
        try:
            with network_open(urllib.request.urlopen, req) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                time.sleep(min(30, 2 ** attempt + 1))
                continue
            raise RuntimeError(f'Notion API returned HTTP {exc.code}; check token, connection access and data source ID') from None
    raise RuntimeError('Notion API retries exhausted')


def paginate(path, payload=None):
    cursor = None
    while True:
        args = {'page_size': 100}
        if cursor:
            args['start_cursor'] = cursor
        result = request(path + '?' + urllib.parse.urlencode(args)) if payload is None else request(path, {**payload, **args})
        yield from result['results']
        if not result.get('has_more'):
            break
        cursor = result['next_cursor']


def plain(parts):
    return ''.join(p.get('plain_text', p.get('text', {}).get('content', '')) for p in parts)


def safe_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname:
        raise ValueError('Only HTTP(S) links are supported')
    if parsed.hostname == 'notion.so' or parsed.hostname.endswith('.notion.so') or parsed.hostname == 'notion.site' or parsed.hostname.endswith('.notion.site'):
        raise ValueError('Remove private Notion links from publishable content')
    return url.replace(' ', '%20').replace('(', '%28').replace(')', '%29')


def rich(parts):
    out = []
    for p in parts:
        if p.get('type') == 'equation':
            out.append('\\(' + p['equation']['expression'] + '\\)')
            continue
        if p.get('type') == 'mention' and p.get('mention', {}).get('type') in ('page', 'database', 'user'):
            out.append(p.get('plain_text', ''))
            continue
        s = p.get('plain_text', p.get('text', {}).get('content', ''))
        a = p.get('annotations', {})
        if a.get('code'):
            fence = '`' * (max([len(m) for m in re.findall(r'`+', s)] + [0]) + 1)
            s = fence + ' ' + s + ' ' + fence
        else:
            s = re.sub(r'([\\`*_\[\]<>])', r'\\\1', s)
            if a.get('bold'): s = '**' + s + '**'
            if a.get('italic'): s = '*' + s + '*'
            if a.get('strikethrough'): s = '~~' + s + '~~'
        link = p.get('href') or p.get('text', {}).get('link', {}) or {}
        if isinstance(link, dict): link = link.get('url')
        if link:
            host = urllib.parse.urlparse(link).hostname or ''
            if host not in ('notion.so', 'app.notion.com', 'www.notion.so') and not host.endswith('.notion.so'):
                s = '[' + s + '](' + safe_url(link) + ')'
        out.append(s)
    return ''.join(out)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def image_download(url, folder):
    # Do not forward the Notion token to asset servers. Validate every redirect.
    opener = urllib.request.build_opener(NoRedirect)
    original = url
    for _ in range(6):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Images must have public HTTPS URLs')
        for addr in socket.getaddrinfo(parsed.hostname, parsed.port or 443):
            if not ipaddress.ip_address(addr[4][0]).is_global:
                raise ValueError('Non-public image address rejected')
        try:
            response = network_open(opener.open, url)
            break
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                url = urllib.parse.urljoin(url, exc.headers['Location'])
                continue
            raise RuntimeError(f'Image download failed: HTTP {exc.code}') from None
    else:
        raise ValueError('Too many image redirects')
    with response:
        mime = response.headers.get_content_type()
        ext = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif', 'image/webp': '.webp', 'image/avif': '.avif'}.get(mime)
        if not ext: raise ValueError('Unsupported image format; use PNG, JPEG, GIF, WebP or AVIF')
        data = response.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024: raise ValueError('Image exceeds 20 MB')
    name = hashlib.sha256(original.split('?')[0].encode()).hexdigest()[:20] + ext
    (folder / name).write_bytes(data)
    return name


def render(blocks, folder):
    output = []
    for b in blocks:
        kind = b['type']
        v = b[kind]
        text = rich(v.get('rich_text', []))
        children = lambda: list(paginate(f"blocks/{b['id']}/children"))
        if kind == 'paragraph': item = text
        elif kind.startswith('heading_'): item = '#' * int(kind[-1]) + ' ' + text
        elif kind in ('bulleted_list_item', 'numbered_list_item', 'to_do'):
            prefix = {'bulleted_list_item': '- ', 'numbered_list_item': '1. ', 'to_do': '- [x] ' if v.get('checked') else '- [ ] '}[kind]
            item = prefix + text
            if b.get('has_children'):
                item += '\n' + '\n'.join('    ' + line for line in render(children(), folder).splitlines())
            output.append(item)
            continue
        elif kind in ('quote', 'callout'):
            item = text
            if b.get('has_children'): item += '\n\n' + render(children(), folder)
            output.append('\n'.join('> ' + line for line in item.splitlines()))
            continue
        elif kind == 'code':
            code = plain(v.get('rich_text', []))
            fence = '`' * max(3, max([len(m) + 1 for m in re.findall(r'`+', code)] + [3]))
            lang = re.sub(r'[^a-zA-Z0-9_+-]', '', v.get('language', ''))
            item = f'{fence}{lang}\n{code}\n{fence}'
        elif kind == 'equation': item = '$$\n' + v['expression'] + '\n$$'
        elif kind == 'divider': item = '---'
        elif kind == 'image':
            name = image_download(v[v['type']]['url'], folder)
            caption = rich(v.get('caption', []))
            item = f'![{caption}]({name})'
        elif kind == 'video' and v.get('type') == 'external':
            url = safe_url(v['external']['url'])
            label = rich(v.get('caption', [])) or '观看视频'
            item = f'[{label}]({url})'
        elif kind == 'table':
            rows = [[rich(c).replace('|', '\\|').replace('\n', ' ') for c in x['table_row']['cells']] for x in children()]
            if not rows: continue
            if not v.get('has_column_header'): rows.insert(0, [''] * len(rows[0]))
            rows.insert(1, ['---'] * len(rows[0]))
            item = '\n'.join('| ' + ' | '.join(row) + ' |' for row in rows)
            output.append(item)
            continue
        elif kind in ('column_list', 'column', 'toggle'):
            item = text
        elif kind in ('bookmark', 'embed', 'link_preview'):
            url = safe_url(v['url'])
            item = '[' + (rich(v.get('caption', [])) or '参考链接') + '](' + url + ')'
        elif kind == 'child_page':
            # Child research pages are separate documents, not part of this post.
            output.append(v.get('title', '子页面'))
            continue
        elif kind == 'unsupported' and b.get('id', '').replace('-', '') == '7daad8a751af838f8fb481df2fefa162':
            output.append('（此处原文的推文嵌入暂不支持网页显示。）')
            print('Note: one original tweet embed is unavailable through the Notion API.')
            continue
        elif kind == 'table_of_contents': continue  # Hugo renders its own TOC.
        else: raise ValueError(f'Unsupported Notion block: {kind}; convert it before publishing')
        if b.get('has_children'): item += '\n\n' + render(children(), folder)
        output.append(item)
    return '\n\n'.join(output)


def metadata(page, now):
    p = page['properties']
    if (p.get('Status', {}).get('select') or {}).get('name') != 'Published' or p.get('Public Approved', {}).get('checkbox') is not True:
        return None
    date = (p.get('Published Date', {}).get('date') or {}).get('start')
    if not date: raise ValueError('Approved post has no Published Date')
    date_obj = dt.datetime.fromisoformat(date.replace('Z', '+00:00'))
    if date_obj.tzinfo is None: date_obj = date_obj.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
    if date_obj > now: return None
    slug = plain(p.get('Slug', {}).get('rich_text', []))
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug): raise ValueError('Slug must be lowercase words separated by hyphens')
    title = plain(p['Name']['title'])
    if not title: raise ValueError('Article title cannot be empty')
    summary = plain(p.get('Summary', {}).get('rich_text', []))
    starred = p.get('Starred', {}).get('checkbox') is True
    series = list(dict.fromkeys(x['name'] for x in p.get('Series', p.get('Tags', {})).get('multi_select', [])))
    if starred and '星标' not in series:
        series.append('星标')
    return {'title': title, 'date': date_obj.isoformat(), 'slug': slug, 'description': summary, 'summary': summary,
            'series': series,
            'categories': [p['Category']['select']['name']] if p.get('Category', {}).get('select') else [],
            'starred': starred,
            'draft': False}


def main():
    if not os.getenv('NOTION_TOKEN') or not os.getenv('NOTION_DATA_SOURCE_ID'):
        raise ValueError('Configure NOTION_TOKEN secret and NOTION_DATA_SOURCE_ID variable')
    source = os.environ['NOTION_DATA_SOURCE_ID']
    if not re.fullmatch(r'[a-fA-F0-9-]{32,36}', source): raise ValueError('Invalid data source ID')
    stage = ROOT / '.notion-stage'
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir()
    seen = set()
    query = {}  # Check publication fields locally after page moves; do not depend on the server-side filter index.
    try:
        for page in paginate(f'data_sources/{source}/query', query):
            meta = metadata(page, dt.datetime.now(ZoneInfo('Asia/Shanghai')))
            if meta is None: continue
            slug = meta['slug']
            if slug in seen: raise ValueError('Duplicate Slug in published posts')
            seen.add(slug)
            folder = stage / slug
            folder.mkdir()
            body = render(paginate(f"blocks/{page['id']}/children"), folder)
            if not body.strip() or '编辑工作稿' in body or '从这里开始写作' in body:
                raise ValueError('Replace editorial scaffold with a completed article before publishing')
            (folder / 'index.md').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n\n' + body + '\n')
        target = ROOT / 'content/posts'
        if target.exists(): shutil.rmtree(target)
        stage.rename(target)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    print(f'Synced {len(seen)} approved posts.')


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        # No tokens, signed asset URLs or private article contents in CI logs.
        detail = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else 'Check publication fields and supported blocks'
        print(f'Sync failed ({type(exc).__name__}): {detail}. Deployment stopped.', file=sys.stderr)
        sys.exit(1)
