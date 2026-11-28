# Browser QA

Browser tests run in GitHub Actions against an isolated TradingDYOR API and browser process.

- `npm install`, `npx playwright install --with-deps chromium`, then `npm run test:browser`.
- Tests use synthetic API failure injection; normal test cases consume the source registry only.
- Failure traces, screenshots and video are retained in CI artifacts for seven days.
- Manifest is bound to the exact commit SHA and workflow run ID.
- Polling helper: `GH_TOKEN=... python scripts/poll_browser_qa.py --run-id <id> --expected-sha <sha>`. The helper also checks the workflow path (`.github/workflows/browser-qa.yml` by default), normalizing GitHub's `@ref` suffix while retaining it in the receipt, so another successful workflow on the same SHA cannot be accepted as browser-QA evidence. It returns mismatch, workflow mismatch, timeout, blocked, failed or passed.
- Poll requests are bounded by the remaining deadline, and redirects are rejected.
- No personal browser profiles, authenticated sites, trading actions or production write access are used.
- CI browser tests are QA evidence, not independent security review or live-provider acceptance.
