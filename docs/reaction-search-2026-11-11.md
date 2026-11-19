# Reaction search in Web

First delivery for [nettrash/family.connect#116](https://github.com/nettrash/family.connect/issues/116): Web and shared search data. Native client pickers are follow-up work under that issue.

The extended reaction picker now has a fixed search field, recent choices, a scrollable categorised grid and category shortcuts. On narrow screens it is a bottom panel. Searching covers the whole catalogue, not the section currently in view. Clearing restores the catalogue; Escape closes the picker and returns focus to the message's actions button. The existing modal supplies the focus loop.

Search uses CLDR names and keywords in the browser's interface language, English names/keywords and the existing English shortcode aliases. Case, surrounding whitespace, colons, underscores and hyphens are normalised. Multiword queries require every word to match. Exact names and aliases rank first, then name prefixes, then keyword matches, with catalogue order breaking ties. Each result is offered once and sends the exact existing catalogue Unicode sequence. This is keyword search, not an AI service.

The catalogue has 771 positions and 769 unique emoji. `tools/emoji/make_search.py` generates search data for all nine interface languages from Unicode CLDR 49 commit `96e54b273d2da4ec6fbad350ba19ff23fa24a588`. Every input is checked against `tools/emoji/cldr-search-sources.sha256`. Serbian Latin has its own CLDR annotations, and `zh-Hans` uses the CLDR `zh` annotations. The Web build includes the Unicode-3.0 license.

The Wasm bundle contains English data from `web/text/data/emoji-search.tsv` and the existing shortcode aliases. Trunk copies the other eight language files from `web/emoji-search/` into the Web distribution. Opening the picker in a non-English locale requests only that locale's versioned TSV. English search stays available while the file loads. When it arrives, the picker updates the current results and accessible names. The page reuses successfully loaded data, and reopening the picker can retry a failed load. Shortcode replacement while typing is unchanged.

Recent choices are local to an account and browser origin, newest first, deduplicated and limited to 24 catalogue entries. A deliberate selection is remembered immediately, including an optimistic selection whose server request might later fail. Opening or searching the picker and other members' reactions do not change recents. Malformed stored data is ignored, invalid entries are removed, and logout clears reaction-recents keys along with the existing personal sticker/played state. No new API or database migration is needed.

## Regeneration

```bash
python3 tools/emoji/make_search.py
python3 tools/emoji/make_search.py --check
```

Both commands download the ten pinned inputs. For offline regeneration/checking, provide a CLDR source directory containing `LICENSE` and `common/annotations/{en,de,es,fr,ja,ru,sr,sr_Latn,zh}.xml`:

```bash
python3 tools/emoji/make_search.py --source-dir /path/to/cldr-49 --check
```

## Verification

Use the repository's Rust and browser test commands:

```bash
(cd web/text && cargo test)
(cd web && wasm-pack test --headless --chrome)
```

The shared tests cover locale and English fallback ranking, aliases, catalogue coverage, Unicode sequences, invalid data, and recent choices. The browser tests also verify the language request, English fallback, retry, and reuse after reopening the picker.
