import { useState } from "react";
import { useI18n, type Lang } from "../lib/i18n";
import { useAppState, AVATAR_COLORS } from "../lib/appState";
import { useAuth } from "../auth/AuthProvider";
import { useTheme, type ThemePreference } from "../lib/theme";
import { Sidebar, AppTopBar } from "../components/Nav";
import { PERSONAS } from "../lib/personas";

const THEME_OPTIONS: { value: ThemePreference; label: string; desc: string }[] = [
  { value: "light", label: "Light", desc: "Always light, whatever your device is set to." },
  { value: "dark", label: "Dark", desc: "Always dark, whatever your device is set to." },
  { value: "system", label: "System", desc: "Follows your device, and changes with it." },
];

const LANG_OPTIONS: { value: Lang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "ms", label: "Bahasa Malaysia" },
  { value: "zh", label: "中文" },
];

export default function Settings() {
  const { t, lang, setLang } = useI18n();
  const { preference, setPreference } = useTheme();
  const { askRole, avatarColor, setAvatarColor, displayName, setDisplayName } = useAppState();
  const { identity } = useAuth();
  const [nameDraft, setNameDraft] = useState(displayName);

  const email = identity?.email ?? "—";
  const role = identity?.role ?? askRole;
  const initials = (displayName || email)[0]?.toUpperCase() ?? "?";

  const saveName = () => setDisplayName(nameDraft.trim());

  return (
    <div className="fb-root fb-shell">
      <Sidebar current="settings" />
      <AppTopBar current="settings" />

      <header className="fb-app-header">
        <h1>{t("settings.title")}</h1>
        <p>{t("settings.desc")}</p>
      </header>

      <div className="fb-page-body">
        <section className="fb-settings-section">
          <h2>Appearance</h2>
          <div className="fb-settings-card">
            {THEME_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={"fb-settings-option" + (preference === opt.value ? " is-selected" : "")}
                onClick={() => setPreference(opt.value)}
                role="radio"
                aria-checked={preference === opt.value}
              >
                <span className="fb-settings-radio"><span className="fb-settings-radio-dot" /></span>
                <span>
                  <span className="fb-settings-option-title">{opt.label}</span>
                  <span className="fb-settings-option-desc">{opt.desc}</span>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="fb-settings-section">
          <h2>Language</h2>
          <div className="fb-settings-card">
            <div className="fb-settings-lang-row">
              {LANG_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={"fb-settings-lang-pill" + (lang === opt.value ? " is-selected" : "")}
                  onClick={() => setLang(opt.value)}
                  aria-pressed={lang === opt.value}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="fb-settings-section">
          <h2>Avatar</h2>
          <div className="fb-settings-card">
            <div className="fb-settings-avatar-row">
              <span className="fb-settings-avatar-preview" style={{ background: avatarColor }}>{initials}</span>
              {AVATAR_COLORS.map((color) => (
                <button
                  key={color}
                  type="button"
                  className={"fb-settings-swatch" + (avatarColor === color ? " is-selected" : "")}
                  style={{ background: color }}
                  onClick={() => setAvatarColor(color)}
                  aria-label={`Use ${color} as avatar color`}
                  aria-pressed={avatarColor === color}
                />
              ))}
            </div>
          </div>
        </section>

        <section className="fb-settings-section">
          <h2>Account</h2>
          <div className="fb-settings-card">
            <div className="fb-settings-field">
              <span className="fb-settings-field-label">Email</span>
              <span className="fb-settings-field-value">{email}</span>
            </div>
            <div className="fb-settings-field">
              <span className="fb-settings-field-label">Role</span>
              <span className="fb-settings-field-value">{PERSONAS[role].label}</span>
            </div>
            <div className="fb-settings-field">
              <span className="fb-settings-field-label">Display name</span>
              <div style={{ display: "flex", gap: ".5rem", alignItems: "center" }}>
                <input
                  className="fb-input"
                  type="text"
                  value={nameDraft}
                  onChange={(event) => setNameDraft(event.target.value)}
                  onBlur={saveName}
                  onKeyDown={(event) => { if (event.key === "Enter") saveName(); }}
                  placeholder={email.split("@")[0]}
                  maxLength={40}
                />
              </div>
            </div>
            <div className="fb-settings-field">
              <span className="fb-fine">Display name only changes your greeting and avatar initials on this device — it doesn't change your account or who others see you as. Email and role come from your provisioned account and can't be changed here.</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
