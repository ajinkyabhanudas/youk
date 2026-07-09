# Stack: TypeScript + React
detection_key: typescript_react

Detected when: TypeScript project + React dependency (package.json).
Covers: Next.js, Vite/CRA, component libraries, frontend-heavy apps.

---

## Core concepts a developer will encounter

| Concept | What it is (one sentence) | When it appears |
|---|---|---|
| Component re-render cycle | React re-renders a component when its state or props change — subtree re-renders by default | Performance; unnecessary API calls; stale closures |
| Virtual DOM diffing | React computes a diff between previous and next render trees and applies only the changes to the real DOM | Understanding React's cost model; `key` prop importance |
| Hooks dependency array | `useEffect`, `useCallback`, `useMemo` only re-run when listed dependencies change | Stale data; infinite loops; unnecessary recomputation |
| Closures in event handlers | Event handlers capture the value of state at the time they were defined, not when they run | Stale state bugs; `useRef` patterns |
| TypeScript structural typing | Types are compatible if their shapes match, not if they share a declared type name | Flexible API design; gotchas when two types share shape but different semantics |
| `async` component / Suspense | React 18+ lets components suspend while awaiting async data | Data fetching patterns; loading states; streaming SSR |
| Server Components vs. Client Components | Server Components render on the server (no JS sent); Client Components ship JS and can use hooks/state | Next.js App Router mental model |
| `useRef` vs. `useState` | `useRef` holds a mutable value that does NOT trigger re-render; `useState` does | DOM access; persisting values across renders without re-render |
| Context API vs. state management | Context re-renders all consumers on every change; Zustand/Redux select only what changed | Global state performance; prop drilling |
| Hydration | Attaching event listeners to server-rendered HTML so it becomes interactive | SSR/SSG; hydration mismatch errors |
| Type narrowing | TypeScript's ability to reduce a union type based on runtime checks (`typeof`, `instanceof`, discriminated unions) | Error handling; polymorphic data; API responses |

---

## Patterns that commonly surprise developers

- **Stale closure in `useEffect`**: `useEffect(() => { console.log(count) }, [])` captures `count` at mount time. Even if `count` changes, the logged value stays the same. Missing dependency = stale read.
- **`key` as identity, not just uniqueness**: Changing a component's `key` unmounts and remounts it — all state is lost. This is intentional for resets, but surprises when keys are derived from data that changes.
- **TypeScript `strictNullChecks` off by default**: Many starter configs don't enable full strict mode. `null` and `undefined` are assignable to any type without `strictNullChecks`, silently hiding bugs.
- **Context triggers all consumers**: `<MyContext.Provider value={obj}>` — if `obj` is a new object on every render (e.g. `value={{ a, b }}`), every consumer re-renders. Memoize the value.
- **`async` in `useEffect`**: Can't mark a `useEffect` callback as `async` directly (it returns a Promise, not a cleanup function). Workaround: define async inside and call it.

---

## Common cross-stack analogies (starting points for MAP phase)

| Concept | Generic analogy | Analogy quality |
|---|---|---|
| Component re-render | Function call triggered by dependency change — like a reactive formula in a spreadsheet | STRONG |
| Virtual DOM diffing | Diff algorithm (like `git diff`) applied to UI trees | STRONG |
| Hooks dependency array | Makefile dependency tracking — only rebuild when listed dependencies change | PARTIAL |
| TypeScript structural typing | Duck typing with compile-time enforcement | STRONG |
| Server vs. Client Components | Server-side rendering vs. client-side JS execution — same concept, new model | STRONG |
| Context API | Global variable with subscriber notification — but re-renders all subscribers on change | PARTIAL |
| Hydration | HTML scaffolding delivered first, then JS attaches to make it interactive — like progressively enhancing static HTML | STRONG |
