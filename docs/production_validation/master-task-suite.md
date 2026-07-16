# Production Validation Master Task Suite

This suite is the canonical PVS-2 catalog for validating the production browser assistant on real websites. Tasks are intentionally practical, user-facing workflows that exercise planning, execution, validation, memory, tab control, file transfer, and long-running behavior.

Use the maximum planner turns and maximum browser actions as stopping limits, not success targets. A task that completes earlier should stop immediately.

## Task Catalog

| ID | Category | Goal | Website | Difficulty | Expected Success Criteria | Max Planner Turns | Max Browser Actions |
|---|---|---|---|---|---|---:|---:|
| PVS-001 | Google Search | Search for "browser automation frameworks" and identify the first three organic result titles. | google.com | Easy | Reports three visible organic result titles without ads or sidebar items. | 6 | 6 |
| PVS-002 | Google Search | Search for "site:github.com browser automation playwright" and open the most relevant repository result. | google.com | Medium | Navigates to a GitHub repository page, not stars/issues/wiki. | 8 | 8 |
| PVS-003 | Google Search | Search for "OpenAI API rate limits documentation" and report the title of the official documentation result. | google.com | Easy | Reports an official docs result title and URL. | 6 | 5 |
| PVS-004 | Google Search | Search for "best lightweight headless browser" and compare two result snippets. | google.com | Medium | Reports two result titles and snippet-level comparison. | 10 | 10 |
| PVS-005 | Google Search | Search for "Python CSV upload example" and open a documentation or tutorial result. | google.com | Medium | Opens a relevant page and reports the page title. | 8 | 8 |
| PVS-006 | Google Search | Search for "weather tomorrow San Francisco" and report the visible forecast summary. | google.com | Easy | Reports forecast from visible search results without requiring another site. | 5 | 5 |
| PVS-007 | Google Search | Search for "Chrome extension manifest v3 storage API" and open the official Chrome docs. | google.com | Medium | Ends on developer.chrome.com documentation. | 8 | 8 |
| PVS-008 | Google Search | Search for "React table virtualization docs" and collect two documentation sources. | google.com | Hard | Reports two documentation pages with titles and URLs. | 14 | 14 |
| PVS-009 | Google Search | Search for "US passport renewal official" and identify the official government result. | google.com | Easy | Reports official government page title and URL. | 6 | 6 |
| PVS-010 | Google Search | Search for "compare Cursor Windsurf pricing" and open pages needed for comparison. | google.com | Hard | Collects at least two pricing sources or reports blocker. | 18 | 20 |
| PVS-011 | GitHub | Search GitHub repositories for "browser automation" and compare the top two by stars and last updated date. | github.com | Hard | Reports two repository names, stars, and update dates. | 20 | 22 |
| PVS-012 | GitHub | Open a repository and report its README headline and primary language. | github.com | Easy | Reports repository name, README headline, and language. | 8 | 8 |
| PVS-013 | GitHub | Find the latest release tag for a repository. | github.com | Medium | Navigates to releases or repository metadata and reports latest tag. | 12 | 12 |
| PVS-014 | GitHub | Find whether a repository has open issues. | github.com | Medium | Reports open issue count or clear absence. | 10 | 10 |
| PVS-015 | GitHub | Compare two repositories from search results by stars. | github.com | Medium | Reports both names and star counts. | 16 | 16 |
| PVS-016 | GitHub | Open repository docs folder and report available documentation files. | github.com | Medium | Reports at least two docs files or explains none visible. | 14 | 14 |
| PVS-017 | GitHub | Search within a repository for "Dockerfile" and open the file. | github.com | Hard | Opens a Dockerfile or reports that search found none. | 16 | 16 |
| PVS-018 | GitHub | Identify the license of a repository. | github.com | Easy | Reports license value from repository page or license file. | 8 | 8 |
| PVS-019 | GitHub | Find the most recent commit message on a repository default branch. | github.com | Medium | Reports the latest visible commit message. | 10 | 10 |
| PVS-020 | GitHub | Open two search results in separate tabs and compare repository descriptions. | github.com | Hard | Uses tabs or preserved context to report both descriptions. | 22 | 24 |
| PVS-021 | Documentation | Find the installation command in Playwright Python docs. | playwright.dev | Medium | Reports correct installation command visible in docs. | 10 | 10 |
| PVS-022 | Documentation | Find the React `useEffect` cleanup explanation. | react.dev | Medium | Reports the relevant explanation or section title. | 12 | 12 |
| PVS-023 | Documentation | Find MDN documentation for `Array.prototype.map` and report syntax. | developer.mozilla.org | Easy | Reports syntax from MDN page. | 8 | 8 |
| PVS-024 | Documentation | Find Chrome extension storage API docs and report the available storage areas. | developer.chrome.com | Medium | Reports listed storage areas. | 12 | 12 |
| PVS-025 | Documentation | Find Next.js App Router dynamic routes documentation. | nextjs.org | Medium | Reports official page title and key route syntax. | 12 | 12 |
| PVS-026 | Documentation | Search Tailwind docs for grid columns and report class examples. | tailwindcss.com | Medium | Reports grid column class examples from docs. | 10 | 10 |
| PVS-027 | Documentation | Find Python `csv` module docs and report reader/writer names. | docs.python.org | Easy | Reports `csv.reader` and `csv.writer` or equivalent. | 8 | 8 |
| PVS-028 | Documentation | Find Postgres `CREATE INDEX` docs and report the command heading. | postgresql.org | Medium | Reports official command page heading. | 10 | 10 |
| PVS-029 | Documentation | Find Vite environment variables docs and report the prefix rule. | vite.dev | Medium | Reports `VITE_` exposure rule from docs. | 10 | 10 |
| PVS-030 | Documentation | Compare two documentation pages about authentication middleware. | nextjs.org / clerk.com | Hard | Reports two source titles and one key difference. | 20 | 22 |
| PVS-031 | Shopping | Search Amazon for "wireless mouse" and report the first visible product name and price. | amazon.com | Medium | Reports product name and price visible in search results or product page. | 14 | 14 |
| PVS-032 | Shopping | Search Amazon India for "USB C cable" and report the first visible price. | amazon.in | Medium | Reports visible price with currency. | 14 | 14 |
| PVS-033 | Shopping | Search Flipkart for "bluetooth headphones" and report the first product rating. | flipkart.com | Medium | Reports first product title and rating. | 14 | 14 |
| PVS-034 | Shopping | Open a product page and identify delivery availability field. | amazon.com | Hard | Reports delivery/availability information or blocker. | 16 | 16 |
| PVS-035 | Shopping | Compare two laptop listings by price from search results. | amazon.com | Hard | Reports two product names and prices. | 20 | 20 |
| PVS-036 | Shopping | Apply a brand filter on a shopping search page. | amazon.com | Hard | Filter state visibly applied or clear blocker recorded. | 18 | 18 |
| PVS-037 | Shopping | Sort product search results by price low to high. | amazon.com | Medium | Sort state visible or results reordered. | 14 | 14 |
| PVS-038 | Shopping | Find whether a product has customer reviews. | amazon.com | Medium | Reports review count or visible absence. | 12 | 12 |
| PVS-039 | Shopping | Add a non-purchase item to cart up to the confirmation step only. | amazon.com | Hard | Item added or stops before purchase/payment. | 18 | 18 |
| PVS-040 | Shopping | Compare return policy snippets for two products. | amazon.com | Hard | Reports policy evidence for two products or blocker. | 24 | 24 |
| PVS-041 | SaaS | Open a SaaS pricing page and report the cheapest paid plan. | notion.so | Medium | Reports plan name and price. | 12 | 12 |
| PVS-042 | SaaS | Find billing plan details on a project management SaaS site. | asana.com | Medium | Reports visible plan names/prices. | 12 | 12 |
| PVS-043 | SaaS | Start signup flow until email field is visible, then stop. | slack.com | Medium | Email input visible; no account created. | 12 | 12 |
| PVS-044 | SaaS | Compare free plan limits between two SaaS pricing pages. | notion.so / trello.com | Hard | Reports both free-plan limits with sources. | 22 | 24 |
| PVS-045 | SaaS | Find API documentation link from a SaaS homepage. | stripe.com | Medium | Navigates to official docs/API reference. | 12 | 12 |
| PVS-046 | SaaS | Find contact sales button and report label. | hubspot.com | Easy | Reports visible sales/contact CTA. | 8 | 8 |
| PVS-047 | SaaS | Locate help center article search and search for "billing". | intercom.com | Medium | Help results visible or blocker recorded. | 14 | 14 |
| PVS-048 | SaaS | Open pricing FAQ and report refund/cancellation text. | calendly.com | Medium | Reports visible FAQ snippet. | 14 | 14 |
| PVS-049 | SaaS | Compare two AI coding assistant pricing pages. | cursor.com / codeium.com | Hard | Reports two prices or free tiers with evidence. | 24 | 26 |
| PVS-050 | SaaS | Navigate from homepage to login page and stop before authentication. | dropbox.com | Easy | Login page or login form visible. | 8 | 8 |
| PVS-051 | Gmail | Open Gmail and summarize the subject of the latest visible email. | mail.google.com | Medium | Reports latest visible subject or auth blocker. | 10 | 10 |
| PVS-052 | Gmail | Search Gmail for "invoice" and report first visible matching subject. | mail.google.com | Hard | Search results visible and first subject reported. | 14 | 14 |
| PVS-053 | Gmail | Open latest unread email and report sender. | mail.google.com | Hard | Sender reported or auth/permission blocker. | 14 | 14 |
| PVS-054 | Gmail | Draft an email with provided recipient/subject/body, but do not send. | mail.google.com | Hard | Draft fields filled; send not clicked. | 18 | 18 |
| PVS-055 | Gmail | Find attachments in latest email and report filenames only. | mail.google.com | Hard | Attachment names reported or none visible. | 16 | 16 |
| PVS-056 | Gmail | Navigate to sent mail and report latest sent subject. | mail.google.com | Medium | Sent list visible and subject reported. | 12 | 12 |
| PVS-057 | Google Docs | Open Docs homepage and identify the first recent document title. | docs.google.com | Medium | Reports first visible recent document or auth blocker. | 10 | 10 |
| PVS-058 | Google Docs | Create a blank document and type a short provided title, then stop. | docs.google.com | Hard | Document created and text inserted; no sharing. | 18 | 18 |
| PVS-059 | Google Docs | Search recent Docs for a provided keyword. | docs.google.com | Hard | Search results visible or blocker recorded. | 14 | 14 |
| PVS-060 | Google Docs | Open a document and report word count if accessible. | docs.google.com | Hard | Word count reported or menu blocker recorded. | 18 | 18 |
| PVS-061 | Google Sheets | Open Sheets homepage and report first recent sheet title. | sheets.google.com | Medium | Reports first visible sheet title or auth blocker. | 10 | 10 |
| PVS-062 | Google Sheets | Create a blank sheet and enter a two-cell table, then stop. | sheets.google.com | Hard | Values visible in cells; no sharing. | 18 | 20 |
| PVS-063 | Google Sheets | Search Sheets templates for budget and report first template. | sheets.google.com | Medium | Reports visible template title. | 12 | 12 |
| PVS-064 | Google Sheets | Open a sheet and report active cell coordinates. | sheets.google.com | Hard | Active cell or blocker reported. | 14 | 14 |
| PVS-065 | LinkedIn | Search LinkedIn jobs for "frontend engineer remote" and report first job title. | linkedin.com/jobs | Hard | First visible job title reported or auth blocker. | 16 | 16 |
| PVS-066 | LinkedIn | Search LinkedIn people for a company name and report first result name/title. | linkedin.com | Hard | First visible result reported or auth blocker. | 16 | 16 |
| PVS-067 | LinkedIn | Open a job result and report company and location. | linkedin.com/jobs | Hard | Company and location reported. | 18 | 18 |
| PVS-068 | LinkedIn | Apply a remote filter to job search. | linkedin.com/jobs | Hard | Remote filter visibly applied or blocker. | 18 | 18 |
| PVS-069 | LinkedIn | Save a job only if user is already authenticated and confirmation is visible. | linkedin.com/jobs | Hard | Saved confirmation or auth blocker. | 16 | 16 |
| PVS-070 | LinkedIn | Compare two job postings by salary visibility. | linkedin.com/jobs | Hard | Reports salary shown/not shown for two jobs. | 22 | 24 |
| PVS-071 | Government Forms | Find official passport renewal page and report eligibility section title. | travel.state.gov | Medium | Official page and section title reported. | 12 | 12 |
| PVS-072 | Government Forms | Open IRS forms search and search for "W-9". | irs.gov | Medium | W-9 result visible or report official result. | 12 | 12 |
| PVS-073 | Government Forms | Fill a public contact form with dummy data up to review, then stop. | usa.gov/contact | Hard | Fields filled; no submit unless harmless test endpoint. | 18 | 18 |
| PVS-074 | Government Forms | Find DMV appointment page for a state and report first appointment-related CTA. | state DMV site | Hard | Official appointment CTA identified. | 16 | 16 |
| PVS-075 | Government Forms | Locate a city permit application PDF download link. | city.gov | Hard | Download link identified or blocker. | 18 | 18 |
| PVS-076 | University Portals | Search university course catalog for "computer science" and report first course. | university catalog | Medium | First visible course title/code reported. | 14 | 14 |
| PVS-077 | University Portals | Find admissions deadline page and report application deadline. | university.edu | Medium | Deadline reported with page title. | 14 | 14 |
| PVS-078 | University Portals | Find tuition page and report undergraduate tuition figure. | university.edu | Medium | Tuition figure reported or blocker. | 14 | 14 |
| PVS-079 | University Portals | Open library search and search for "machine learning". | university library | Hard | Results visible or blocker. | 16 | 16 |
| PVS-080 | University Portals | Navigate to student portal login and stop before login. | university.edu | Easy | Login page visible. | 8 | 8 |
| PVS-081 | File Upload | Upload a provided resume file to a test upload form. | local/test or public test upload page | Hard | File selected and upload metadata visible; no real application submitted. | 16 | 16 |
| PVS-082 | File Upload | Use a drag-and-drop upload zone backed by file input. | local/test or public test upload page | Hard | File accepted by upload widget. | 16 | 16 |
| PVS-083 | File Upload | Replace an already selected file with a different provided file. | local/test or public test upload page | Hard | New filename visible. | 18 | 18 |
| PVS-084 | File Upload | Attempt upload without file and report validation message. | local/test or public test upload page | Medium | Validation message reported; no retry loop. | 10 | 10 |
| PVS-085 | File Download | Download a sample PDF and report filename. | w3.org or public sample file site | Medium | Download completed and filename metadata captured. | 12 | 12 |
| PVS-086 | File Download | Download a CSV sample and report completion metadata. | public sample file site | Medium | Download completion and filename recorded. | 12 | 12 |
| PVS-087 | File Download | Trigger a download from documentation page. | browser vendor docs/sample | Hard | Download started/completed or blocker. | 14 | 14 |
| PVS-088 | File Download | Identify a PDF link but do not download; report URL/title. | government/university site | Easy | PDF link identified and not clicked if user requested no download. | 8 | 8 |
| PVS-089 | Multi-tab Research | Open two product pages in separate tabs and compare prices. | shopping sites | Hard | Reports both prices and source tab titles. | 24 | 26 |
| PVS-090 | Multi-tab Research | Preserve Google search results while opening two results in new tabs. | google.com | Hard | Search tab remains known; two result tabs tracked. | 22 | 24 |
| PVS-091 | Multi-tab Research | Compare two documentation pages in separate tabs. | docs sites | Hard | Reports both source titles and differences. | 22 | 24 |
| PVS-092 | Multi-tab Research | Switch back to a previously opened repository tab and collect missing stars. | github.com | Hard | Correct tab focused and missing evidence collected. | 22 | 24 |
| PVS-093 | Multi-tab Research | Close an irrelevant tab while preserving active research tab. | any site | Medium | Non-pinned non-final tab closed; workspace updated. | 12 | 12 |
| PVS-094 | Cross-site Reasoning | Compare GitHub repository stars with npm package weekly downloads. | github.com / npmjs.com | Hard | Reports both metrics with sources. | 26 | 28 |
| PVS-095 | Cross-site Reasoning | Compare product price on Amazon and Walmart. | amazon.com / walmart.com | Hard | Reports both prices or site blockers. | 28 | 30 |
| PVS-096 | Cross-site Reasoning | Compare SaaS free plan between two vendors. | SaaS pricing pages | Hard | Reports both free-plan details. | 26 | 28 |
| PVS-097 | Long-running | Research five browser automation tools and produce a compact comparison. | multiple sites | Hard | Five tools tracked with at least one fact each. | 40 | 45 |
| PVS-098 | Long-running | Build a reading list of five official docs pages for a topic. | google.com + docs sites | Hard | Reports five official docs titles/URLs. | 35 | 40 |
| PVS-099 | Long-running | Fill a multi-page public form with provided dummy data up to final review. | public form site | Hard | Reaches review page without final submission. | 35 | 40 |
| PVS-100 | Long-running | Compare three job postings by title, company, location, and salary visibility. | job board | Hard | Reports structured comparison across three postings. | 40 | 45 |

## Recommended Sampling Bands

- Smoke: PVS-001, PVS-011, PVS-021, PVS-031, PVS-041, PVS-071, PVS-085, PVS-089.
- Daily validation: all Easy tasks plus 10 rotating Medium tasks.
- Weekly validation: all Medium tasks plus 20 rotating Hard tasks.
- Release validation: all 100 tasks.
