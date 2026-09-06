import { NextResponse, type NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  if (process.env.NEXT_PUBLIC_RAPID_PUBLIC_DEMO !== "true") return NextResponse.next();
  const path = request.nextUrl.pathname;
  if (path === "/aerospec" || path.startsWith("/aerospec/")) {
    return NextResponse.redirect(new URL("/rapid-design", request.url));
  }
  if (path.startsWith("/api/") && !path.startsWith("/api/rapid-design/")) {
    return NextResponse.json({ detail: "Not available in the public demo" }, { status: 404 });
  }
  return NextResponse.next();
}

export const config = { matcher: ["/api/:path*", "/aerospec/:path*"] };
