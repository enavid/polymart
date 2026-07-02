import type { InputProps } from "@/components/ui/input";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface FormFieldProps extends InputProps {
  id: string;
  label: string;
  hint?: string;
  /**
   * Omit the `name` attribute. Use for credential fields so that if the client
   * ever fails to hydrate and the browser falls back to a native form submit,
   * the value cannot be serialized into the URL (query string / history / logs).
   */
  omitName?: boolean;
}

/** Label + input pair with consistent spacing, used by every Phase 1 form. */
export function FormField({ id, label, hint, omitName, ...inputProps }: FormFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} name={omitName ? undefined : id} {...inputProps} />
      {hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
