import { redirect } from "next/navigation";

/**
 * The batches table lived here. The history log supersedes it — same rows, plus
 * imports and review notes, plus a date filter — so the old route forwards
 * instead of maintaining a second list of the same thing.
 */
export default function JobsPage() {
  redirect("/dashboard?view=history");
}
