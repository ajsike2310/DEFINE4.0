import { useCallback, useEffect, useRef, useState } from "react";

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const latest = useRef(0);   // only the most recent request may update state (a slow older response is ignored)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(() => {
    const id = ++latest.current;
    setLoading(true);
    fn()
      .then((d) => { if (id === latest.current) { setData(d); setError(null); } })
      .catch((e) => { if (id === latest.current) setError(e); })
      .finally(() => { if (id === latest.current) setLoading(false); });
  }, deps);
  useEffect(run, [run]);
  useEffect(() => () => { latest.current++; }, []);   // ignore results after unmount
  return { data, error, loading, reload: run };
}
