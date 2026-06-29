import type { InputProps } from "@/components/ui/input";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface FormFieldProps extends InputProps {
  id: string;
  label: string;
  hint?: string;
}

/** Label + input pair with consistent spacing, used by every Phase 1 form. */
export function FormField({ id, label, hint, ...inputProps }: FormFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} name={id} {...inputProps} />
      {hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
