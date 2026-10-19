"use client";

// tenant-picker.tsx: choose the workspace (demo, Scale Demo, Finebase HQ) before signing in as a persona. The persona list
// follows the workspace, so Finebase HQ's people only appear once it is chosen. Used by: features/home.tsx.
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useTenants } from "@/lib/api/hooks";
import { useUi } from "@/lib/store";

export function TenantPicker() {
  const tenantId = useUi((s) => s.tenantId);
  const setTenant = useUi((s) => s.setTenant);
  const tenants = useTenants();
  const options = tenants.data ?? [{ id: tenantId, name: tenantId, isScaleDemo: false }];

  return (
    <Select value={tenantId} onValueChange={setTenant}>
      <SelectTrigger size="sm" className="h-9 max-w-[170px] text-xs font-medium" aria-label="Workspace">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((tenant) => (
          <SelectItem key={tenant.id} value={tenant.id}>{tenant.name}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
