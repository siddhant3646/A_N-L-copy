# Lessons Learned

## Modern UI DOM Handling (LinkedIn)
- **Pattern:** Using standard `document.querySelector` or `.querySelectorAll()` can cause script logic to mysteriously fail and "not find" elements that are clearly visible on the screen.
- **Root Cause:** Modern websites like LinkedIn heavily utilize component-based architectures where elements are encapsulated within Shadow DOM structures.
- **Rule:** For high-robustness scraping or UI automation, replace native selection methods with deep querying patterns (`queryDeep` / `queryAllDeep`) that recursively explore and piece together the `shadowRoot` elements of the web page.

## Mac Terminal Browsing (CDP)
- **Pattern:** Attempting to spawn Chrome with Playwright's persistent context triggers deep macOS restriction blocks (`Operation not permitted` / `SingletonLock` issues) resulting in instant script failure or ECONNREFUSED when binding to `9222`.
- **Root Cause:** App Gatekeeper sandbox limits Playwright's ability to seamlessly hijack an existing user profile's session variables natively.
- **Rule:** Rather than mirroring profiles or launching Chrome binaries directly, the most bulletproof way to hook Playwright into a session profile natively on macOS is using `subprocess.Popen` with the `open -n -a "Google Chrome"` command combined with CDP connection, and systematically removing hanging `SingletonLock` artifacts before boot.
