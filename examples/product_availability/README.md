# product_availability (TypeScript)

The TypeScript counterpart to [`add_to_cart`](../add_to_cart/): drive the `hai-agents`
SDK from Node to find a product on a store's site and report its availability across
sizes. It returns a typed, `zod`-validated answer. (This demo looks up the France
Jacquemus × Nike football jersey on jacquemus.com and checks sizes **S** and **XXL**.)

Entry point: [`src/index.ts`](src/index.ts).

## Run

```bash
cd examples/product_availability
npm install
# Export the repository's .env variables (bash/zsh)
set -a
source ../../.env
set +a
npm start
```

If `HAI_API_KEY` is already exported, skip the three environment-loading commands.
`npm start` reads environment variables; it does not load `.env` itself.

Set `HAI_REGION=us` to target the US endpoint (EU is the default). Both regions use
`platform.hcompany.ai` for Agent View. The script prints the live link first, then a
per-size availability report. It exits nonzero if the session does not complete or
returns no structured answer.
