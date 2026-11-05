import type { ThemePreference } from "./theme";

const OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: "system", label: "Auto" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

interface ThemeSwitchProps {
  preference: ThemePreference;
  onChoose: (preference: ThemePreference) => void;
}

export function ThemeSwitch({ preference, onChoose }: ThemeSwitchProps) {
  return (
    <div className="theme-switch" role="group" aria-label="Theme">
      {OPTIONS.map(({ value, label }) => (
        <button key={value} type="button" aria-pressed={preference === value} onClick={() => onChoose(value)}>
          {label}
        </button>
      ))}
    </div>
  );
}
