"""Keep release facts, bilingual metadata, and example text tied to source."""
import json
import hashlib
from pathlib import Path
import struct
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://lwf225-source.github.io/codex-plugin-store-localizer/"


class DocumentationTests(unittest.TestCase):
    def test_social_preview_dimensions(self):
        for filename, dimensions in (('social-preview.png', (1280, 640)), ('before-after.png', (1280, 900))):
            image = (ROOT / 'docs/assets' / filename).read_bytes()
            self.assertEqual(image[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II', image[16:24]), dimensions)
            if filename == 'social-preview.png':
                self.assertLess(len(image), 1_000_000)

    def test_original_screenshots_are_unaltered(self):
        expected = {
            'catalog-english.png': 'f3fc41bf8a67f348a762ed69d4e0111bc77f87874a17d7f4214a9929ec803f41',
            'catalog-chinese.png': '708673acceff5ba40ee483a3700f3e76e6128db9f304e173955c7fa66e8c0cf9',
            'github-detail-chinese.png': 'ff06a4d7ee5dee40e4b128974383e9980d7211fc654a16482af56571d099073c',
            'github-detail-english.png': '7acb6788cd8ccd1b6ad51444e7d86ae368cadd7471b43ed2dc9a28fa99c96780',
        }
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / 'docs/assets' / name).read_bytes()).hexdigest(), digest)
            self.assertIn(digest, (ROOT / 'docs/coverage.md').read_text())

    def test_real_screenshot_references(self):
        for page in ('index.html', 'zh-Hans/index.html', 'social-card.html', 'before-after.html'):
            html = (ROOT / 'docs' / page).read_text()
            for language in ('english', 'chinese'):
                self.assertIn(f'assets/github-detail-{language}.png', html)
            self.assertNotIn('not an app screenshot', html)
        for page in ('index.html', 'zh-Hans/index.html'):
            html = (ROOT / 'docs' / page).read_text()
            self.assertIn('<details>', html)
            self.assertIn('assets/catalog-chinese.png', html)

    def test_bilingual_metadata(self):
        for language, relative in (("en", ""), ("zh-Hans", "zh-Hans/")):
            html = (ROOT / "docs" / relative / "index.html").read_text()
            self.assertIn(f'<html lang="{language}">', html)
            self.assertIn(f'<link rel="canonical" href="{BASE}{relative}">', html)
            for alt in ("en", "zh-Hans", "x-default"):
                self.assertIn(f'hreflang="{alt}"', html)
            self.assertIn('name="description"', html)
            self.assertIn('property="og:image"', html)
            self.assertNotIn('name="robots" content="noindex"', html)
            self.assertEqual(html.count("<h1>"), 1)
            data = json.loads(html.split('<script type="application/ld+json">')[1].split('</script>')[0])
            self.assertEqual(data['softwareVersion'], '0.3.0')
            self.assertNotIn('aggregateRating', data)

    def test_dictionary_examples_are_verbatim(self):
        dictionary = json.loads((ROOT / "assets/dom-translations.zh-Hans.json").read_text())
        chosen = [item for item in dictionary['plugin_descriptions'] if item['display_name'] in ('Gmail', 'Notion', 'Slack')]
        self.assertEqual(len(chosen), 3)
        for file in ('examples.html',):
            text = (ROOT / "docs" / file).read_text()
            for item in chosen:
                self.assertIn(item['source_short'][0], text)
                self.assertIn(item['target_short'], text)
            self.assertIn('not an app screenshot', text)

    def test_facts_and_readme_links(self):
        coverage = json.loads((ROOT / 'assets/catalog-coverage.zh-Hans.json').read_text())
        text = (ROOT / 'docs/coverage.md').read_text()
        self.assertIn(coverage['catalog_fetched_at'], text)
        for key in ('plugin_descriptions','plugin_details','plugin_texts'):
            self.assertIn(f"{coverage['counts'][key]:,}", text)
        for readme, other in (('README.md', 'README.zh-Hans.md'), ('README.zh-Hans.md','README.md')):
            content = (ROOT / readme).read_text()
            self.assertIn(f']({other})', content)
            self.assertIn('docs/assets/before-after.png', content)
        ET.parse(ROOT / 'docs/sitemap.xml')


if __name__ == '__main__':
    unittest.main()
