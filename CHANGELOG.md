# Changelog

Only versions with a corresponding GitHub release are published releases. Dates are UTC calendar dates; translation snapshot dates are recorded separately.

## [0.3.0] - 2026-09-02

Initial public release of Codex Plugin Store Localizer.

### Included

- Local macOS launcher and experimental Windows `.cmd` launcher using a private Chromium CDP pipe.
- 15 locale codes, with an expanded Simplified Chinese catalog snapshot and 14 starter locale packs.
- September 2026 snapshot: 3,075 short-description pairs, 3,078 long-description pairs, and 12,487 plugin-text entries.
- Exact plugin-name/source-text matching, JSON schema validation, and pre-launch integrity checks.
- English and Simplified Chinese setup guides, bilingual GitHub Pages documentation, user-provided screenshots, and coverage provenance.

### Known limitations

- Windows real-device UI validation is pending. Automated tests do not prove native compatibility.
- The Windows signature check validates Authenticode status but does not pin a publisher certificate.
- macOS targets a specific signed app identity; app updates may affect compatibility. Integrity failures must not be bypassed.
- Catalog coverage is snapshot-based. New or changed strings remain untranslated. Translation quality remains open to review.
- User-provided screenshots show translated and remaining-English areas; app build/OS were not supplied. They do not prove Windows or full-catalog acceptance.

[0.3.0]: https://github.com/lwf225-source/codex-plugin-store-localizer/releases/tag/v0.3.0
