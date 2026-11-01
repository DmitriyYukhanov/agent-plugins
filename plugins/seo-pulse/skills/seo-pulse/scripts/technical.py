"""Check explicit public URL expectations without credentials or site mutations."""
import argparse
import hashlib
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
from queue import Queue, Empty
import re
import socket
import sys
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit, unquote, urldefrag
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

LIMIT = 1024 * 1024
META = {'description', 'og:title', 'og:description', 'og:image', 'twitter:card',
        'twitter:title', 'twitter:description', 'twitter:image'}
ARTICLE_EXCLUDE = {'nav','header','footer','aside','h1','h2','h3','h4','h5','h6'}


def origin_id(value):
    p = urlsplit(value)
    return p.scheme,p.hostname,p.port or (443 if p.scheme=='https' else 80)


def checked_url(value, origins=None):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Invalid URL')
    p = urlsplit(value)
    decoded = unquote(value)
    if (p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password
            or p.fragment or p.port not in (None, 80 if p.scheme == 'http' else 443)
            or re.search(r'[\x00-\x20\x7f<>"`|\\]', decoded)
            or any(x in ('.', '..') for x in unquote(p.path).split('/'))
            or not re.fullmatch(r'[a-z0-9.-]+', p.hostname) or p.hostname.endswith('.')):
        raise ValueError('Invalid public URL')
    host = p.hostname
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError('Non-public IP')
    except ValueError as error:
        if str(error) == 'Non-public IP': raise
        if '.' not in host or host.endswith(('.local', '.localhost', '.internal')):
            raise ValueError('Non-public hostname') from error
    if origins is not None and origin_id(value) not in [origin_id(o) for o in origins]:
        raise ValueError('URL escapes configured origins')
    return value


def validate_config(config):
    if not isinstance(config, dict): raise ValueError('Config must be an object')
    c = config.get('technical')
    if not isinstance(c, dict) or set(c) - {'origins', 'pages', 'sitemap_url', 'link_prefixes'}:
        raise ValueError('Configure technical origins and pages')
    origins = c.get('origins')
    if not isinstance(origins, list) or not 1 <= len(origins) <= 8 or any(not isinstance(x,str) for x in origins) or len(set(origins)) != len(origins):
        raise ValueError('Configure 1 to 8 distinct origins')
    for origin in origins:
        checked_url(origin)
        p = urlsplit(origin)
        if p.path or p.query: raise ValueError('Origins cannot include paths or queries')
    pages = c.get('pages')
    if not isinstance(pages, list) or not 1 <= len(pages) <= 1000:
        raise ValueError('Configure 1 to 1000 pages; each run is limited to 100 requests')
    prefixes = c.get('link_prefixes', [])
    if not isinstance(prefixes,list) or len(prefixes)>32: raise ValueError('Invalid link prefixes')
    for prefix in prefixes:
        checked_url(prefix,origins)
        if urlsplit(prefix).query or re.search(r'%2f|%5c|%25',urlsplit(prefix).path,re.I):
            raise ValueError('Link prefixes require unambiguous paths without queries')
    seen = set()
    for page in pages:
        if not isinstance(page, dict) or set(page) - {'url','role','canonical','status','final_url','required_meta','organization','in_sitemap','group','require_title','article','lang','check_links'}:
            raise ValueError('Unknown page fields')
        url = checked_url(page.get('url'), origins)
        if url in seen: raise ValueError('Duplicate URL')
        seen.add(url)
        checked_url(page.get('final_url', url), origins)
        status = page.get('status', 200)
        if type(status) is not int or not 100 <= status <= 599: raise ValueError('Invalid status')
        role = page.get('role')
        if role not in ('public','nonindexable','excluded'): raise ValueError('Explicit page role required')
        if role != 'excluded' and status != 200: raise ValueError('Content roles require status 200')
        canonical = page.get('canonical')
        if role == 'public' and not canonical: raise ValueError('Public page needs canonical expectation')
        if canonical is not None: checked_url(canonical, origins)
        for flag in ('organization','in_sitemap','require_title','article','check_links'):
            if flag in page and type(page[flag]) is not bool: raise ValueError('Invalid boolean expectation')
        if any(key in page for key in ('require_title','article','lang','check_links')) and role != 'public':
            raise ValueError('Title, article, language and link checks require a public page')
        if 'lang' in page and (not isinstance(page['lang'],str) or not re.fullmatch(r'[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*',page['lang'])):
            raise ValueError('Invalid language expectation')
        if page.get('check_links') and not prefixes: raise ValueError('Link sources require explicit owned link prefixes')
        required = page.get('required_meta', [])
        if not isinstance(required, list) or any(x not in META for x in required) or len(required) != len(set(required)):
            raise ValueError('Unsupported metadata')
        if 'group' in page and (not isinstance(page['group'], str) or not re.fullmatch(r'[a-z0-9-]{1,64}', page['group'])):
            raise ValueError('Invalid group')
        if role == 'excluded' and (canonical or required or page.get('organization')):
            raise ValueError('Excluded role supports only status/final URL and explicit sitemap expectations')
        if 'in_sitemap' in page and not c.get('sitemap_url'): raise ValueError('Sitemap URL required')
    if 'sitemap_url' in c: checked_url(c['sitemap_url'], origins)
    return c


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def public_host(url):
    host = urlsplit(url).hostname
    answers = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    if not answers or any(not ipaddress.ip_address(x[4][0]).is_global for x in answers):
        raise ValueError('Host does not resolve exclusively to public addresses')


def in_link_scope(url, prefixes):
    p = urlsplit(url)
    if re.search(r'%2f|%5c|%25',p.path,re.I): raise ValueError('Ambiguous encoded link path')
    for prefix in prefixes:
        root = urlsplit(prefix)
        if origin_id(url) == origin_id(prefix):
            path = root.path.rstrip('/')
            if unquote(p.path) == unquote(path) or unquote(p.path).startswith(unquote(path)+'/'): return True
    return False


def fetch(url, origins, budget=None, deadline=None, read_body=True, link_prefixes=None):
    deadline = deadline or time.monotonic() + 10
    opener = build_opener(NoRedirect())
    trace = []
    current = url
    for _ in range(6):
        if time.monotonic() >= deadline: raise TimeoutError("Elapsed request budget exhausted")
        if budget is not None and budget[0] <= 0: raise ValueError('Request budget exhausted')
        checked_url(current, origins)
        if link_prefixes is not None and not in_link_scope(current,link_prefixes): raise ValueError('Link escapes configured path scope')
        public_host(current)
        if time.monotonic() >= deadline: raise TimeoutError("Elapsed request budget exhausted")
        if budget is not None:
            if budget[0] <= 0: raise ValueError('Request budget exhausted')
            budget[0] -= 1
        try:
            reply = opener.open(Request(current, headers={'User-Agent':'SEO-Pulse-Technical/1.0', 'Accept-Encoding':'identity'}), timeout=max(.001, min(10, deadline-time.monotonic())))
        except HTTPError as error:
            reply = error
        try:
            status = reply.code
            trace.append({'url':current, 'status':status})
            if status in (301,302,303,307,308):
                location = reply.headers.get('Location')
                if not location: raise ValueError('Redirect without Location')
                target = checked_url(urljoin(current, location))
                if (origin_id(target) not in [origin_id(o) for o in origins]
                        or link_prefixes is not None and not in_link_scope(target,link_prefixes)):
                    return {'final_url':current, 'status':None, 'trace':trace,
                            'headers':[], 'body':'', 'rejected_destination':target}
                current = target
                continue
            if time.monotonic() >= deadline: raise TimeoutError("Elapsed request budget exhausted")
            if not read_body:
                return {'final_url':current, 'status':status, 'trace':trace,
                        'headers':list(reply.headers.items()), 'body':''}
            raw = reply.read(LIMIT + 1)
            if len(raw) > LIMIT: raise ValueError('Response exceeds 1 MiB')
            if reply.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                raise ValueError('Unsupported compressed response')
            return {'final_url':current, 'status':status, 'trace':trace,
                    'headers':list(reply.headers.items()), 'body':raw.decode('utf-8-sig')}
        finally:
            reply.close()
    raise ValueError('Redirect limit exceeded')


class Signals(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.head = True
        self.hidden = 0
        self.text_tag = None
        self.ambiguous = False
        self.base = None
        self.canonicals = []
        self.meta = {}
        self.robots = []
        self.jsonld = []
        self.script = None
        self.titles = []
        self.title_active = False
        self.languages = []
        self.content_context = []
        self.article_text = []
        self.hrefs = []
        self.truncated = False

    def handle_starttag(self, tag, attrs):
        if self.text_tag: return
        if tag in ('template','noscript'): self.hidden += 1
        if self.hidden: return
        d = dict(attrs)
        if tag == 'html':
            self.languages.append(d.get('lang') or '')
            if len(attrs) != len(d): self.ambiguous = True
        if tag == 'title' and self.head:
            self.titles.append(''); self.title_active = True
        if tag in ARTICLE_EXCLUDE or tag == 'article': self.content_context.append(tag)
        if tag == 'a' and d.get('href') is not None:
            if len(attrs) != len(d): self.ambiguous = True
            if len(self.hrefs)<1000: self.hrefs.append(d['href'])
            else: self.truncated = True
        if tag not in ('html','head','base','basefont','bgsound','link','meta','title','style','script'):
            self.head = False
        if tag in ('title','style','script'): self.text_tag = tag
        if tag == 'script' and (d.get('type') or '').lower() == 'application/ld+json': self.script = ''
        if tag == 'meta':
            name = (d.get('name') or d.get('property') or '').lower()
            if len(attrs) != len(d): self.ambiguous = True
            if name in ('robots','googlebot'): self.robots.append(d.get('content') or '')
        if not self.head: return
        if tag in ('meta','link','base') and len(attrs) != len(d): self.ambiguous = True
        if tag == 'base' and self.base is None and 'href' in d: self.base = d['href'] or ''
        if tag == 'link' and 'canonical' in (d.get('rel') or '').lower().split():
            self.canonicals.append(d.get('href') if len(attrs) == len(d) else None)
        if tag == 'meta':
            name = (d.get('name') or d.get('property') or '').lower()
            self.meta.setdefault(name, []).append(d.get('content') or '')

    def handle_endtag(self, tag):
        if self.text_tag and tag != self.text_tag: return
        if self.text_tag == tag: self.text_tag = None
        if tag in ('template','noscript') and self.hidden: self.hidden -= 1; return
        if self.hidden: return
        if tag == 'title': self.title_active = False
        if tag in self.content_context:
            index = len(self.content_context)-1-self.content_context[::-1].index(tag)
            if index != len(self.content_context)-1: self.ambiguous = True
            del self.content_context[index:]
        if tag == 'head': self.head = False
        if tag == 'script' and self.script is not None:
            self.jsonld.append(self.script)
            self.script = None

    def handle_data(self, data):
        if self.hidden: return
        if self.title_active and self.text_tag == 'title': self.titles[-1] += data
        if not self.text_tag and 'article' in self.content_context and not ARTICLE_EXCLUDE.intersection(self.content_context):
            self.article_text.append(data)
        if self.script is not None: self.script += data
        if not self.text_tag and data.strip(' \t\r\n\f'): self.head = False


def noindex(values, *, header=True):
    parameters = {'max-snippet','max-image-preview','max-video-preview','unavailable_after'}
    for value in values:
        scope = None
        for part in value.lower().split(','):
            part = part.strip()
            if header and ':' in part:
                prefix, rest = part.split(':',1)
                if prefix.strip() not in parameters:
                    scope, part = prefix.strip(), rest.strip()
            if scope in (None,'googlebot') and part in ('noindex','none'): return True
    return False


def organization(values):
    for text in values:
        try: nodes = [json.loads(text)]
        except (ValueError, RecursionError): continue
        for _ in range(5000):
            if not nodes: break
            item = nodes.pop()
            if isinstance(item, dict):
                kind = item.get('@type', [])
                kinds = kind if isinstance(kind,list) else [kind]
                if any(isinstance(v,str) and v in ('Organization','http://schema.org/Organization','https://schema.org/Organization') for v in kinds): return True
                nodes.extend(item.values())
            elif isinstance(item,list): nodes.extend(item)
    return False


def bounded(call, seconds):
    queue = Queue(maxsize=1)
    def worker():
        try: queue.put((True,call()))
        except Exception as error: queue.put((False,str(error)))
    Thread(target=worker,daemon=True).start()
    try: ok, value = queue.get(timeout=max(.001,seconds))
    except Empty: raise TimeoutError('Elapsed collection budget exhausted') from None
    if not ok: raise ValueError(value)
    return value


def collect(config, fetcher=None, timeout=60):
    c = validate_config(config)
    findings, observations = [], []
    deadline = time.monotonic() + timeout
    budget = [100]
    stopped = False
    cache, errors = {}, {}
    links, edges = [], []
    omitted_pages, unknown_targets, truncated_sources = [], [], set()
    unknown_sources = {p['url'] for p in c['pages'] if p.get('check_links')}
    body_urls = {p['url'] for p in c['pages'] if p['role'] != 'excluded'} | {c.get('sitemap_url')}
    def read(url, derived=False):
        nonlocal stopped
        if url in errors: raise ValueError(errors[url])
        if url in cache: return cache[url]
        if stopped or time.monotonic() >= deadline: raise TimeoutError('Collection stopped after elapsed timeout')
        if budget[0] <= 0: raise ValueError('Request budget exhausted')
        try:
            if fetcher:
                budget[0] -= 1
                call = lambda:fetcher(url,c['origins'])
            else:
                call = lambda:fetch(url,c['origins'],budget,min(deadline,time.monotonic()+10),
                                   url in body_urls and not derived,c.get('link_prefixes') if derived else None)
            cache[url] = bounded(call,min(10,deadline-time.monotonic()))
            return cache[url]
        except Exception as error:
            errors[url] = str(error)
            if isinstance(error,TimeoutError): stopped = True
            raise
    sitemap, sitemap_error = None, None
    if c.get('sitemap_url') and any('in_sitemap' in p for p in c['pages']):
        try:
            r = read(c['sitemap_url'])
            if r['status'] != 200: raise ValueError('Sitemap HTTP status is not 200')
            if '<!DOCTYPE' in r['body'].upper(): raise ValueError('Sitemap DOCTYPE is unsupported')
            tree = ET.fromstring(r['body'])
            if tree.tag != '{http://www.sitemaps.org/schemas/sitemap/0.9}urlset':
                raise ValueError('Only namespaced urlset sitemap is supported')
            sitemap = {e.text for e in tree.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc')}
        except Exception as error: sitemap_error = str(error)
    for p in c['pages']:
        group = p.get('group',p.get('canonical') or p.get('final_url',p['url']))
        def check(rule, good, observed, severity='error', unknown=False):
            findings.append({'url':p['url'],'group':group,'rule':rule,'severity':severity,
                             'status':'unknown' if unknown else 'pass' if good else 'fail','observed':observed})
        if 'in_sitemap' in p:
            target = p.get('canonical') or p.get('final_url',p['url'])
            check('sitemap',sitemap is not None and (target in sitemap)==p['in_sitemap'],
                  sitemap_error if sitemap is None else target,'warning',unknown=sitemap is None)
        try:
            r = read(p['url'])
            r['headers'] = [(k,v) for k,v in r['headers'] if k.lower() in ('content-type','x-robots-tag')]
            observations.append({'url':p['url'],**{k:v for k,v in r.items() if k!='body'}})
        except Exception as error:
            observations.append({'url':p['url'],'error':str(error)})
            omitted_pages.append(p['url'])
            check('collection',False,str(error),unknown=True); continue
        if 'rejected_destination' in r:
            check('destination',False,r['rejected_destination'])
            check('collection',False,'Redirect target is outside allowed scope',unknown=True)
            continue
        check('http-status',r['status']==p.get('status',200),r['status'])
        check('destination',r['final_url']==p.get('final_url',p['url']),r['final_url'])
        if r['status'] == 200 and p['role'] != 'excluded':
            media = [v.split(';',1)[0].strip().lower() for k,v in r['headers'] if k.lower()=='content-type']
            if any(v not in ('text/html','application/xhtml+xml') for v in media):
                check('html-content',False,media,unknown=True)
                headers = [v for k,v in r['headers'] if k.lower()=='x-robots-tag']
                if noindex(headers): check('noindex-directive',p['role']=='nonindexable',headers)
            else:
                s = Signals(); s.feed(r['body']); s.close()
                directives = s.robots + [v for k,v in r['headers'] if k.lower()=='x-robots-tag']
                header_blocked = noindex([v for k,v in r['headers'] if k.lower()=='x-robots-tag'])
                blocked = noindex(s.robots,header=False) or header_blocked
                check('noindex-directive',blocked==(p['role']=='nonindexable'),directives,unknown=s.ambiguous and not header_blocked)
                if p.get('canonical'):
                    try:
                        base = urljoin(r['final_url'],s.base) if s.base is not None else r['final_url']
                        actual = [urljoin(base,v) if v else None for v in s.canonicals]
                        check('canonical',actual==[p['canonical']],actual,unknown=s.ambiguous)
                    except ValueError:
                        check('canonical',False,'Malformed canonical or base URL',unknown=True)
                for name in p.get('required_meta',[]):
                    check('meta:'+name,any(v.strip() for v in s.meta.get(name,[])),s.meta.get(name,[]),'warning',unknown=s.ambiguous)
                if p.get('organization'):check('organization',organization(s.jsonld),'Organization present' if organization(s.jsonld) else 'Organization absent','warning')
                if p.get('require_title'): check('title',len(s.titles)==1 and bool(s.titles[0].strip()),s.titles,unknown=s.ambiguous)
                if p.get('lang'): check('lang',[v.lower() for v in s.languages]==[p['lang'].lower()],s.languages,unknown=s.ambiguous)
                if p.get('article'): check('article',bool(''.join(s.article_text).strip()),'Non-heading article text present' if ''.join(s.article_text).strip() else 'Article text absent',unknown=s.ambiguous or bool(s.content_context))
                if p.get('check_links') and not s.ambiguous:
                    try:
                        base = urljoin(r['final_url'],s.base) if s.base is not None else r['final_url']
                        for href in s.hrefs:
                            target = urldefrag(urljoin(base,href))[0]
                            parsed = urlsplit(target)
                            if parsed.scheme not in ('http','https'): continue
                            checked_url(target)
                            if origin_id(target) not in [origin_id(o) for o in c['origins']]: continue
                            if not in_link_scope(target,c['link_prefixes']): continue
                            if len(edges)>=1000: s.truncated = True; break
                            edges.append({'source':p['url'],'href':href,'target':target})
                        if s.truncated: truncated_sources.add(p['url'])
                        else: unknown_sources.discard(p['url'])
                    except ValueError:
                        check('link-source',False,'Invalid owned link or base URL',unknown=True)
    for source in sorted(unknown_sources):
        findings.append({'url':source,'group':source,'rule':'link-source','severity':'error','status':'unknown',
                         'observed':'Source links were unavailable, ambiguous or truncated'})
    for edge in edges:
        target = edge['target']
        try:
            r = read(target,derived=True)
            if 'rejected_destination' in r or any(not in_link_scope(hop['url'],c['link_prefixes']) for hop in r['trace']) or not in_link_scope(r['final_url'],c['link_prefixes']):
                raise ValueError('Link redirect leaves configured scope')
            state = 'pass' if 200 <= r['status'] < 300 else 'fail'
            links.append({**edge,'status':state,'http_status':r['status'],'final_url':r['final_url'],'trace':r['trace']})
        except Exception as error:
            state = 'unknown'
            if target not in unknown_targets: unknown_targets.append(target)
            links.append({**edge,'status':state,'error':str(error)})
        findings.append({'url':edge['source'],'group':target,'rule':'link-target','severity':'error',
                         'status':state,'observed':links[-1]})
    groups = {}
    for f in findings:
        if f['status']=='pass': continue
        key = (f['rule'],f['group'],f['status'],f['severity'])
        groups.setdefault(key,{'rule':f['rule'],'group':f['group'],'status':f['status'],'severity':f['severity'],'urls':[]})['urls'].append(f['url'])
    counts = {state:sum(f['status']==state for f in findings) for state in ('pass','fail','unknown')}
    return {'version':1,'observed_at':datetime.now(timezone.utc).isoformat(),
            'status':'fail' if counts['fail'] else 'unknown' if counts['unknown'] else 'pass',
            'complete':not counts['unknown'],'counts':counts,'observations':observations,
            'findings':findings,'groups':list(groups.values()),'links':links,
            'coverage':{'scope':'Configured manifest and one-hop links only',
                        'manifest_sha256':hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest(),
                        'configured_pages':len(c['pages']),'observed_pages':len(observations)-len(omitted_pages),
                        'omitted_pages':omitted_pages,'requests':100-budget[0],
                        'discovered_targets':len({e['target'] for e in edges}),
                        'unknown_targets':unknown_targets,'unknown_sources':sorted(unknown_sources),
                        'truncated_sources':sorted(truncated_sources)}}


def markdown(report):
    lines = ['# Technical SEO report','',f"Status: {report['status']}; complete: {report['complete']}",'',
             '| Rule | Status | Severity | URLs |','| --- | --- | --- | --- |']
    if 'error' in report: return '\n'.join(lines[:4])+ '\nError: '+escape(report['error'])+'\n'
    for g in report['groups']:
        urls = ', '.join('<code>'+escape(u)+'</code>' for u in g['urls'])
        lines.append(f"| {escape(g['rule'])} | {g['status']} | {g['severity']} | {urls} |")
    lines.extend(['', 'Observed URLs:', ''])
    for row in report['observations']:
        lines.append('- <code>'+escape(row['url'])+'</code>: '+escape(str(row.get('status',row.get('error','unknown')))))
    c = report['coverage']
    lines.extend(['',f"Configured pages: {c['configured_pages']}; observed: {c['observed_pages']}; requests: {c['requests']}/100.",
                  'Scope: '+c['scope']+'.','', 'Link observations:', ''])
    for edge in report['links']:
        lines.append('- <code>'+escape(edge['source'])+'</code> → <code>'+escape(edge['target'])+'</code>: '+edge['status'])
    for key in ('omitted_pages','unknown_targets','unknown_sources','truncated_sources'):
        if c[key]: lines.extend(['',key+':']+['- <code>'+escape(url)+'</code>' for url in c[key]])
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--format',choices=('json','markdown'),default='json')
    args = parser.parse_args()
    try:
        with Path(args.config).open('rb') as source: raw = source.read(LIMIT+1)
        if len(raw)>LIMIT:raise ValueError('Config exceeds 1 MiB')
        report = collect(json.loads(raw.decode('utf-8-sig')))
    except (ValueError, OSError, KeyError, TypeError) as error:
        report = {'version':1, 'observed_at':datetime.now(timezone.utc).isoformat(),
                  'status':'unknown', 'complete':False, 'counts':{'pass':0,'fail':0,'unknown':1},
                  'observations':[], 'findings':[], 'groups':[], 'error':str(error)}
        print(str(error),file=sys.stderr)
    print(json.dumps(report,ensure_ascii=True,indent=2) if args.format=='json' else markdown(report),end='\n')
    return 1 if report['counts']['fail'] else 2 if report['counts']['unknown'] else 0


if __name__=='__main__': raise SystemExit(main())
