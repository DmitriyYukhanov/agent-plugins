import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import json
import subprocess
import sys
import time

PATH = Path(__file__).parents[1] / 'skills/seo-pulse/scripts/technical.py'
spec = importlib.util.spec_from_file_location('technical', PATH)
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


def config(**changes):
    page = dict(url='https://example.com/privacy', role='public', canonical='https://example.com/privacy')
    page.update(changes)
    return {'technical': {'origins': ['https://example.com', 'http://example.com'], 'pages': [page]}}


def response(body='<head><link rel="canonical" href="https://example.com/privacy"></head>', **changes):
    value = dict(status=200, final_url='https://example.com/privacy', trace=[], headers=[], body=body)
    value.update(changes)
    return value


class TechnicalTests(unittest.TestCase):
    def report(self, cfg=None, value=None):
        return t.collect(cfg or config(), lambda u, o: value or response())

    def test_healthy_without_gsc(self):
        self.assertEqual(self.report()['status'], 'pass')

    def test_bad_canonical_variants(self):
        for body in ['<head></head>', '<head><link rel="canonical" href="/wrong"></head>', '<head><link rel="canonical" href="/privacy"><link rel="canonical" href="/privacy"></head>']:
            with self.subTest(body=body):
                self.assertEqual(self.report(value=response(body))['status'], 'fail')

    def test_alias_200_fails_and_redirect_passes(self):
        cfg = config(url='http://example.com/privacy', final_url='https://example.com/privacy')
        self.assertEqual(self.report(cfg, response(final_url='http://example.com/privacy'))['status'], 'fail')
        self.assertEqual(self.report(cfg)['status'], 'pass')

    def test_login_and_showcase(self):
        cfg = config(role='nonindexable'); cfg['technical']['pages'][0].pop('canonical')
        self.assertEqual(self.report(cfg, response('<head></head>'))['status'], 'fail')
        self.assertEqual(self.report(cfg, response('<head><meta name="robots" content="noindex"></head>'))['status'], 'pass')

    def test_header_scope(self):
        self.assertTrue(t.noindex(['googlebot: noindex']))
        self.assertTrue(t.noindex(['noindex']))
        self.assertFalse(t.noindex(['otherbot: noindex, nofollow']))
        self.assertFalse(t.noindex(['unavailable_after: 01 Jan 2030']))

    def test_html_head_and_templates(self):
        for body in ['<body><link rel="canonical" href="https://example.com/privacy">', '<head><template><link rel="canonical" href="https://example.com/privacy"></template></head>', '<head><script>"<link rel=canonical href=https://example.com/privacy>"</script></head>']:
            self.assertEqual(self.report(value=response(body))['status'], 'fail')

    def test_relative_canonical(self):
        self.assertEqual(self.report(value=response('<head><link rel="CANONICAL" href="/privacy"></head>'))['status'], 'pass')

    def test_optional_metadata(self):
        self.assertEqual(self.report()['status'], 'pass')
        self.assertEqual(self.report(config(required_meta=['description']))['status'], 'fail')
        self.assertEqual(self.report(config(organization=True))['status'], 'fail')

    def test_organization_and_metadata(self):
        body='<head><link rel="canonical" href="/privacy"><meta name="description" content="Policy"><meta property="og:title" content="Policy"></head><script type="application/ld+json">{"@graph":[{"@type":"Organization"}]}</script>'
        self.assertEqual(self.report(config(required_meta=['description','og:title'], organization=True), response(body))['status'], 'pass')

    def test_collection_error_is_unknown(self):
        def fail(u, o): raise OSError('TLS unavailable')
        r=t.collect(config(), fail)
        self.assertEqual(r['status'], 'unknown')
        self.assertFalse(any(x['status']=='fail' for x in r['findings']))

    def test_expected_404(self):
        self.assertEqual(self.report(config(role='excluded', canonical=None, status=404), response(status=404, body=''))['status'], 'pass')

    def test_sitemap_missing_and_unavailable(self):
        cfg=config(in_sitemap=True);cfg['technical']['sitemap_url']='https://example.com/sitemap.xml'
        def fetch(u,o):return response('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>') if u.endswith('.xml') else response()
        self.assertEqual(t.collect(cfg,fetch)['status'],'fail')
        def fail(u,o):
            if u.endswith('.xml'):raise OSError('timeout')
            return response()
        r=t.collect(cfg,fail)
        self.assertEqual(r['status'],'unknown')
        self.assertFalse(any(x['rule']=='sitemap' and x['status']=='fail' for x in r['findings']))

    def test_grouping_preserves_raw_urls(self):
        cfg=config();p=cfg['technical']['pages'][0];p['group']='privacy';q=dict(p,url='http://example.com/privacy');cfg['technical']['pages'].append(q)
        r=t.collect(cfg,lambda u,o:response('<head></head>',final_url=u))
        groups=[g for g in r['groups'] if g['rule']=='canonical']
        self.assertEqual(len(groups),1);self.assertEqual(len(groups[0]['urls']),2)

    def test_validation_before_network(self):
        for url in ['file:///etc/passwd','http://127.0.0.1/a','https://user:pass@example.com/','https://example.com/%2e%2e/a','https://example.com/a#b','https://example.com/\\x']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                t.collect(config(url=url),lambda u,o:self.fail('network used'))

    def test_scope_and_encoded_query(self):
        raw='https://example.com/login?next=%2Fcheckout%3Foffer%3Dlifetime'
        self.assertEqual(t.checked_url(raw,['https://example.com']),raw)
        with self.assertRaises(ValueError):t.checked_url('https://evil.example/a',['https://example.com'])

    def test_transport_rejects_escape_before_request(self):
        class Reply:
            code=302;headers={'Location':'https://evil.example/'}
            def close(self):pass
        class Opener:
            def open(self,*a,**k):return Reply()
        with patch.object(t,'build_opener',return_value=Opener()),patch.object(t,'public_host'):
            self.assertEqual(t.fetch('https://example.com/a',['https://example.com'])['rejected_destination'], 'https://evil.example/')

    def test_request_timeout_does_not_skip_later_pages(self):
        cfg=config()
        later='https://example.com/later'
        cfg['technical']['pages'].append(dict(url=later,role='public',canonical=later))
        requested=[]
        def fetcher(url,origins):
            requested.append(url)
            return response(f'<link rel="canonical" href="{url}">',final_url=url)
        def bounded_once(call,seconds):
            if bound.call_count==1: raise TimeoutError('Request timed out')
            return call()
        with patch.object(t,'bounded',side_effect=bounded_once) as bound:
            r=t.collect(cfg,fetcher)
        self.assertEqual(requested,[later])
        self.assertEqual(r['coverage']['omitted_pages'],['https://example.com/privacy'])
        self.assertEqual(r['observations'][1]['status'],200)
        self.assertEqual(r['counts']['unknown'],1)

    def test_elapsed_budget_stops_scan(self):
        cfg=config();cfg['technical']['pages'].append(dict(cfg['technical']['pages'][0],url='https://example.com/other'))
        calls=[]
        def slow(u,o):calls.append(u);time.sleep(.15);return response()
        r=t.collect(cfg,slow,timeout=.02)
        self.assertEqual(r['status'],'unknown');self.assertEqual(len(calls),1)

    def test_noindex_requires_complete_tokens(self):
        self.assertFalse(t.noindex(['not-noindex']))
        self.assertFalse(t.noindex(['none-ish']))

    def test_parameterized_noindex(self):
        self.assertTrue(t.noindex(['max-snippet:0, noindex']))
        self.assertTrue(t.noindex(['googlebot: max-snippet:0, noindex']))
        r=self.report(value=response('<head><link rel="canonical" href="/privacy"><meta name="robots" content="max-snippet:0, noindex"></head>'))
        self.assertEqual(r['status'],'fail')

    def test_report_discards_cookies_and_private_headers(self):
        r=self.report(value=response(headers=[('Set-Cookie','session=opaque'),('Authorization','secret'),('X-Robots-Tag','index')]))
        self.assertNotIn('opaque',str(r));self.assertNotIn('secret',str(r))
        self.assertIn('X-Robots-Tag',str(r))

    def test_head_cannot_reopen_after_body(self):
        for body in ['<a>Hello</a><link rel="canonical" href="/privacy">','<body><head><link rel="canonical" href="/privacy"></head>']:
            self.assertEqual(self.report(value=response(body))['status'],'fail')

    def test_ambiguous_robots_never_passes(self):
        for role in ['public','nonindexable']:
            cfg=config(role=role)
            if role=='nonindexable':cfg['technical']['pages'][0].pop('canonical')
            r=self.report(cfg,response('<head><link rel="canonical" href="/privacy"><meta name="robots" content="noindex" content="index"></head>'))
            self.assertNotEqual(r['status'],'pass')

    def test_valueless_attributes_do_not_abort_report(self):
        for bad in ['<link rel>','<meta name>','<script type></script>']:
            body='<head>'+bad+'<link rel="canonical" href="/privacy"></head>'
            self.assertEqual(self.report(value=response(body))['status'],'pass')

    def test_plain_body_text_and_title_are_not_canonical(self):
        for body in ['Visible text<link rel="canonical" href="/privacy">','<title><link rel="canonical" href="/privacy"></title>']:
            self.assertEqual(self.report(value=response(body))['status'],'fail')
        body='<title>Valid title text</title><link rel="canonical" href="/privacy">'
        self.assertEqual(self.report(value=response(body))['status'],'pass')

    def test_first_base_controls_relative_canonical(self):
        body='<head><base href="https://other.example/"><link rel="canonical" href="/privacy"></head>'
        self.assertEqual(self.report(value=response(body))['status'],'fail')

    def test_deadline_after_dns_prevents_request(self):
        with patch.object(t,'public_host',side_effect=lambda u:time.sleep(.03)), patch.object(t,'build_opener') as opener:
            with self.assertRaises(TimeoutError):t.fetch('https://example.com/privacy',['https://example.com'],deadline=time.monotonic()+.01)
            opener.return_value.open.assert_not_called()

    def test_markdown_failure_rows_stay_in_table(self):
        r=self.report(value=response('<head></head>'))
        lines=t.markdown(r).splitlines();at=lines.index('| --- | --- | --- | --- |')
        self.assertTrue(lines[at+1].startswith('| canonical |'))

    def test_malformed_html_urls_do_not_abort_later_pages(self):
        for body in ['<head><base href="https://["><link rel="canonical" href="/privacy"></head>','<head><link rel="canonical" href="https://["></head>']:
            cfg=config();cfg['technical']['pages'].append(dict(cfg['technical']['pages'][0],url='https://example.com/other'))
            r=t.collect(cfg,lambda u,o:response(body if u.endswith('privacy') else '<head><link rel="canonical" href="/privacy"></head>',final_url=u))
            self.assertEqual(len(r['observations']),2)
            self.assertEqual(r['status'],'unknown')

    def test_explicit_non_html_is_not_healthy_html(self):
        r=self.report(value=response(headers=[('Content-Type','application/json')]))
        self.assertEqual(r['status'],'unknown');self.assertFalse(r['complete'])

    def test_non_html_preserves_header_failure(self):
        r=self.report(value=response(headers=[('Content-Type','application/json'),('X-Robots-Tag','noindex')]))
        self.assertEqual(r['status'],'fail');self.assertFalse(r['complete'])

    def test_body_robots_directive_is_applicable(self):
        body='<head><link rel="canonical" href="/privacy"></head><body><meta name="robots" content="noindex"></body>'
        self.assertEqual(self.report(value=response(body))['status'],'fail')
        cfg=config(role='nonindexable');cfg['technical']['pages'][0].pop('canonical')
        self.assertEqual(self.report(cfg,response(body))['status'],'pass')

    def test_markdown_escapes(self):
        r=self.report();text=t.markdown(r)
        self.assertIn('Technical SEO report',text)
        self.assertIn('example.com',text)

    def test_invalid_config_still_emits_report(self):
        r = subprocess.run([sys.executable, str(PATH), '--config', str(PATH / 'absent')], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertFalse(json.loads(r.stdout)['complete'])

    def test_status_only_skips_unreadable_body(self):
        class Reply:
            code = 404
            headers = {'Content-Encoding': 'gzip'}
            def close(self): pass
            def read(self, *args): raise OSError('Body must not be read')
        with patch.object(t, 'build_opener') as opener, patch.object(t, 'public_host'):
            opener.return_value.open.return_value = Reply()
            self.assertEqual(t.collect(config(role='excluded', canonical=None, status=404))['status'], 'pass')

    def test_public_http_failure_survives_unreadable_error_body(self):
        class Reply:
            headers = {}
            def close(self): pass
            def read(self, *args): raise OSError('Unreadable error body')
        for status in (404,503):
            reply = Reply(); reply.code = status
            with self.subTest(status=status), patch.object(t,'build_opener') as opener, patch.object(t,'public_host'):
                opener.return_value.open.return_value = reply
                r = t.collect(config())
                self.assertTrue(any(f['rule']=='http-status' and f['status']=='fail' for f in r['findings']))

    def test_organization_iri_types(self):
        for kind in ['https://schema.org/Organization', ['Thing', 'http://schema.org/Organization']]:
            self.assertTrue(t.organization([json.dumps({'@type': kind})]))
        self.assertFalse(t.organization(['{"@type": [{"bad": "type"}]}']))

    def test_unused_sitemap_is_not_requested(self):
        cfg = config(); cfg['technical']['sitemap_url'] = 'https://example.com/sitemap.xml'
        calls = []
        def get(u, o):
            calls.append(u)
            return response()
        self.assertEqual(t.collect(cfg, get)['status'], 'pass')
        self.assertNotIn(cfg['technical']['sitemap_url'], calls)

    def test_sitemap_doctype_is_unknown(self):
        cfg = config(in_sitemap=True); cfg['technical']['sitemap_url'] = 'https://example.com/sitemap.xml'
        xml = '<!DOCTYPE urlset [<!ENTITY page "https://example.com/privacy">]><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>&page;</loc></url></urlset>'
        r = t.collect(cfg, lambda u,o: response(xml) if u.endswith('.xml') else response())
        self.assertEqual(r['status'], 'unknown')

    def test_foreign_sitemap_children_do_not_satisfy_membership(self):
        cfg = config(in_sitemap=True); cfg['technical']['sitemap_url'] = 'https://example.com/sitemap.xml'
        xml = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url xmlns="urn:foreign"><loc>https://example.com/privacy</loc></url></urlset>'
        r = t.collect(cfg, lambda u,o: response(xml) if u.endswith('.xml') else response())
        self.assertEqual(r['status'], 'fail')

    def test_rejected_redirect_preserves_destination_failure(self):
        class Reply:
            code = 302
            headers = {'Location': 'https://other.example/moved'}
            def close(self): pass
        with patch.object(t, 'build_opener') as opener, patch.object(t, 'public_host'):
            opener.return_value.open.return_value = Reply()
            r = t.collect(config())
            opener.return_value.open.assert_called_once()
        self.assertTrue(any(f['rule']=='destination' and f['status']=='fail' for f in r['findings']))
        self.assertFalse(r['complete'])
        self.assertIn('https://other.example/moved', str(r))

    def test_sitemap_failure_survives_page_collection_error(self):
        cfg = config(in_sitemap=True); cfg['technical']['sitemap_url'] = 'https://example.com/sitemap.xml'
        def get(u, o):
            if u.endswith('.xml'): return response('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>')
            raise OSError('TLS error')
        r = t.collect(cfg, get)
        self.assertEqual(r['status'], 'fail')
        self.assertFalse(r['complete'])

    def test_header_noindex_survives_ambiguous_html(self):
        r = self.report(value=response('<meta name="description" name="other">', headers=[('X-Robots-Tag', 'noindex')]))
        self.assertTrue(any(f['rule']=='noindex-directive' and f['status']=='fail' for f in r['findings']))

    def test_public_article_title_and_language(self):
        cfg = config(require_title=True, article=True, lang='en')
        empty = '<html><head><title> </title><link rel="canonical" href="/privacy"></head><body><nav>Site menu</nav><article><h1>Heading</h1><nav><a>Menu</a></nav><script>text</script></article></body></html>'
        r = self.report(cfg, response(empty))
        self.assertEqual({f['rule'] for f in r['findings'] if f['status']=='fail'}, {'title','article','lang'})
        short = '<html lang="EN"><head><title>API</title><link rel="canonical" href="/privacy"></head><body><article><h1>API</h1><pre>int Count;</pre></article></body></html>'
        self.assertEqual(self.report(cfg, response(short))['status'], 'pass')
        self.assertEqual(self.report(cfg, response(short.replace('EN','en-US')))['status'], 'fail')

    def test_intentional_content_exceptions_and_strict_flags(self):
        self.assertEqual(self.report()['status'], 'pass')
        for changes in [dict(role='nonindexable',article=True), dict(require_title='yes'), dict(lang=True), dict(check_links=True)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError): t.validate_config(config(**changes))

    def link_config(self, hrefs):
        cfg = config(check_links=True)
        cfg['technical']['link_prefixes'] = ['https://example.com/docs/']
        body = '<head><link rel="canonical" href="/privacy"></head><body>' + ''.join('<a href="'+h+'">Namespace</a>' for h in hrefs)
        return cfg, response(body)

    def test_source_page_reveals_missing_namespace_without_enumerated_target(self):
        for product in ['toolkit','inspector']:
            target = 'https://example.com/docs/'+product+'/api/Parent.html'
            cfg, source = self.link_config([target+'#namespace', target+'#other'])
            calls = []
            def get(u,o):
                calls.append(u)
                return source if u.endswith('/privacy') else response(status=404,final_url=u)
            r = t.collect(cfg,get)
            self.assertEqual(r['status'], 'fail')
            self.assertEqual(calls.count(target), 1)
            edge = r['links'][0]
            self.assertEqual(edge['source'], 'https://example.com/privacy')
            self.assertEqual(edge['target'], target)
            self.assertEqual(edge['href'], target+'#namespace')

    def test_links_preserve_queries_skip_external_and_do_not_recurse(self):
        hrefs = ['/docs/api.html?next=%2Fother%3Fx%3D1#part','/docs/api.html?next=%2Fother%3Fx%3D2','https://external.example/docs/a','/docs-other/a','/user/alice/a']
        cfg, source = self.link_config(hrefs)
        calls = []
        def get(u,o):
            calls.append(u)
            return source if u.endswith('/privacy') else response('<a href="/docs/deeper.html">next</a>',final_url=u)
        r = t.collect(cfg,get)
        self.assertEqual(r['status'],'pass')
        self.assertEqual(calls, ['https://example.com/privacy']+['https://example.com'+h.split('#')[0] for h in hrefs[:2]])

    def test_link_error_and_uncollected_source_are_unknown(self):
        cfg, source = self.link_config(['/docs/missing'])
        def get(u,o):
            if u.endswith('/privacy'): return source
            raise OSError('TLS error')
        r=t.collect(cfg,get)
        self.assertEqual(r['status'],'unknown'); self.assertFalse(r['complete'])
        self.assertEqual(r['coverage']['unknown_targets'], ['https://example.com/docs/missing'])
        r=t.collect(cfg,lambda u,o: (_ for _ in ()).throw(OSError('TLS error')))
        self.assertIn('https://example.com/privacy', r['coverage']['unknown_sources'])

    def test_large_manifest_never_silently_certifies_omissions(self):
        cfg=config(role='excluded',canonical=None)
        cfg['technical']['pages']=[dict(url='https://example.com/docs/'+str(i),role='excluded') for i in range(325)]
        calls=[]
        class Reply:
            code=200;headers={}
            def close(self):pass
        class Opener:
            def open(self,request,**kwargs):calls.append(request.full_url);return Reply()
        with patch.object(t,'build_opener',return_value=Opener()),patch.object(t,'public_host') as dns:
            r=t.collect(cfg)
        self.assertEqual(len(calls),100);self.assertEqual(dns.call_count,100)
        self.assertEqual(r['coverage']['configured_pages'],325)
        self.assertEqual(len(r['coverage']['omitted_pages']),225)
        self.assertFalse(r['complete']);self.assertEqual(r['status'],'unknown')

    def test_derived_link_redirect_cannot_enter_user_content(self):
        cfg, source=self.link_config(['/docs/start'])
        class Reply:
            code=302;headers={'Location':'https://example.com/user/alice'}
            def close(self):pass
        with patch.object(t,'build_opener') as opener,patch.object(t,'public_host'):
            opener.return_value.open.return_value=Reply()
            transport=lambda u,o: source if u.endswith('/privacy') else t.fetch(u,o,read_body=False,link_prefixes=cfg['technical']['link_prefixes'])
            r=t.collect(cfg,transport)
        opener.return_value.open.assert_called_once()
        self.assertFalse(r['complete']);self.assertEqual(r['links'][0]['status'],'unknown')

    def test_link_truncation_is_unknown(self):
        cfg,source=self.link_config(['/docs/'+str(i) for i in range(1100)])
        r=t.collect(cfg,lambda u,o:source if u.endswith('/privacy') else response(final_url=u))
        self.assertFalse(r['complete'])
        self.assertIn('https://example.com/privacy',r['coverage']['truncated_sources'])

    def test_directory_index_alias_uses_explicit_canonical(self):
        cfg=config(url='https://example.com/docs/',canonical='https://example.com/docs/index.html')
        cfg['technical']['pages'].append(dict(cfg['technical']['pages'][0],url='https://example.com/docs/index.html'))
        self.assertEqual(t.collect(cfg,lambda u,o:response('<link rel="canonical" href="/docs/index.html">',final_url=u))['status'],'pass')

    def test_markdown_explains_link_target_and_omitted_scope(self):
        cfg,source=self.link_config(['/docs/Parent.html'])
        r=t.collect(cfg,lambda u,o:source if u.endswith('/privacy') else response(status=404,final_url=u))
        text=t.markdown(r)
        self.assertIn('https://example.com/docs/Parent.html',text)
        self.assertIn('Configured pages: 1',text)

    def test_expected_404_does_not_excuse_incoming_link(self):
        cfg,source=self.link_config(['/docs/reserved'])
        cfg['technical']['pages'].append(dict(url='https://example.com/docs/reserved',role='excluded',status=404))
        r=t.collect(cfg,lambda u,o:source if u.endswith('/privacy') else response(status=404,final_url=u))
        self.assertEqual(r['links'][0]['status'],'fail')

    def test_first_base_and_encoded_paths_keep_original_evidence(self):
        cfg,source=self.link_config(['Parent%2Ehtml?x=%2F#namespace'])
        source['body']=source['body'].replace('<head>','<head><base href="/docs/api/">')
        calls=[]
        def get(u,o):
            calls.append(u)
            return source if u.endswith('/privacy') else response(final_url=u)
        r=t.collect(cfg,get)
        self.assertEqual(calls[-1],'https://example.com/docs/api/Parent%2Ehtml?x=%2F')
        self.assertEqual(r['status'],'pass')

    def test_encoded_link_path_escape_is_not_requested(self):
        cfg,source=self.link_config(['/docs/%2fuser/alice'])
        calls=[]
        def get(u,o):calls.append(u);return source
        r=t.collect(cfg,get)
        self.assertEqual(calls,['https://example.com/privacy'])
        self.assertFalse(r['complete'])

    def test_ambiguous_language_and_unclosed_article_do_not_pass(self):
        cfg=config(lang='en',article=True)
        body='<html lang="en" lang="ru"><head><link rel="canonical" href="/privacy"></head><body><article>Definition'
        r=self.report(cfg,response(body))
        self.assertEqual(r['status'],'unknown')

    def test_equivalent_owned_origins_cannot_hide_broken_links(self):
        for target in ['https://EXAMPLE.com/docs/missing','https://example.com:443/docs/missing']:
            cfg,source=self.link_config([target])
            calls=[]
            def get(u,o):calls.append(u);return source if u.endswith('/privacy') else response(status=404,final_url=u)
            r=t.collect(cfg,get)
            self.assertEqual(r['status'],'fail')
            self.assertIn(target,calls)
            self.assertEqual(r['links'][0]['target'],target)

    def test_equivalent_origin_transport_preserves_raw_url(self):
        target='https://EXAMPLE.com:443/docs/api.html?next=%2Fvalue'
        class Reply:
            code=404;headers={}
            def close(self):pass
        with patch.object(t,'build_opener') as opener,patch.object(t,'public_host'):
            opener.return_value.open.return_value=Reply()
            r=t.fetch(target,['https://example.com'],read_body=False,link_prefixes=['https://example.com/docs/'])
            self.assertEqual(r['status'],404)
            self.assertEqual(opener.return_value.open.call_args.args[0].full_url,target)


if __name__=='__main__':unittest.main()
