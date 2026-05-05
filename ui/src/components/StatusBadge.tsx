import { Badge } from "@/components/ui/badge";

const variantFor = (status: string) => {
  switch (status) {
    case "done": return "success" as const;
    case "running": return "default" as const;
    case "error": return "destructive" as const;
    case "pending": return "secondary" as const;
    case "no_execution": return "outline" as const;
    default: return "outline" as const;
  }
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={variantFor(status)} className="capitalize">
      {status.replace("_", " ")}
    </Badge>
  );
}
