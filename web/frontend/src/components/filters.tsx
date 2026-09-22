"use client";
import { useState } from "react";
import { FunnelSimpleIcon, XIcon } from "@phosphor-icons/react";
import type { Filters } from "@/lib/types";
import { DateField } from "./date-field";
export function FilterBar({
  filters,
  onChange,
  ponds,
  demo = false,
}: {
  filters: Filters;
  onChange: (filters: Filters) => void;
  ponds: string[];
  demo?: boolean;
}) {
  const active = Object.values(filters).some(Boolean);
  const [dateReset, setDateReset] = useState(0);
  return (
    <div className="filter-bar">
      <div className="filter-date">
        <DateField
          key={`start-${dateReset}`}
          label="開始日期"
          value={filters.start_date || ""}
          max={filters.end_date || undefined}
          onChange={(value) => onChange({ ...filters, start_date: value })}
        />
        <span className="date-to">至</span>
        <DateField
          key={`end-${dateReset}`}
          label="結束日期"
          value={filters.end_date || ""}
          min={filters.start_date || undefined}
          onChange={(value) => onChange({ ...filters, end_date: value })}
        />
      </div>
      <label className="filter-pond">
        <FunnelSimpleIcon size={18} />
        <select
          aria-label="篩選池別"
          value={filters.pond || ""}
          onChange={(e) => onChange({ ...filters, pond: e.target.value })}
        >
          <option value="">所有養殖池</option>
          {ponds.map((pond) => (
            <option key={pond} value={pond}>
              {pond}
            </option>
          ))}
        </select>
      </label>
      {active ? (
        <button
          type="button"
          className="clear-filter"
          onClick={() => {
            // A date's controlled value can already be empty while its local draft
            // is invalid. Remount both fields so clear-all also clears that draft.
            setDateReset((value) => value + 1);
            onChange({});
          }}
        >
          <XIcon size={14} />
          清除篩選
        </button>
      ) : (
        <span className="filter-hint">
          {demo ? "範例日期 2026.09.14 – 09.20" : "顯示全部觀察記錄"}
        </span>
      )}
    </div>
  );
}
