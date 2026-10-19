export function loginDestination(
  location: Pick<Location, "pathname" | "search" | "hash"> = window.location,
) {
  const next = location.pathname + location.search + location.hash;
  return "/login?next=" + encodeURIComponent(next);
}
// A relative old-static link works both under the cloud and unmodified home mount.
export const legacyDestination = "/static/index.html";
