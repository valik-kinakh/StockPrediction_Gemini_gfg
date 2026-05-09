import './TabBar.css';

const TABS = [
  { value: 'forecast', label: 'Forecast' },
  { value: 'options', label: 'Options Lab' },
  { value: 'scanner', label: 'Watchlist Scanner' },
];

function TabBar({ active, onChange }) {
  return (
    <nav className="tabbar" role="tablist">
      {TABS.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={active === t.value}
          className={`tab ${active === t.value ? 'active' : ''}`}
          onClick={() => onChange(t.value)}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}

export default TabBar;
