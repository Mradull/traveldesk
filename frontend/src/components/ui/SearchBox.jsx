import { Search, X } from "lucide-react";

export default function SearchBox({ value, onChange, placeholder = "Search…", label = "Search" }) {
  return (
    <div className="search-box">
      <Search size={16} aria-hidden="true" />
      <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={label} />
      {value && (
        <button type="button" onClick={() => onChange("")} aria-label="Clear search"><X size={14} /></button>
      )}
    </div>
  );
}
