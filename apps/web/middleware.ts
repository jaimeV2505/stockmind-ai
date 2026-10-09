import { NextResponse, type NextRequest } from "next/server";
import { decideAccess } from "./lib/access.ts";

export function middleware(req: NextRequest) {
  const d = decideAccess({
    authorization: req.headers.get("authorization"),
    dataMode: process.env.STOCKMIND_DATA,
    user: process.env.SITE_USER,
    password: process.env.SITE_PASSWORD,
  });
  if (d.action === "allow") return NextResponse.next();
  if (d.action === "challenge") {
    return new NextResponse("Authentication required", { status: 401, headers: { "WWW-Authenticate": 'Basic realm="StockMind", charset="UTF-8"' } });
  }
  // Fail closed: never serve real market data without a proper password.
  return new NextResponse(`Service misconfigured: ${d.reason}`, { status: 503, headers: { "Cache-Control": "no-store" } });
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
