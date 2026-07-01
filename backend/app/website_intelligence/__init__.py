"""
Phase E — Website Intelligence & Semantic DOM Understanding.

A READ-ONLY, DETERMINISTIC, DOM-driven analysis package. It converts a raw DOM
snapshot into semantic UI structures (forms, tables, navigation, dialogs, an
interactive registry, locator metadata, and advisory execution hints).

NO AI / LLM / OCR / Vision / ML / embeddings. NO browser actions. NO autonomy. It
never executes anything — it only describes what is on the page. The Execution
Gateway, Planner, Playwright Adapter, Adaptive Resolver, and Recovery Engine are
UNCHANGED; Website Intelligence is purely additive enrichment.

The single point of contact with a real browser is one read-only `page.evaluate`
DOM capture (see dom_snapshot.py); every analyzer thereafter is pure Python over a
serializable DomNode tree, so it is fully testable without a browser.
"""
