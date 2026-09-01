# Contributing

Thanks for helping improve Codex Plugin Store Localizer.

## Before opening a pull request

1. Keep the launcher local-first. Do not add telemetry, remote runtime calls, or network debugging endpoints.
2. Translation packs must remain JSON data only. Never embed JavaScript or HTML.
3. Preserve exact source matching: a translation must be tied to the displayed plugin name and the original English text.
4. Do not change the official app bundle, executable, catalog cache, or plugin source as part of the runtime flow.
5. Run both test suites:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/test_injector.mjs
```

## Translation changes

- Use the correct locale code and keep the JSON schema valid.
- Prefer clear product terminology over literal word-for-word translations.
- Add a regression test for a new matching rule or a layout-sensitive language such as Arabic.
- Do not claim full-catalog coverage for a locale unless every required catalog pair is audited.

## Pull request checklist

- [ ] Tests pass locally.
- [ ] No secrets, account data, logs, or local status files are included.
- [ ] Security boundaries remain fail-closed.
- [ ] README wording still reflects actual locale coverage.
