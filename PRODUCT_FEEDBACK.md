# Product Feedback

## 2026-10-10

### MCP / Streamable HTTP

- Purpose: expose Billie capabilities as discoverable tools over a single HTTP JSON-RPC endpoint.
- What worked: a small JSON-RPC surface is enough to demonstrate initialization, tool discovery, and tool invocation.
- Needs improvement: a production submission should replace the minimal compatibility layer with the official SDK after dependency installation is available.
- Would build with it again: yes, because it gives a clean boundary between the conversational UI and application logic.

### Amazon Bedrock

- Purpose: natural-language explanation of deterministic findings.
- What worked: the application has a deterministic fallback explanation path.
- Needs improvement: live Bedrock calls need AWS credentials, model permissions, and SDK dependency validation.
- Would build with it again: yes, for presentation and summarization, not numerical truth or policy enforcement.

