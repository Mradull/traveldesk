// Sortable tables (#9): click a header to sort, click again to reverse.
import { useMemo, useState } from "react";

export function useTableSort(rows, initial = { key: null, dir: "asc" }, accessors = {}) {
  const [sort, setSort] = useState(initial);
  const sorted = useMemo(() => {
    if (!sort.key || !rows) return rows ?? [];
    const get = accessors[sort.key] ?? ((r) => r[sort.key]);
    return [...rows].sort((a, b) => {
      const x = get(a), y = get(b);
      const cmp = typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""), "en", { numeric: true });
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }, [rows, sort]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggle = (key) => setSort((s) => ({ key, dir: s.key === key && s.dir === "asc" ? "desc" : "asc" }));
  return { sorted, sort, toggle };
}

/** Free-text filter over the given fields */
export function filterRows(rows, query, fields) {
  const q = query.trim().toLowerCase();
  if (!q) return rows ?? [];
  return (rows ?? []).filter((r) => fields.some((f) => String(typeof f === "function" ? f(r) : r[f] ?? "").toLowerCase().includes(q)));
}
