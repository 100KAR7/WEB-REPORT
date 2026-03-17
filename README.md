# AI-Powered Website Testing System
< img src="https://www.thebluediamondgallery.com/handwriting/images/testing.jpg" width="100">
A modular, scalable Python framework for automated website analysis using AI.

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
export OPENAI_API_KEY="your_api_key_here"   # Linux / Mac
set OPENAI_API_KEY=your_api_key_here        # Windows
```
### 6️⃣ Run the Tester
```bash
python main.py --url https://example.com
```
## THE PROJECT WILL NOT SUPPORT THE LLM FEATURE RIGHT NOW AND THE HTML REPORT WILL NOT OPEN RIGHT NOW 
