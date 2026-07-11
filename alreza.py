import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import quote_plus, urljoin
import time

class AlRezaExtractor:
    def __init__(self):
        self.base_url = "https://www.alrezaenterprise.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Complete patterns for all fields from your image
        self.patterns = {
            'brand': [r'BRAND\s*[:：]\s*([A-Z0-9\-]+)'],
            'model': [r'MODEL\s*[:：]\s*([A-Z0-9\-]+)'],
            'type': [r'TYPE\s*[:：]\s*([A-Z0-9\s\-]+)'],
            'rating': [r'RATING\s*[:：]\s*([A-Z0-9\s\/]+)'],
            'input_voltage': [r'(?:INPUT\s*)?VOLTAGE\s*[:：]\s*([A-Z0-9\/\s]+)'],
            'frequency': [r'FREQUENCY\s*[:：]\s*([A-Z0-9\s]+)'],
            'control_input': [r'CONTROL\s*INPUT\s*[:：]\s*([A-Z0-9\-]+)'],
            'power_device': [r'POWER\s*DEVICE\s*[:：]\s*([A-Z0-9\s\(\)]+)'],
            'phase': [r'PHASE\s*[:：]\s*([A-Z0-9]+)'],
            'application': [r'APPLICATION\s*[:：]\s*([A-Z0-9\s,]+)'],
            'condition': [r'CONDITION\s*[:：]\s*([A-Z0-9\s\/\-]+)'],
            'qty': [r'QTY\s*[:：]\s*([A-Z0-9]+)'],
            'ref': [r'REF\s*[:：]?\s*([A-Z0-9\/\.]+)'],
        }
    
    def search_blog(self, query: str):
        """Search the blog using its search function"""
        search_url = f"{self.base_url}/search?q={quote_plus(query)}"
        
        print(f"\n🔍 Searching: {search_url}")
        
        try:
            response = requests.get(search_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all post links
            post_links = []
            
            # Look for post titles with links
            for title_elem in soup.find_all(['h2', 'h3', 'h1']):
                link = title_elem.find('a')
                if link:
                    href = link.get('href')
                    if href and ('/202' in href or '/search' not in href):
                        post_links.append({
                            'title': link.get_text(strip=True),
                            'url': urljoin(self.base_url, href)
                        })
            
            # Also find any other post links
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if '/202' in href and href not in [p['url'] for p in post_links]:
                    post_links.append({
                        'title': link.get_text(strip=True) or 'Blog Post',
                        'url': urljoin(self.base_url, href)
                    })
            
            # Remove duplicates
            seen = set()
            unique_links = []
            for post in post_links:
                if post['url'] not in seen:
                    seen.add(post['url'])
                    unique_links.append(post)
            
            if unique_links:
                print(f"✓ Found {len(unique_links)} blog posts")
                return unique_links
            else:
                print("✗ No posts found")
                return []
                
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def extract_first_image(self, soup):
        """Extract the first image URL from the post"""
        # Find all images
        images = soup.find_all('img')
        
        for img in images:
            src = img.get('src', '')
            # Skip icon images, avatars, etc.
            if 'icon' in src.lower() or 'avatar' in src.lower():
                continue
            if 's72-c' in src:  # Blogger thumbnail
                # Convert to full size by removing size parameter
                src = re.sub(r's\d+(-c)?', 's1600', src)
            if src and src.startswith('http'):
                return src
        
        # Try to find images in the content div
        content = soup.find('div', {'class': 'post-body'}) or soup.find('div', {'class': 'entry-content'})
        if content:
            img = content.find('img')
            if img:
                src = img.get('src', '')
                if src and src.startswith('http'):
                    return src
        
        return None
    
    def extract_from_post(self, post_data):
        """Extract all product details from a specific post"""
        url = post_data['url']
        title = post_data['title']
        
        print(f"\n  📄 Extracting from: {title[:50]}...")
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get all text
            text = soup.get_text(separator=' ', strip=True)
            
            extracted = {
                'title': title,
                'url': url,
                'image_url': None,
                'data': {}
            }
            
            # Extract first image
            image_url = self.extract_first_image(soup)
            if image_url:
                extracted['image_url'] = image_url
                print(f"  ✓ Found image: {image_url[:60]}...")
            
            # Extract all fields using patterns
            for field, pattern_list in self.patterns.items():
                for pattern in pattern_list:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        extracted['data'][field] = match.group(1).strip()
                        break
            
            # Also try to find model from title if not found
            if not extracted['data'].get('model'):
                model_match = re.search(r'(TPR-\w+)', title, re.IGNORECASE)
                if model_match:
                    extracted['data']['model'] = model_match.group(1)
            
            # Try to find rating from title if not found
            if not extracted['data'].get('rating'):
                rating_match = re.search(r'(\d+)\s*A', title, re.IGNORECASE)
                if rating_match:
                    extracted['data']['rating'] = f"{rating_match.group(1)}A"
            
            # Try to find voltage from title if not found
            if not extracted['data'].get('input_voltage'):
                voltage_match = re.search(r'(AC\s*\d+/\d+V|\d+V)', title, re.IGNORECASE)
                if voltage_match:
                    extracted['data']['input_voltage'] = voltage_match.group(1)
            
            # Clean up - remove None values
            extracted['data'] = {k: v for k, v in extracted['data'].items() if v}
            
            if extracted['data']:
                print(f"  ✓ Found {len(extracted['data'])} fields")
            else:
                print(f"  ⚠️ No structured data found")
            
            return extracted
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return None
    
    def search_and_extract(self, query: str):
        """Main function: Search and extract from all found posts"""
        print("\n" + "="*70)
        print(f"🔍 SEARCHING FOR: {query}")
        print("="*70)
        
        # Step 1: Search for posts
        posts = self.search_blog(query)
        
        if not posts:
            print("\n❌ No posts found")
            return []
        
        # Step 2: Extract from each post
        print(f"\n📋 Extracting data from {len(posts)} post(s)...")
        results = []
        
        for i, post in enumerate(posts, 1):
            print(f"\n{'─'*50}")
            print(f"Post {i}/{len(posts)}")
            extracted = self.extract_from_post(post)
            if extracted and extracted['data']:
                results.append(extracted)
            time.sleep(0.5)  # Be polite
        
        return results
    
    def print_results(self, results):
        """Print formatted results with all details"""
        if not results:
            print("\n" + "="*70)
            print("❌ NO DATA FOUND")
            print("="*70)
            return
        
        print("\n" + "="*70)
        print(f"📋 FOUND {len(results)} PRODUCT(S)")
        print("="*70)
        
        for i, result in enumerate(results, 1):
            print(f"\n{'─'*70}")
            print(f"📌 PRODUCT {i}")
            print(f"{'─'*70}")
            print(f"📝 Title: {result['title'][:80]}...")
            print(f"🔗 URL: {result['url']}")
            
            # Show image URL if found
            if result.get('image_url'):
                print(f"🖼️  Image: {result['image_url']}")
            
            data = result['data']
            if data:
                print(f"\n📊 SPECIFICATIONS:")
                # Display in a nice order
                display_order = ['brand', 'model', 'type', 'rating', 'input_voltage', 
                               'frequency', 'control_input', 'power_device', 'phase',
                               'application', 'condition', 'qty', 'ref']
                for field in display_order:
                    if field in data:
                        label = field.replace('_', ' ').upper()
                        print(f"  {label:20}: {data[field]}")
                
                # Display any remaining fields
                for field, value in data.items():
                    if field not in display_order:
                        label = field.replace('_', ' ').upper()
                        print(f"  {label:20}: {value}")
            else:
                print("\n  ⚠️ No structured data found on this page")
        
        print("\n" + "="*70)

def main():
    extractor = AlRezaExtractor()
    
    print("\n" + "="*70)
    print("🔍 AL REZA ENTERPRISE - PRODUCT EXTRACTOR")
    print("="*70)
    print("\nThis tool searches the Al Reza blog and extracts:")
    print("  • All specifications (Brand, Model, Type, Rating, etc.)")
    print("  • First image URL")
    print("  • Condition, Quantity, Reference")
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
        
        # Search and extract
        results = extractor.search_and_extract(query)
        extractor.print_results(results)
        
        print("\n💡 Tip: Try searching for 'TPR', 'TPR-2P', or 'thyristor'")

if __name__ == "__main__":
    main()