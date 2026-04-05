# AI-Powered Website Testing System
<img src="https://www.thebluediamondgallery.com/handwriting/images/testing.jpg" width="100">
A modular, scalable Python framework for automated website analysis using AI.

## Highlights

- Crawl a site and measure page response times
- Detect broken links with source-page tracking
- Audit on-page SEO issues and sitewide duplicate metadata
- Generate a richer HTML and JSON report with health scoring, recommendations, and page rankings
- Optionally add AI-written content and UX insights

## Project Structure

```
ai_web_tester/
├── config/          # Settings & environment config
├── crawler/         # Web crawling & page fetching
├── tests/           # Functional & performance tests
├── seo/             # SEO checks & audits
├── ai_analysis/     # AI-powered content analysis
├── reports/         # Report generation (HTML/JSON)
├── pipeline/        # Orchestration & workflow
├── main.py          # Entry point
└── requirements.txt
```
## ⚡ Quick Start

```bash
pip install -r requirements.txt
playwright install
python main.py --url https://example.com
```
## ⚙️ Full Setup (Recommended)
### 1️⃣ Clone the Repository
```bash
git clone https://github.com/your-username/ai-website-tester.git
cd ai-website-tester
```
### 2️⃣ Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate     # Linux / Mac
venv\Scripts\activate        # Windows
```
### 3️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```
### 4️⃣ Install Playwright Browsers
```bash
playwright install
```
### 5️⃣ Setup Environment Variables
```bash
export ANTHROPIC_API_KEY="your_api_key_here"   # Linux / Mac
set ANTHROPIC_API_KEY=your_api_key_here        # Windows
```
### 6️⃣ Run the Tester
```bash
python main.py --url https://example.com
```
