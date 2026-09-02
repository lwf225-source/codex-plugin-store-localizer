# Translation coverage and evidence

Last documented: **2026-09-02**. These facts describe the bundled v0.3.0 snapshot, not the ever-changing live catalog.

## Reproducible snapshot

- Catalog fetched at: **2026-09-01T15:31:18.802229Z** (UTC).
- Short-description entries: **3,075**.
- Long-description entries: **3,078**.
- Other plugin-text entries: **12,487**.
- Host strings: **20**.
- Catalog records in the coverage manifest: **3,087**.
- Canonical dictionary SHA-256: `8d8d027c4c4f324eb9a5edf0a1a3c1d3e1b90b55833b428536e1279bbc6cbf81`.

Sources: [dictionary](../assets/dom-translations.zh-Hans.json), [coverage manifest](../assets/catalog-coverage.zh-Hans.json), [locale packs](../assets/locale-packs.json), and [coverage tests](../tests/test_full_coverage.py). The dictionary digest uses the canonical JSON calculation in `runtime_common.dictionary_sha256`, not the file's raw bytes.

Counts are entries/pairs, not unique plugins. A later catalog can contain new or changed strings absent from this pack. Exact matching intentionally leaves those strings in English. Schema and count validation do not constitute native-language review of every translation.

## Platform verification boundary

Python and Node automated tests exercise data validation, launcher paths, and injector behavior. The current CI environment is Ubuntu with Python 3.11 and Node.js 22. These tests do not launch the official macOS or Windows desktop app.

Windows real-device UI acceptance is **pending**. Its Authenticode validation does not pin a publisher. macOS requires the expected signed identity and full app integrity. An earlier agent-run macOS launch attempt was blocked by app integrity validation. The subsequently supplied user screenshots show translated content, but do not establish that the blocked attempt later succeeded; no guard was bypassed.

To verify your own compatible build, use the launcher, enter the plugin directory, and inspect real text plus fresh status: `launcher_running=true`, `state=active`, and `translated_nodes>0`. Historical status alone is not sufficient.

## Image provenance

The user supplied four real screenshots on **2026-09-02**. This is the receipt date, not a verified capture timestamp. Original pixels and files are preserved byte-for-byte in `docs/assets/`; no UI text has been repainted, translated into the image, or removed.

| File | Source attachment | Visible evidence |
| --- | --- | --- |
| `catalog-english.png` | Image 1 | English descriptions in Popular / New sections |
| `catalog-chinese.png` | Image 2 | Chinese descriptions in Productivity / Creative sections |
| `github-detail-chinese.png` | Image 3 | Chinese GitHub short description, suggested prompts and overview |
| `github-detail-english.png` | Image 4 | The corresponding GitHub detail content in English |

Images 4 and 3 form the matched detail-page comparison. Their viewport framing differs; display them proportionally without cropping. Images 1 and 2 show different catalog sections and must not be presented as the same section before/after.

The GitHub connector descriptions near the bottom of Image 3 remain English. The supplied screenshots do not establish all-string coverage, the capture OS, app version, or Windows acceptance. They are user-supplied visual evidence, not a new agent-run acceptance test. Visible prompt suggestions in the screenshots are documentation content, not instructions to execute.

Raw-file SHA-256 values:

```text
f3fc41bf8a67f348a762ed69d4e0111bc77f87874a17d7f4214a9929ec803f41  catalog-english.png
708673acceff5ba40ee483a3700f3e76e6128db9f304e173955c7fa66e8c0cf9  catalog-chinese.png
ff06a4d7ee5dee40e4b128974383e9980d7211fc654a16482af56571d099073c  github-detail-chinese.png
7acb6788cd8ccd1b6ad51444e7d86ae368cadd7471b43ed2dc9a28fa99c96780  github-detail-english.png
```

`before-after.png` and `social-preview.png` are browser captures of HTML layouts embedding these unaltered originals. Capture [the comparison layout](before-after.html) at **1280 × 900** and [the social card](social-card.html) at **1280 × 640**. Labels are outside the supplied screenshots. Full-resolution originals are linked from both READMEs and the landing pages.

The earlier [dictionary example layout](examples.html) and `translation-examples.png` remain supplementary illustrations only; they are no longer used as the primary screenshot or social preview.

## 中文口径

数字对应 2026 年 9 月 1 日 UTC 的随包快照，不是实时目录总量。2026 年 9 月 2 日收到用户提供的四张真实截图：第 4 / 3 张用于同一 GitHub 详情页的英文 / 中文对照；第 1 / 2 张为不同目录区域。截图保留原始像素，连接器区域仍有英文。未提供系统和应用版本，Windows 仍待实机验收；不要从局部截图推导全量覆盖。
