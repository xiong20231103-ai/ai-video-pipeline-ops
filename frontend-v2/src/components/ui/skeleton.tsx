// Source: https://raw.githubusercontent.com/shadcn-ui/ui/ba1503c64472b82256d9de95e2e62c5901a38e8b/apps/v4/registry/new-york-v4/ui/skeleton.tsx
// License: MIT; see public/licenses/shadcn-ui.LICENSE.md. Import alias adapted.
import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-md bg-accent", className)}
      {...props}
    />
  )
}

export { Skeleton }
