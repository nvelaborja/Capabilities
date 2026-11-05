import type { Profile } from "../api/types";

interface PresetPickerProps {
  profiles: Profile[];
  preset: string | null;
  edited: boolean;
  onChoose: (preset: string | null) => void;
}

export function PresetPicker({ profiles, preset, edited, onChoose }: PresetPickerProps) {
  const current = profiles.find((profile) => profile.id === preset);
  const details = [current?.period, current?.region].filter(Boolean).join(" · ");
  return (
    <div className="preset-picker">
      <label htmlFor="preset">Preset</label>
      <div className="preset-row">
        <select id="preset" value={preset ?? ""} onChange={(event) => onChoose(event.target.value || null)}>
          <option value="">None (start empty)</option>
          {profiles.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.label}
            </option>
          ))}
        </select>
        {edited && preset && <span className="edited-badge">edited</span>}
      </div>
      {details && <p className="preset-details">{details}</p>}
    </div>
  );
}
