import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
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
            with self.assertRaises(ValueError):t.fetch('https://example.com/a',['https://example.com'])

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


if __name__=='__main__':unittest.main()
