/**
 * Find the France (FFF) Jacquemus × Nike football jersey on jacquemus.com,
 * check availability in sizes S and XXL, and report the result.
 *
 * Uses the H Computer-Use Agent platform (hai-agents SDK):
 *   - startSession()        -> returns a handle with .id IMMEDIATELY (no block)
 *                              so we can print the live agent-view link up front
 *   - handle.waitForCompletion() -> blocks until the run settles, returns the
 *                              schema-validated answer
 *
 * EU is the SDK default. Both regions use platform.hcompany.ai for Agent View.
 */
import { HaiAgentsClient } from "hai-agents";
import { z } from "zod";

// The SDK reads HAI_API_KEY from the environment; see README.md for .env setup.
if (!process.env.HAI_API_KEY) {
  console.error("Missing HAI_API_KEY. Export it in the environment; see README.md for .env setup.");
  process.exit(1);
}

// --- Region (EU is the default; flip to US by setting HAI_REGION=us) ----------
const region = (process.env.HAI_REGION ?? "eu").toLowerCase();
const client = new HaiAgentsClient(
  region === "us" ? { environment: "https://agp.hcompany.ai" } : {}, // EU default needs no override
);

// --- Typed, schema-validated result we want back from the agent ---------------
const SIZES = ["S", "XXL"] as const;

const Availability = z.object({
  productFound: z.boolean().describe("Whether the France Jacquemus x Nike jersey product page was found on jacquemus.com"),
  productName: z.string().nullable().describe("Exact product title shown on the page"),
  productUrl: z.string().nullable().describe("URL of the product page"),
  price: z.string().nullable().describe("Listed price as shown, including currency"),
  sizes: z
    .array(
      z.object({
        size: z.string().describe('Size label, e.g. "S" or "XXL"'),
        available: z.boolean().describe("True if this size can be added to the cart / is in stock"),
        note: z.string().nullable().describe('Optional detail, e.g. "Sold out" or "Low stock"'),
      }),
    )
    .describe("Availability for each requested size (S and XXL)"),
  summary: z.string().describe("One- or two-sentence plain-language summary of the findings"),
});

const task = `Go to jacquemus.com and find the France national team (FFF) football shirt / jersey from the Jacquemus x Nike collaboration.

Use the on-site search or the menu (search terms like "France", "Nike", "football", "jersey", "maillot", "FFF").
Open the correct product page for that jersey.
Then determine whether each of these sizes is available to add to the cart: ${SIZES.join(", ")}.
A size is AVAILABLE only if it can be selected and added to the bag (not greyed out / not 'Sold Out' / not 'Notify me').
Report the product name, URL, price, and the availability of each size.`;

async function main(): Promise<void> {
  // Create the session; returns immediately with an id (does NOT block).
  const handle = await client.startSession({
    agent: "h/web-surfer-pro", // visual web agent, larger model, best for a real shopping flow
    messages: task,
    answerSchema: Availability,
  });

  // Print the live agent-view link first (flushed) so the user can watch now.
  const agentViewUrl = `https://platform.hcompany.ai/agent-view/${handle.id}`;
  console.log(`\n▶ Watch live: ${agentViewUrl}`);
  console.log(`  session id: ${handle.id}\n  working… (this can take a couple of minutes)\n`);

  const result = await handle.waitForCompletion();

  console.log(`Session status: ${result.status}`);
  const answer = result.answer;
  if (result.status !== "completed" || !answer) {
    console.error("The session did not complete with a structured answer. Final text/changes:");
    console.log(JSON.stringify(result.finalChanges?.answer ?? null, null, 2));
    process.exitCode = 1;
    return;
  }

  console.log("\n================ RESULT ================");
  if (!answer.productFound) {
    console.log("❌ Could not find the France Jacquemus × Nike jersey on jacquemus.com.");
  } else {
    console.log(`Product : ${answer.productName ?? "(name not captured)"}`);
    if (answer.price) console.log(`Price   : ${answer.price}`);
    if (answer.productUrl) console.log(`URL     : ${answer.productUrl}`);
    console.log("\nRequested sizes:");
    for (const size of SIZES) {
      const found = answer.sizes.find((s) => s.size.toUpperCase() === size);
      if (!found) {
        console.log(`  • ${size.padEnd(4)} → ❓ not reported`);
      } else {
        const mark = found.available ? "✅ available" : "❌ unavailable";
        console.log(`  • ${found.size.padEnd(4)} → ${mark}${found.note ? ` (${found.note})` : ""}`);
      }
    }
  }
  console.log(`\nSummary : ${answer.summary}`);
  console.log("========================================\n");
  console.log(`Replay : ${agentViewUrl}`);
}

main().catch((err) => {
  console.error("Run failed:", err);
  process.exit(1);
});
