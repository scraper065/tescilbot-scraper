"""
TescilBot TÜRKPATENT Scraper
Railway/Render deployment
"""
import asyncio
import json
import re
import os
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from typing import Optional, List
import httpx

app = FastAPI(title="TescilBot Scraper", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Browser instance
browser = None
playwright_instance = None

async def get_browser():
    global browser, playwright_instance
    if browser is None:
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-gpu'
            ]
        )
    return browser

@app.on_event("shutdown")
async def shutdown():
    global browser, playwright_instance
    if browser:
        await browser.close()
    if playwright_instance:
        await playwright_instance.stop()

# ==================== TÜRKPATENT SCRAPER ====================

async def scrape_turkpatent(query: str) -> dict:
    """TÜRKPATENT'ten marka ara"""
    results = {
        'query': query,
        'source': 'turkpatent',
        'trademarks': [],
        'error': None
    }
    
    try:
        b = await get_browser()
        context = await b.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            locale='tr-TR'
        )
        page = await context.new_page()
        
        # Anti-bot bypass
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)
        
        # TÜRKPATENT arama sayfası
        url = f"https://www.turkpatent.gov.tr/arastirma-yap"
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)
        
        # Marka sekmesine tıkla
        try:
            marka_tab = await page.wait_for_selector('text=Marka', timeout=5000)
            if marka_tab:
                await marka_tab.click()
                await asyncio.sleep(1)
        except:
            pass
        
        # Input bul ve doldur
        input_selectors = [
            'input[name*="marka"]',
            'input[placeholder*="marka"]',
            'input[id*="marka"]',
            '#markaAdi',
            'input[type="text"]'
        ]
        
        filled = False
        for sel in input_selectors:
            try:
                inp = await page.query_selector(sel)
                if inp:
                    await inp.fill(query)
                    filled = True
                    break
            except:
                continue
        
        if not filled:
            # JavaScript ile doldur
            await page.evaluate(f'''
                const inputs = document.querySelectorAll('input');
                for (let i of inputs) {{
                    if (i.type === 'text' || i.name.includes('marka')) {{
                        i.value = "{query}";
                        i.dispatchEvent(new Event('input', {{bubbles: true}}));
                        break;
                    }}
                }}
            ''')
        
        # Ara butonuna tıkla
        btn_selectors = [
            'button[type="submit"]',
            'button:has-text("Ara")',
            'button:has-text("Search")',
            '.search-btn',
            '#searchBtn',
            'input[type="submit"]'
        ]
        
        for sel in btn_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    break
            except:
                continue
        
        # Sonuçları bekle
        await asyncio.sleep(3)
        
        # Sonuçları parse et
        # Tablo satırları
        rows = await page.query_selector_all('table tbody tr, .result-item, .marka-sonuc')
        
        for row in rows[:30]:
            try:
                cells = await row.query_selector_all('td')
                if len(cells) >= 3:
                    name = await cells[0].inner_text()
                    app_no = await cells[1].inner_text() if len(cells) > 1 else ''
                    owner = await cells[2].inner_text() if len(cells) > 2 else ''
                    status = await cells[3].inner_text() if len(cells) > 3 else ''
                    classes_text = await cells[4].inner_text() if len(cells) > 4 else ''
                    
                    classes = [int(c) for c in re.findall(r'\d+', classes_text)]
                    
                    if name and len(name.strip()) > 1:
                        results['trademarks'].append({
                            'name': name.strip().upper(),
                            'application_no': app_no.strip(),
                            'owner': owner.strip(),
                            'classes': classes,
                            'status': status.strip() or 'Bilinmiyor',
                            'source': 'TÜRKPATENT'
                        })
            except Exception as e:
                continue
        
        # Alternatif: JSON veri varsa al
        if not results['trademarks']:
            try:
                data = await page.evaluate('''
                    () => {
                        const items = [];
                        // Tüm text'leri tara
                        const walker = document.createTreeWalker(
                            document.body,
                            NodeFilter.SHOW_TEXT,
                            null,
                            false
                        );
                        let node;
                        while (node = walker.nextNode()) {
                            const text = node.textContent.trim();
                            if (text.match(/^[A-ZÇĞİÖŞÜ0-9\\s]{2,30}$/) && !text.match(/^(Ara|Search|Marka|Sonuç)/)) {
                                items.push({name: text, source: 'TÜRKPATENT'});
                            }
                        }
                        return items.slice(0, 20);
                    }
                ''')
                if data:
                    results['trademarks'] = data
            except:
                pass
        
        await context.close()
        
    except Exception as e:
        results['error'] = str(e)
    
    return results

# ==================== WIPO SCRAPER ====================

async def scrape_wipo(query: str) -> dict:
    """WIPO Global Brand Database'den ara"""
    results = {
        'query': query,
        'source': 'wipo',
        'trademarks': [],
        'error': None
    }
    
    try:
        b = await get_browser()
        context = await b.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        url = f"https://branddb.wipo.int/branddb/en/?q={query}"
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)
        
        # CAPTCHA kontrolü
        captcha = await page.query_selector('[class*="captcha"], #captcha')
        if captcha:
            results['error'] = 'CAPTCHA gerekli'
            await context.close()
            return results
        
        # Sonuçları al
        rows = await page.query_selector_all('.result-row, .brand-result, table tr')
        
        for row in rows[:20]:
            try:
                name_el = await row.query_selector('.brand-name, td:first-child, .name')
                if name_el:
                    name = await name_el.inner_text()
                    if name and len(name.strip()) > 1:
                        results['trademarks'].append({
                            'name': name.strip().upper(),
                            'source': 'WIPO'
                        })
            except:
                continue
        
        await context.close()
        
    except Exception as e:
        results['error'] = str(e)
    
    return results

# ==================== EUIPO SCRAPER ====================

async def scrape_euipo(query: str) -> dict:
    """EUIPO'dan ara"""
    results = {
        'query': query,
        'source': 'euipo',
        'trademarks': [],
        'error': None
    }
    
    try:
        b = await get_browser()
        context = await b.new_context()
        page = await context.new_page()
        
        url = f"https://euipo.europa.eu/eSearch/#basic/{query}"
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)
        
        # Sonuçları al
        items = await page.query_selector_all('.search-result, .trademark-item, tr.result')
        
        for item in items[:20]:
            try:
                name_el = await item.query_selector('.trademark-name, .name, td:first-child')
                if name_el:
                    name = await name_el.inner_text()
                    if name:
                        results['trademarks'].append({
                            'name': name.strip().upper(),
                            'source': 'EUIPO'
                        })
            except:
                continue
        
        await context.close()
        
    except Exception as e:
        results['error'] = str(e)
    
    return results

# ==================== API ENDPOINTS ====================

@app.get("/")
async def root():
    return {
        "name": "TescilBot Scraper API",
        "version": "1.0",
        "sources": ["TÜRKPATENT", "WIPO", "EUIPO"],
        "status": "active"
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "browser": browser is not None}

@app.get("/scrape/turkpatent")
async def api_turkpatent(q: str):
    """TÜRKPATENT'ten ara"""
    if len(q) < 2:
        raise HTTPException(400, "Min 2 karakter")
    return await scrape_turkpatent(q)

@app.get("/scrape/wipo")
async def api_wipo(q: str):
    """WIPO'dan ara"""
    if len(q) < 2:
        raise HTTPException(400, "Min 2 karakter")
    return await scrape_wipo(q)

@app.get("/scrape/euipo")
async def api_euipo(q: str):
    """EUIPO'dan ara"""
    if len(q) < 2:
        raise HTTPException(400, "Min 2 karakter")
    return await scrape_euipo(q)

@app.get("/scrape/all")
async def api_all(q: str):
    """Tüm kaynaklardan ara"""
    if len(q) < 2:
        raise HTTPException(400, "Min 2 karakter")
    
    # Paralel scraping
    results = await asyncio.gather(
        scrape_turkpatent(q),
        scrape_wipo(q),
        scrape_euipo(q),
        return_exceptions=True
    )
    
    all_trademarks = []
    errors = []
    
    for r in results:
        if isinstance(r, dict):
            all_trademarks.extend(r.get('trademarks', []))
            if r.get('error'):
                errors.append(f"{r['source']}: {r['error']}")
        elif isinstance(r, Exception):
            errors.append(str(r))
    
    # Deduplicate
    seen = set()
    unique = []
    for tm in all_trademarks:
        if tm['name'] not in seen:
            seen.add(tm['name'])
            unique.append(tm)
    
    return {
        'query': q,
        'total': len(unique),
        'trademarks': unique,
        'errors': errors if errors else None
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
