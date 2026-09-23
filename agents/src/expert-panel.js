/*
Optional Experts.js adapter.

The browser collector remains deterministic and evidence-first. Experts.js is used
as a specialist layer only after raw observations are collected. This prevents an
LLM from becoming the source of truth.
*/

export async function runExpertPanel(observation) {
  let experts;
  try {
    experts = await import("experts");
  } catch {
    return { enabled: false, reason: "Experts.js package is unavailable" };
  }

  if (!process.env.OPENAI_API_KEY) {
    return { enabled: false, reason: "OPENAI_API_KEY not configured" };
  }

  // Keep the adapter isolated because Experts.js versions expose different
  // assistant/thread APIs. Raw evidence is returned unchanged if the adapter
  // cannot be initialized.
  try {
    const { Assistant, Thread } = experts;
    const thread = await Thread.create();
    const assistant = await Assistant.create({
      name: "TradingDYOR Evidence Reviewer",
      instructions: "Review only supplied observations. Separate facts, conflicts, uncertainty and missing evidence. Never invent financial data.",
      model: process.env.EXPERTS_DEFAULT_MODEL || "gpt-4o"
    });
    const prompt = JSON.stringify({
      task: "Review this public-source observation",
      observation
    });
    const output = await assistant.ask(prompt, thread.id);
    return { enabled: true, output };
  } catch (error) {
    return { enabled: false, reason: String(error) };
  }
}
