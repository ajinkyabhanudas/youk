# Test Strategies

Used in the TEST phase of dev-loop. Select the section for the detected
language/framework and apply the patterns.

---

## Test Plan Template

Before writing any test code, emit a test plan:

```
TEST PLAN
---------
Unit under test: [function/class/module]
Framework: [pytest / Vitest / testing / #[test] / etc.]

Happy path:
  1. [normal input → expected output]
  2. ...

Edge cases:
  3. [empty input]
  4. [single element]
  5. [max / overflow boundary]
  6. [nil / null / undefined / None]

Error paths:
  7. [invalid input type]
  8. [external dependency failure]
  9. [timeout / cancellation]

Concurrency (if async/concurrent):
  10. [concurrent calls don't corrupt state]

Performance (if relevant):
  11. [Nmax input completes in < T ms]

Missing coverage (honest assessment):
  - [what you're not testing and why]
```

---

## Python — pytest

```python
# conftest.py — shared fixtures
import pytest

@pytest.fixture
def sample_data():
    return {"key": "value"}

@pytest.fixture(autouse=True)
def reset_state():
    # setup
    yield
    # teardown

# test_module.py
import pytest
from mymodule import MyClass, process

class TestProcess:
    def test_happy_path(self, sample_data):
        result = process(sample_data)
        assert result.status == "ok"
        assert result.value == expected

    def test_empty_input(self):
        with pytest.raises(ValueError, match="input cannot be empty"):
            process({})

    def test_none_input(self):
        with pytest.raises(TypeError):
            process(None)

    @pytest.mark.parametrize("input,expected", [
        (1, "one"),
        (2, "two"),
        (0, "zero"),
    ])
    def test_parametrized(self, input, expected):
        assert convert(input) == expected

# Async tests
import pytest_asyncio

@pytest.mark.asyncio
async def test_async_function():
    result = await my_async_fn()
    assert result is not None

# Mocking
from unittest.mock import patch, AsyncMock

def test_with_mock():
    with patch("mymodule.external_call") as mock:
        mock.return_value = {"data": 42}
        result = function_that_calls_external()
        mock.assert_called_once_with(expected_arg)
```

**Run:** `pytest -v --tb=short`
**With coverage:** `pytest --cov=mymodule --cov-report=term-missing`

---

## TypeScript — Vitest

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config'
export default defineConfig({
  test: { environment: 'node', globals: true }
})

// module.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { processData, MyClass } from './module'

describe('processData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns processed result for valid input', () => {
    const result = processData({ key: 'value' })
    expect(result.status).toBe('ok')
  })

  it('throws on empty input', () => {
    expect(() => processData({})).toThrow('input cannot be empty')
  })

  it('handles null gracefully', () => {
    expect(() => processData(null as any)).toThrow(TypeError)
  })

  it.each([
    [1, 'one'],
    [2, 'two'],
    [0, 'zero'],
  ])('converts %i to %s', (input, expected) => {
    expect(convert(input)).toBe(expected)
  })
})

// Async
it('resolves with data on success', async () => {
  const result = await fetchData('id-123')
  expect(result).toMatchObject({ id: 'id-123' })
})

// Mocking
import { fetchExternalService } from './api'
vi.mock('./api')

it('calls external service with correct params', async () => {
  vi.mocked(fetchExternalService).mockResolvedValue({ ok: true })
  await myFunction('arg')
  expect(fetchExternalService).toHaveBeenCalledWith('arg')
})
```

**Run:** `vitest run` / `vitest --coverage`

---

## TypeScript — Jest (legacy/existing projects)

Same patterns as Vitest but use `jest.fn()`, `jest.mock()`, `jest.spyOn()`.
Import from `@jest/globals` for type safety.

---

## Go — testing + testify

```go
package mypackage_test

import (
    "testing"
    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
    "github.com/stretchr/testify/mock"
)

// Table-driven test (idiomatic Go)
func TestProcess(t *testing.T) {
    tests := []struct {
        name    string
        input   Input
        want    Output
        wantErr bool
    }{
        {
            name:  "happy path",
            input: Input{Key: "value"},
            want:  Output{Status: "ok"},
        },
        {
            name:    "empty input",
            input:   Input{},
            wantErr: true,
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got, err := Process(tt.input)
            if tt.wantErr {
                require.Error(t, err)
                return
            }
            require.NoError(t, err)
            assert.Equal(t, tt.want, got)
        })
    }
}

// Mock with testify/mock
type MockExternalService struct {
    mock.Mock
}

func (m *MockExternalService) Call(id string) (Result, error) {
    args := m.Called(id)
    return args.Get(0).(Result), args.Error(1)
}

func TestWithMock(t *testing.T) {
    svc := new(MockExternalService)
    svc.On("Call", "id-1").Return(Result{OK: true}, nil)
    
    subject := NewProcessor(svc)
    result, err := subject.Run("id-1")
    
    require.NoError(t, err)
    assert.True(t, result.OK)
    svc.AssertExpectations(t)
}
```

**Run:** `go test ./... -v -race`
**Coverage:** `go test ./... -coverprofile=coverage.out && go tool cover -html=coverage.out`

---

## Rust — built-in test + tokio-test

```rust
#[cfg(test)]
mod tests {
    use super::*;

    // Unit test
    #[test]
    fn test_process_happy_path() {
        let input = Input { key: "value".into() };
        let result = process(input).unwrap();
        assert_eq!(result.status, "ok");
    }

    #[test]
    fn test_process_empty_input() {
        let input = Input { key: "".into() };
        let err = process(input).unwrap_err();
        assert!(matches!(err, MyError::EmptyInput));
    }

    // Async test (tokio)
    #[tokio::test]
    async fn test_async_handler() {
        let result = async_handler("arg").await.unwrap();
        assert_eq!(result.id, "expected");
    }

    // Parameterized (manual)
    #[test]
    fn test_conversion() {
        let cases = vec![
            (1u32, "one"),
            (2u32, "two"),
            (0u32, "zero"),
        ];
        for (input, expected) in cases {
            assert_eq!(convert(input), expected, "failed for input {}", input);
        }
    }
}
```

**Run:** `cargo test`
**With output:** `cargo test -- --nocapture`

---

## Mocking Strategy (All Languages)

**Mock at the boundary, not inside your domain:**

```
[Your Code] → [Boundary Interface] → [Real External: DB, HTTP, FS, Clock]
                    ↑
              Mock this in tests
```

- Define an interface/trait/protocol for every external dependency.
- Inject the real implementation in production; inject the mock in tests.
- Never mock a type you don't own (mock the wrapper, not the third-party client).
- For HTTP: use a test server (e.g. `httptest.NewServer` in Go, `msw` in JS).
- For time: inject a clock interface; never call `time.Now()` / `Date.now()` directly.
- For DB: prefer an in-memory DB or transactions rolled back after each test over full mocks.

---

## Coverage Targets

| Layer | Target |
|-------|--------|
| Domain / business logic | ≥ 90% |
| Service / use-case layer | ≥ 80% |
| Infrastructure / adapters | ≥ 70% |
| CLI / main entrypoints | ≥ 50% (integration tests cover these) |

> Coverage is a floor, not a goal. 100% coverage with trivial assertions is worse
> than 70% coverage with meaningful assertions.

---

## Integration & E2E (Brief Notes)

- Integration tests: spin up real dependencies (Docker Compose or testcontainers).
- E2E tests: drive the public API; assert on observable outputs only.
- Keep E2E tests ≤ 20% of the test suite; they're slow and brittle.
- Always clean up created data; tests must be re-runnable without state leakage.
