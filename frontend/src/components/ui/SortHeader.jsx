import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

/** <th> with a sort button; aria-sort tells screen readers the current order */
export default function SortHeader({ label, sortKey, sort, onSort, num = false }) {
  const active = sort.key === sortKey;
  const Icon = !active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th className={num ? "num" : undefined} aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" className={active ? "sort-btn sort-btn--active" : "sort-btn"} onClick={() => onSort(sortKey)}>
        {label} <Icon size={13} aria-hidden="true" />
      </button>
    </th>
  );
}
