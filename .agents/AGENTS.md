# KiteCLI Workspace Agent Rules

These rules apply to all AI agents working on the `kitecli` repository. Follow these constraints to prevent regression bugs, ensure trade safety, and maintain TUI scroll performance.

## 1. Safety Guardrails & Testing
*   **No Live Trading in Tests**: Under no circumstances should test modules execute live network calls to Zerodha or place actual orders. Always use `unittest.mock` to patch `KCLIClient`, `KiteTicker`, and `KCLILiveSession.execute_exit`.
*   **Mandatory Test Validation**: After any modification to the CLI or the broker manager, you MUST run the test suite and verify that all tests pass:
    ```bash
    python3 run_tests.py
    ```

## 2. Command & Parameter Rules
*   **Limit Price Syntax**: Limit prices parsed from command inputs must be raw floats (e.g. `1.40`). Do not prefix prices with the `@` symbol (e.g. `@1.40` is invalid).
*   **Symbol Mapping for Exits**:
    *   The `exit all` command must map the `"all"` symbol to `None` when calling `execute_exit` or `exit_positions`.
    *   Position lookup is resolved via active positions table matching or index integers (1, 2, 3...) mapped in `session.position_id_map`.
*   **Order Quantity Splitting**:
    *   Order quantities larger than the exchange limit (1800) must route through `place_order` in `kite_manager.py` to be automatically sliced. Never bypass this code for large volume orders.

## 3. UI Scroll & State
*   **Dynamic WebSocket Connection Header**:
    *   The header uses `FormattedTextControl` with a list of text fragments to map a custom mouse click callback (`_header_click_handler`) on the WebSocket status label.
    *   Connection states are tracked via `on_connect`, `on_close`, and `on_error` callbacks inside `live_session.py`.
    *   Do not replace the header fragments with a plain string; keep the HTML/fragment structure intact for mouse click routing.
*   **Buffer Scroll Movement**:
    *   Use prompt-toolkit's native cursor movement (`cursor_up()` and `cursor_down()`) on the underlying pane buffers instead of modifying scroll values directly. This prevents scroll snapping and locks.
