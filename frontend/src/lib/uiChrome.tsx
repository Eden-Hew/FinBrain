import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

interface UiChromeValue {
  askOpen: boolean;
  openAsk: () => void;
  closeAsk: () => void;
  paletteOpen: boolean;
  openPalette: () => void;
  closePalette: () => void;
}

const UiChromeContext = createContext<UiChromeValue | null>(null);

export function UiChromeProvider({ children }: { children: ReactNode }) {
  const [askOpen, setAskOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const openAsk = useCallback(() => { setAskOpen(true); setPaletteOpen(false); }, []);
  const closeAsk = useCallback(() => setAskOpen(false), []);
  const openPalette = useCallback(() => { setPaletteOpen(true); setAskOpen(false); }, []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((v) => !v);
        setAskOpen(false);
      }
      if (event.key === "Escape") {
        setAskOpen(false);
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <UiChromeContext.Provider value={{ askOpen, openAsk, closeAsk, paletteOpen, openPalette, closePalette }}>
      {children}
    </UiChromeContext.Provider>
  );
}

export function useUiChrome() {
  const ctx = useContext(UiChromeContext);
  if (!ctx) throw new Error("useUiChrome must be used within UiChromeProvider");
  return ctx;
}
