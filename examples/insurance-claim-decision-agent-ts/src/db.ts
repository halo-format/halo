// asyncpg-equivalent: a single shared pg Pool over MIMIC_DB_DSN (least-priv role).
import pg from "pg";

let _pool: pg.Pool | null = null;

export function pool(): pg.Pool {
  if (_pool === null) {
    const dsn = process.env.MIMIC_DB_DSN;
    if (!dsn) throw new Error("MIMIC_DB_DSN is not set");
    _pool = new pg.Pool({ connectionString: dsn, max: 8 });
  }
  return _pool;
}

export async function q<T = any>(text: string, params: unknown[] = []): Promise<T[]> {
  const r = await pool().query(text, params);
  return r.rows as T[];
}

export async function one<T = any>(text: string, params: unknown[] = []): Promise<T | null> {
  const rows = await q<T>(text, params);
  return rows.length ? rows[0] : null;
}

export async function closePool(): Promise<void> {
  if (_pool) {
    await _pool.end();
    _pool = null;
  }
}
