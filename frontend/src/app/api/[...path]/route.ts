import { NextRequest, NextResponse } from "next/server";

/**
 * Catch-all API proxy — forwards /api/* requests to the backend.
 * Uses server-side BACKEND_URL env var (not NEXT_PUBLIC_*).
 */
const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";

async function proxyRequest(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await context.params;
    const pathStr = path.join("/");
    const url = `${BACKEND}/api/${pathStr}`;

    const headers: Record<string, string> = {};

    // Forward content-type
    const ct = request.headers.get("content-type");
    if (ct) headers["content-type"] = ct;

    // Forward cookies so the backend can read the auth token
    const cookie = request.headers.get("cookie");
    if (cookie) headers["cookie"] = cookie;

    const init: RequestInit = {
      method: request.method,
      headers,
    };

    // Forward the body for non-GET requests
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = await request.text();
    }

    const backendRes = await fetch(url, init);

    // Build the response, forwarding all headers from backend
    const resHeaders = new Headers();
    backendRes.headers.forEach((value, key) => {
      // Forward set-cookie and other headers
      resHeaders.append(key, value);
    });

    const body = await backendRes.text();

    return new NextResponse(body, {
      status: backendRes.status,
      statusText: backendRes.statusText,
      headers: resHeaders,
    });
  } catch (err) {
    console.error("[API Proxy Error]", err);
    return NextResponse.json(
      { detail: "Proxy error: unable to reach backend" },
      { status: 502 }
    );
  }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, context);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, context);
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, context);
}

export async function OPTIONS(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, context);
}
