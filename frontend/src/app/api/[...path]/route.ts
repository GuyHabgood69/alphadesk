import { NextRequest, NextResponse } from "next/server";

/**
 * Catch-all API proxy — forwards /api/* requests to the backend.
 * Uses server-side BACKEND_URL env var (not NEXT_PUBLIC_*).
 * This runs at runtime so the env var is read when the request comes in.
 */
const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxy(request, await params);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxy(request, await params);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxy(request, await params);
}

async function proxy(
  request: NextRequest,
  params: { path: string[] }
) {
  const path = params.path.join("/");
  const url = `${BACKEND}/api/${path}`;

  const headers = new Headers();
  headers.set("Content-Type", request.headers.get("Content-Type") || "application/json");
  // Forward cookies so the backend can read the auth token
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);

  const init: RequestInit = {
    method: request.method,
    headers,
  };

  // Forward the body for POST/PUT/PATCH/DELETE
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  const backendRes = await fetch(url, init);

  // Build response and forward Set-Cookie headers from backend
  const resHeaders = new Headers();
  backendRes.headers.forEach((value, key) => {
    resHeaders.append(key, value);
  });

  return new NextResponse(backendRes.body, {
    status: backendRes.status,
    statusText: backendRes.statusText,
    headers: resHeaders,
  });
}
