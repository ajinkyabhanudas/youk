# JavaScript / TypeScript — Code Review Additions

Layer these checks on top of the base ANALYZE and SECURITY phases.
Applies to both JavaScript and TypeScript. TypeScript-specific rows are marked **[TS]**.

---

## JS/TS ANALYZE additions

| Check | Severity |
|---|---|
| `async` function called without `await` — Promise silently dropped | HIGH |
| `Promise` returned from a function but not awaited by caller | HIGH |
| Event listener added without corresponding `removeEventListener` in cleanup | MEDIUM — memory leak |
| `useEffect` with missing dependency array entries (React) | HIGH — stale closure |
| `useEffect` cleanup function missing when effect sets up subscription or timer | MEDIUM |
| `setState` called on unmounted component (React) | MEDIUM |
| `==` used for equality instead of `===` | LOW |
| `typeof x === "undefined"` instead of `x === undefined` or `x == null` | INFO |
| Object property access without null check on potentially-null object | HIGH |
| `parseInt()` without radix argument | MEDIUM |
| Mutating function argument directly (not a copy) | MEDIUM |

---

## TypeScript-specific additions **[TS]**

| Check | Severity |
|---|---|
| `any` type used without comment explaining why it can't be typed | MEDIUM |
| `as` type assertion masking a genuine type mismatch | MEDIUM |
| `!` non-null assertion on a value that could realistically be null | HIGH |
| `@ts-ignore` or `@ts-expect-error` without a reason comment | MEDIUM |
| `Record<string, any>` used where a typed interface would catch errors | MEDIUM |
| Enum used where a const object or union type is sufficient | INFO |

---

## JS/TS security additions

| Check | Severity |
|---|---|
| `eval()`, `new Function()`, or `setTimeout("string", ...)` | CRITICAL |
| `innerHTML` set from any user-controlled value (XSS) | CRITICAL |
| `dangerouslySetInnerHTML` in React without sanitization | CRITICAL |
| `document.write()` | HIGH |
| `postMessage` target origin is `"*"` (any origin can receive) | HIGH |
| `JSON.parse()` on untrusted input without try/catch | MEDIUM |
| `prototype` or `__proto__` access in data processing (prototype pollution) | HIGH |
| `require()` or `import()` with user-controlled path | CRITICAL |
| URL constructed from user input and used in `fetch()` without allowlist | HIGH — SSRF |

---

## Bundle / performance additions (when reviewing frontend code)

| Check | Severity |
|---|---|
| Large library imported fully when only a single function is needed | MEDIUM — bundle size |
| `import * as X` from a large module (prevents tree-shaking) | LOW |
| Image loaded without lazy loading or explicit dimensions | LOW |
| `console.log` left in production code | LOW |
