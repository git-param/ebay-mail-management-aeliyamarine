import requests
import re
import json
from urllib.parse import quote_plus
from datetime import datetime

class BlogFeedExtractor:
    def __init__(self):
        self.blog_id = "4779734925367992915"
        self.feed_url = f"https://www.blogger.com/feeds/{self.blog_id}/posts/default"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Enhanced patterns
        self.serial_patterns = [
            r'SERIAL\.?NO\s*[:：]\s*([A-Z0-9/\-]+)',
            r'[A-Z]{2,3}-\d+-\d+',  # Pattern like KSM-16-163
            r'\d+/\d+',  # Pattern like 3/60
        ]
        
        self.condition_patterns = [
            r'CONDITION\s*[:：]\s*([A-Z\s]+)',
        ]
        
        self.ref_patterns = [
            r'REF\.?NO\s*[:：]?\s*([A-Z0-9/\.]+)',
            r'REF\.?NO\(S\)\s*[:：]?\s*([A-Z0-9/\.]+)',
        ]
        
    def search_posts(self, query: str):
        """Search posts using Blogger API"""
        search_url = f"{self.feed_url}?q={quote_plus(query)}&v=2&alt=json"
        
        try:
            response = requests.get(search_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'feed' in data and 'entry' in data['feed']:
                entries = data['feed']['entry']
                print(f"✓ Found {len(entries)} posts matching '{query}'")
                
                results = []
                for entry in entries:
                    extracted = self.extract_from_entry(entry)
                    if extracted:
                        results.append(extracted)
                
                return results
            else:
                print(f"✗ No posts found for '{query}'")
                return []
                
        except Exception as e:
            print(f"Error searching: {e}")
            return []
    
    def extract_from_entry(self, entry):
        """Extract serial, condition, ref from a feed entry"""
        content = entry.get('content', {}).get('$t', '')
        title = entry.get('title', {}).get('$t', '')
        published = entry.get('published', {}).get('$t', '')
        
        # Extract data
        serial = None
        for pattern in self.serial_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                if 'SERIAL' in pattern:
                    serial = match.group(1).strip()
                else:
                    serial = match.group(0).strip()
                break
        
        condition = None
        for pattern in self.condition_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                condition = match.group(1).strip()
                break
        
        ref_no = None
        for pattern in self.ref_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                ref_no = match.group(1).strip()
                break
        
        # Get URL
        url = None
        for link in entry.get('link', []):
            if link.get('rel') == 'alternate':
                url = link.get('href')
                break
        
        extracted = {
            'title': title,
            'url': url,
            'published': published,
            'serial_no': serial,
            'condition': condition,
            'ref_no': ref_no,
        }
        
        # Only return if we found something
        if serial or condition or ref_no:
            return extracted
        return None
    
    def format_results(self, results):
        """Format and print results nicely"""
        if not results:
            print("\n❌ No results found")
            return
        
        print("\n" + "="*70)
        print(f"📋 FOUND {len(results)} RESULT(S)")
        print("="*70)
        
        for i, result in enumerate(results, 1):
            print(f"\n{'─'*70}")
            print(f"📌 RESULT {i}")
            print(f"{'─'*70}")
            print(f"📝 Title: {result.get('title', 'N/A')[:60]}...")
            print(f"🔗 URL: {result.get('url', 'N/A')}")
            if result.get('published'):
                print(f"📅 Date: {result.get('published')[:10]}")
            
            print(f"\n🔢 SERIAL NO: {result.get('serial_no', '❌ Not found')}")
            print(f"📦 CONDITION: {result.get('condition', '❌ Not found')}")
            print(f"📎 REF NO: {result.get('ref_no', '❌ Not found')}")
        
        print("\n" + "="*70)

def main():
    extractor = BlogFeedExtractor()
    
    print("\n" + "="*70)
    print("🔍 BLOGGER FEED EXTRACTOR - PRODUCT DATA")
    print("="*70)
    print("\nThis tool searches blog posts and extracts:")
    print("  • Serial Number")
    print("  • Condition")
    print("  • Reference Number")
    print("="*70)
    
    while True:
        print("\n" + "─"*70)
        query = input("🔎 Enter product name/SKU (or 'quit' to exit): ").strip()
        
        if query.lower() == 'quit':
            print("\n👋 Goodbye!")
            break
        
        if not query:
            print("⚠️ Please enter a search term")
            continue
        
        # Search and display results
        results = extractor.search_posts(query)
        extractor.format_results(results)
        
        # Offer to extract all data
        if results:
            print("\n💡 Tip: Try searching with just 'ODME' to find all related posts")

if __name__ == "__main__":
    main()