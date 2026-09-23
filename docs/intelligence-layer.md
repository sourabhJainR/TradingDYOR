# Intelligence layer

The research engine now has three explicit learning-safe layers:

1. Historical fundamentals are normalized with the SEC filing date as the information-availability timestamp.
2. Walk-forward strategy selection chooses a strategy from training history before each test window; test returns are never used to choose that window's strategy.
3. Experience memory records capability success, latency, evidence yield, verification depth, retries and counterfactual value so Decision Fabric can learn routing and verification policies from observed outcomes.

The SPA should treat these outputs as evidence and model diagnostics, not guarantees of future returns.
