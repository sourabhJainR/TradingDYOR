# Browser QA

Browser tests run in GitHub Actions against an isolated TradingDYOR API and browser process.

- `npm ci`, `npx playwright install --with-deps chromium`, then `npm run test:browser`.
- Tests use synthetic API failure injection; normal test cases consume the source registry only.
- Failure traces, screenshots and video are retained in CI artifacts for seven days.
- Manifest is bound to the exact commit SHA and workflow run ID.
- Polling helper: `GH_TOKEN=... python scripts/poll_browser_qa.py --run-id <id> --expected-sha <sha>`. It returns mismatch, timeout, failed or passed; SHA mismatch is not accepted as evidence.
- No personal browser profiles, authenticated sites, trading actions or production write access are used.
- CI browser tests are QA evidence, not independent security review or live-provider acceptance.
