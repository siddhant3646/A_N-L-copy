import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

async def inspect():
    b = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await b.start()
    p = await b.get_current_page() or await b.new_page()
    await p.goto('https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B', wait_until='domcontentloaded')
    await asyncio.sleep(3)
    cards = await p.evaluate('''() => {
        const out = [];
        document.querySelectorAll('div.cardOutline.tapItem.result, div[data-jk]').forEach(c => {
            const jk = c.getAttribute('data-jk');
            if (jk) {
                const isEasilyApply = c.innerText.includes('Easily apply') || c.innerText.includes('Apply with your Indeed');
                out.push({ jk, isEasilyApply, snippet: c.innerText.slice(0, 100) });
            }
        });
        return out.slice(0, 5);
    }''')
    for c in cards:
        print('CARD:', c)
    
    for c in cards[:3]:
        jk = c['jk']
        print(f"\n--- Checking viewjob?jk={jk} ---")
        await p.goto(f"https://in.indeed.com/viewjob?jk={jk}", wait_until='domcontentloaded')
        await asyncio.sleep(3)
        res = await p.evaluate('''() => {
            const btns = Array.from(document.querySelectorAll('button, a')).map(el => ({
                tag: el.tagName,
                id: el.id,
                testid: el.getAttribute('data-testid'),
                href: el.getAttribute('href'),
                text: el.innerText.trim()
            })).filter(x => x.text.toLowerCase().includes('apply') || (x.href && x.href.includes('smartapply')) || (x.testid && x.testid.includes('apply')));
            return {
                title: document.title,
                url: window.location.href,
                applyElements: btns
            };
        }''')
        print(f"Title: {res['title']}")
        print(f"URL: {res['url']}")
        print(f"Apply elements: {res['applyElements']}")

    await b.stop(fast=True)
    await reset_shared_playwright()

if __name__ == '__main__':
    asyncio.run(inspect())
