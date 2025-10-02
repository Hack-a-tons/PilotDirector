import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { LlamaIndexAgent } from "@ag-ui/llamaindex";

import { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  // Extract user ID from headers
  const userId = request.headers.get('x-user-id') || 'default';
 
  const runtime = new CopilotRuntime({
    agents: {
      sample_agent: new LlamaIndexAgent({
        url: "http://127.0.0.1:9000/run",
        // Pass user context to the agent
        headers: {
          'x-user-id': userId
        }
      })
    }
  })

  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter: new ExperimentalEmptyAdapter(),
    endpoint: `/api/copilotkit`,
  });

  return handleRequest(request);
}
