import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export const MOTION_STORAGE_KEY = "closureops-motion-preference";
const mediaQuery = "(prefers-reduced-motion: reduce)";
export const MotionContext = createContext({
  preferReducedMotion: false,
  systemReducedMotion: false,
  reducedMotion: false,
  storageUnavailable: false,
  setPreferReducedMotion: (_value: boolean) => {
    void _value;
  },
});

export function MotionPreferenceProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [preferReducedMotion, setPreference] = useState(() => {
    try {
      return localStorage.getItem(MOTION_STORAGE_KEY) === "reduce";
    } catch {
      return false;
    }
  });
  const [systemReducedMotion, setSystemReducedMotion] = useState(
    () =>
      typeof window !== "undefined" && window.matchMedia(mediaQuery).matches,
  );
  const [storageUnavailable, setStorageUnavailable] = useState(false);
  useEffect(() => {
    const query = window.matchMedia(mediaQuery);
    const update = () => setSystemReducedMotion(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const setPreferReducedMotion = useCallback((value: boolean) => {
    setPreference(value);
    try {
      localStorage.setItem(MOTION_STORAGE_KEY, value ? "reduce" : "system");
      setStorageUnavailable(false);
    } catch {
      setStorageUnavailable(true);
    }
  }, []);
  return (
    <MotionContext.Provider
      value={{
        preferReducedMotion,
        systemReducedMotion,
        reducedMotion: preferReducedMotion || systemReducedMotion,
        storageUnavailable,
        setPreferReducedMotion,
      }}
    >
      {children}
    </MotionContext.Provider>
  );
}

export const useMotionPreference = () => useContext(MotionContext);
