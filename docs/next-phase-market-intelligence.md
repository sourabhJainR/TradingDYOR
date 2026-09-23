# Next phase: institutional, sector and macro intelligence

TradingDYOR treats external market intelligence as evidence modules rather than hidden assumptions.

Data hierarchy:
1. SEC EDGAR for filings, Form 4 and 13F XML.
2. FRED for optional official macro history when FRED_API_KEY is configured.
3. Yahoo Finance for market and sector prices where no key is required.
4. Existing filing vocabulary for M&A, litigation, restructuring, buyback/dividend, cybersecurity and guidance.

Point-in-time rule: every observation keeps its filing or observation date and decisions must not use values unavailable at the decision timestamp.

13F limitation: 13F is manager-level reporting and the XML information table does not provide a reliable ticker field. TradingDYOR never guesses a CUSIP-to-ticker mapping; an approved identifier adapter is required before ticker-level aggregation.

The next Decision Fabric integration will choose which evidence modules to activate, verification depth and escalation based on historical evidence yield, duration and failure rate.
