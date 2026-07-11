import requests
import re
import json
from urllib.parse import quote_plus
from datetime import datetime
from bs4 import BeautifulSoup
import time

class AtlasFeedExtractor:
    def __init__(self):
        self.blog_id = "4779734925367992915"
        self.feed_url = f"https://www.blogger.com/feeds/{self.blog_id}/posts/default"
        self.base_url = "https://atlasship.blogspot.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Improved patterns with exact field matching
        self.field_patterns = {
            'type_designation': [
                r'TYPE\s+DESIGNATION\s*[:：]\s*([A-Z0-9\s\-]+)',
                r'TYPE\s+DESIGNATION\s*[:：]\s*([^\n]+)'
            ],
            'version': [
                r'VER\.?\s*[:：]?\s*([0-9\.]+)',
                r'VER\.?\s*[:：]?\s*([A-Z0-9\.]+)'
            ],
            'serial_no': [
                r'SERIAL\.?NO\s*[:：]\s*([A-Z0-9/\-]+)',
                r'SERIAL\s+NUMBER\s*[:：]\s*([A-Z0-9/\-]+)',
                r'SN\s*[:：]\s*([A-Z0-9/\-]+)'
            ],
            'date': [
                r'DATE\s*[:：]\s*([\d\-\.\/]+)'
            ],
            'certificate': [
                r'CERTIFICATE\s*[:：]\s*([A-Z0-9&\-]+)'
            ],
            'approved_by': [
                r'APPROVED\s+BY\s*[:：]\s*([A-Z0-9\s\(\)\-]+)'
            ],
            'approved_for': [
                r'APPROVED\s+FOR\s*[:：]\s*([A-Z\s]+)'
            ],
            'rated_voltage': [
                r'RATED\s+VOLTAGE\s*[:：]\s*([A-Z0-9\s]+)'
            ],
            'rated_current': [
                r'RATED\s+CURRENT\s*[:：]\s*([A-Z0-9\.\s]+)'
            ],
            'made_in': [
                r'MADE\s+IN\s*[:：]\s*([A-Z\s]+)'
            ],
            'condition': [
                r'CONDITION\s*[:：]\s*([A-Z\s\/\-]+)'
            ],
            'ref_no': [
                r'REF\.?NO\(S\)\s*[:：]?\s*([A-Z0-9/\.]+)',
                r'REF\.?NO\s*[:：]?\s*([A-Z0-9/\.]+)'
            ],
            'mepc': [
                r'MEPC\s+([\d\(\)&]+)'
            ],
            'certificate_no': [
                r'CERTIFICATE\s+NO\s*[:：]\s*([A-Z0-9\-]+)'
            ]
        }
    
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
                        time.sleep(0.3)
                
                return results
            else:
                print(f"✗ No posts found for '{query}'")
                return []
                
        except Exception as e:
            print(f"Error searching: {e}")
            return []
    
    def extract_image_from_html(self, html_content: str) -> str:
        """Extract the first valid image URL from HTML content"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all img tags
        images = soup.find_all('img')
        
        for img in images:
            src = img.get('src', '')
            if not src:
                continue
            
            if 'icon' in src.lower() or 'avatar' in src.lower():
                continue
            
            if 'blogger.googleusercontent.com' in src:
                if '/s72-c/' in src or '/s320/' in src:
                    src = re.sub(r'/s\d+(-c)?/', '/s1600/', src)
                return src
            
            if src.startswith('http') and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                return src
        
        return None
    
    def extract_field_value(self, content: str, field: str, patterns: list) -> str:
        """Extract a specific field value using multiple patterns"""
        for pattern in patterns:
            # Search with multiline support
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                # Clean up common issues
                value = re.sub(r'\s+', ' ', value)  # Remove extra spaces
                return value
        return None
    
    def extract_from_entry(self, entry):
        """Extract all fields from a feed entry"""
        content = entry.get('content', {}).get('$t', '')
        title = entry.get('title', {}).get('$t', '')
        published = entry.get('published', {}).get('$t', '')
        
        # Get URL
        url = None
        for link in entry.get('link', []):
            if link.get('rel') == 'alternate':
                url = link.get('href')
                break
        
        # Extract data
        extracted = {
            'title': title,
            'url': url,
            'published': published,
            'image_url': None,
            'data': {}
        }
        
        # Extract image from content
        if content:
            image_url = self.extract_image_from_html(content)
            if image_url:
                extracted['image_url'] = image_url
        
        # Extract each field using specific patterns
        for field, patterns in self.field_patterns.items():
            value = self.extract_field_value(content, field, patterns)
            if value:
                extracted['data'][field] = value
        
        # Try to extract serial number from title if not found
        if not extracted['data'].get('serial_no'):
            serial_match = re.search(r'(?:SERIAL|SN)[\s:]+([A-Z0-9/\-]+)', title, re.IGNORECASE)
            if serial_match:
                extracted['data']['serial_no'] = serial_match.group(1)
        
        # Try to extract ref_no from title if not found
        if not extracted['data'].get('ref_no'):
            ref_match = re.search(r'REF[\s:]+([A-Z0-9/\.]+)', title, re.IGNORECASE)
            if ref_match:
                extracted['data']['ref_no'] = ref_match.group(1)
        
        # Only return if we have data
        if extracted['data'] or extracted['image_url']:
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
            print(f"📝 Title: {result.get('title', 'N/A')}")
            print(f"🔗 URL: {result.get('url', 'N/A')}")
            if result.get('published'):
                print(f"📅 Date: {result.get('published')[:10]}")
            
            if result.get('image_url'):
                print(f"🖼️  Image: {result['image_url']}")
            
            data = result.get('data', {})
            if data:
                print(f"\n📊 SPECIFICATIONS:")
                # Display in order
                display_order = [
                    'type_designation', 'version', 'serial_no', 'date',
                    'certificate', 'certificate_no', 'approved_by', 
                    'approved_for', 'rated_voltage', 'rated_current',
                    'made_in', 'condition', 'ref_no', 'mepc'
                ]
                for field in display_order:
                    if field in data:
                        label = field.replace('_', ' ').upper()
                        print(f"  {label:20}: {data[field]}")
                
                # Any remaining fields
                for field, value in data.items():
                    if field not in display_order:
                        label = field.replace('_', ' ').upper()
                        print(f"  {label:20}: {value}")
            else:
                print("\n  ⚠️ No structured data found")
        
        print("\n" + "="*70)

def main():
    extractor = AtlasFeedExtractor()
    
    print("\n" + "="*70)
    print("🔍 ATLAS SHIPCARE - PRODUCT EXTRACTOR (IMPROVED)")
    print("="*70)
    print("\nThis tool searches blog posts and extracts:")
    print("  • All specifications with better accuracy")
    print("  • First image URL")
    print("  • Reference numbers and certificates")
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
        
        results = extractor.search_posts(query)
        extractor.format_results(results)
        
        if results:
            print("\n💡 Tip: Try searching with just 'ODME' or 'KSB' to find all related posts")

if __name__ == "__main__":
    main()