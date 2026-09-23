# Evidence Fabric

The Evidence Fabric is the provenance layer between public data and decisions.

It deduplicates evidence, retains source and availability timestamps, scores confidence/relevance, and exposes coverage by evidence type.

Decision Fabric then uses historical experience to select evidence capabilities, verification depth, retry budget and counterfactual branch budget. It is deliberately conservative when history is sparse.

External sources used by the implementation include SEC EDGAR, FRED and PatentsView. APIs that require credentials are optional and degrade to explicit not-configured states rather than silently fabricating data.
