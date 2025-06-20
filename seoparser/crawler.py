import asyncio
import csv
import json
import os
from dataclasses import dataclass, asdict
from typing import Callable, List, Set, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
from bs4 import BeautifulSoup
import pandas as pd


@dataclass
class PageResult:
    url: str
    title: str = ""
    description: str = ""
    h1: str = ""
    canonical: str = ""
    meta_robots: str = ""
    status: int = 0
    error: str = ""


class SEOCrawler:
    def __init__(
        self,
        base_url: str,
        *,
        max_depth: int = 2,
        max_pages: int = 100,
        include_subdomains: bool = False,
        rate_limit: float = 1.0,
        autosave_interval: int = 50,
        session: Optional[aiohttp.ClientSession] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ):
        self.base_url = base_url.rstrip('/')
        self.parsed_base = urlparse(self.base_url)
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.include_subdomains = include_subdomains
        self.rate_limit = rate_limit
        self.autosave_interval = autosave_interval
        self.results: List[PageResult] = []
        self.errors: List[PageResult] = []
        self.visited: Set[str] = set()
        self.to_visit: asyncio.Queue = asyncio.Queue()
        self.session = session
        self.robot_parser = RobotFileParser()
        self.last_request = 0.0
        self.progress_callback = progress_callback

    async def initialize(self):
        await self.load_robots()
        await self.load_sitemap()
        await self.to_visit.put((self.base_url, 0))

    async def load_robots(self):
        robots_url = urljoin(self.base_url, '/robots.txt')
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(robots_url) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        self.robot_parser.parse(text.splitlines())
                    else:
                        self.robot_parser = RobotFileParser()
                        self.robot_parser.parse([])
        except Exception as exc:
            self.robot_parser = RobotFileParser()
            self.robot_parser.parse([])

    async def load_sitemap(self):
        sitemap_url = urljoin(self.base_url, '/sitemap.xml')
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(sitemap_url) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        from xml.etree import ElementTree as ET
                        root = ET.fromstring(text)
                        for loc in root.iterfind('.//{*}loc'):
                            url = loc.text.strip()
                            await self.to_visit.put((url, 0))
        except Exception:
            pass

    def allowed(self, url: str) -> bool:
        if not self.include_subdomains:
            parsed = urlparse(url)
            if parsed.hostname and parsed.hostname != self.parsed_base.hostname:
                return False
        return self.robot_parser.can_fetch('*', url)

    async def crawl(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        await self.initialize()
        while not self.to_visit.empty() and len(self.results) < self.max_pages:
            url, depth = await self.to_visit.get()
            if url in self.visited or depth > self.max_depth:
                continue
            if not self.allowed(url):
                continue
            self.visited.add(url)
            await self.rate_limit_wait()
            try:
                async with self.session.get(url) as resp:
                    status = resp.status
                    text = await resp.text(errors='ignore')
            except Exception as exc:
                self.errors.append(PageResult(url=url, status=0, error=str(exc)))
                continue
            page = self.parse_page(url, status, text)
            if status != 200:
                self.errors.append(page)
            self.results.append(page)
            if self.progress_callback:
                self.progress_callback(len(self.results), self.max_pages)
            if len(self.results) % self.autosave_interval == 0:
                self.autosave()
            if status == 200 and depth < self.max_depth:
                for link in self.extract_links(text, url):
                    if link not in self.visited:
                        await self.to_visit.put((link, depth + 1))
        await self.session.close()

    async def rate_limit_wait(self):
        elapsed = asyncio.get_event_loop().time() - self.last_request
        wait_for = self.rate_limit - elapsed
        if wait_for > 0:
            await asyncio.sleep(wait_for)
        self.last_request = asyncio.get_event_loop().time()

    def parse_page(self, url: str, status: int, html: str) -> PageResult:
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.title.string.strip() if soup.title and soup.title.string else ''
        desc_tag = soup.find('meta', attrs={'name': 'description'})
        description = desc_tag['content'].strip() if desc_tag and desc_tag.get('content') else ''
        h1_tag = soup.find('h1')
        h1 = h1_tag.get_text(strip=True) if h1_tag else ''
        canonical_tag = soup.find('link', rel='canonical')
        canonical = canonical_tag['href'].strip() if canonical_tag and canonical_tag.get('href') else ''
        robots_tag = soup.find('meta', attrs={'name': 'robots'})
        meta_robots = robots_tag['content'].strip() if robots_tag and robots_tag.get('content') else ''
        return PageResult(url, title, description, h1, canonical, meta_robots, status)

    def extract_links(self, html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            href = urljoin(base_url, a['href'])
            if href.startswith('http') and self.allowed(href):
                links.append(href)
        return links

    def autosave(self):
        df = pd.DataFrame([asdict(r) for r in self.results])
        df.to_csv('autosave.csv', index=False)
        df.to_excel('autosave.xlsx', index=False)

    def export(self, basename: str = 'results'):
        df = pd.DataFrame([asdict(r) for r in self.results])
        df.to_csv(f'{basename}.csv', index=False)
        df.to_excel(f'{basename}.xlsx', index=False)
        with open(f'{basename}.json', 'w', encoding='utf-8') as f:
            json.dump([asdict(r) for r in self.results], f, ensure_ascii=False, indent=2)
        if self.errors:
            with open(f'{basename}_errors.log', 'w', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(PageResult.__annotations__.keys())
                for err in self.errors:
                    writer.writerow(asdict(err).values())
