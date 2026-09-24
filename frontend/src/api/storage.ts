/** Storage wrappers — every access is guarded (private mode, blocked storage, SSR). */

const TOKEN_KEY = 'sie.token';
const ADMIN_KEY = 'sie.adminKey';

function read(storage: () => Storage, key: string): string | null {
  try {
    return storage().getItem(key);
  } catch {
    return null;
  }
}

function write(storage: () => Storage, key: string, value: string | null): void {
  try {
    if (value == null) storage().removeItem(key);
    else storage().setItem(key, value);
  } catch {
    /* storage unavailable — keep working in memory only */
  }
}

let memoryToken: string | null = null;
let memoryAdminKey: string | null = null;

export const tokenStore = {
  get(): string | null {
    return read(() => window.localStorage, TOKEN_KEY) ?? memoryToken;
  },
  set(token: string | null): void {
    memoryToken = token;
    write(() => window.localStorage, TOKEN_KEY, token);
  },
};

export const adminKeyStore = {
  get(): string | null {
    return read(() => window.sessionStorage, ADMIN_KEY) ?? memoryAdminKey;
  },
  set(key: string | null): void {
    memoryAdminKey = key;
    write(() => window.sessionStorage, ADMIN_KEY, key);
  },
};
